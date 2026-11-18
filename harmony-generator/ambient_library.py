"""Local metadata-only Ambient library; no audio is written by this module."""

import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

LIBRARY_DIR = Path(__file__).parent / "data" / "ambient_saved"


def fingerprint(metadata):
    # Includes source stimulus ID and the exact render recipe. Independently
    # generated stimuli or deliberately changed rendering settings remain distinct.
    return hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_metadata(metadata):
    for key in ("chord", "selection_settings", "states", "transitions", "rendering"):
        if key not in metadata:
            raise ValueError(f"Missing reconstruction metadata: {key}.")
    states = metadata["states"]
    if not 1 <= len(states) <= 3 or not 2 <= len(states[0]["notes_midi"]) <= 5:
        raise ValueError("Invalid saved harmonic states.")
    for state in states:
        pitches = state["notes_midi"]
        if (len(pitches) != len(states[0]["notes_midi"]) or pitches != sorted(set(pitches))
                or any(type(pitch) is not int or not 0 <= pitch <= 127 for pitch in pitches)
                or len(state["voices"]) != len(pitches)):
            raise ValueError("Invalid saved pitches or voice assignments.")
        for key in ("start_seconds", "end_seconds", "notes_names"):
            if key not in state:
                raise ValueError(f"Missing state metadata: {key}.")
    audio = metadata["rendering"]
    for key in ("duration_seconds", "backend", "timbre", "reverb", "effect_level",
                "sample_rate", "renderer_version"):
        if key not in audio:
            raise ValueError(f"Missing rendering metadata: {key}.")
    if not 10 <= audio["duration_seconds"] <= 90:
        raise ValueError("Invalid saved duration.")
    if audio["backend"] == "SoundFont":
        font = audio["soundfont"]
        for key in ("path", "sha256", "bank", "program"):
            if key not in font:
                raise ValueError(f"Missing SoundFont identity: {key}.")
    elif audio["backend"] != "Procedural":
        raise ValueError("Unknown saved audio backend.")
    fingerprint(metadata)  # Reject non-JSON data and NaNs before persisting.


@contextmanager
def locked():
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    with (LIBRARY_DIR / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _atomic_record(record, destination=None):
    if destination is None:
        destination = LIBRARY_DIR / f"{UUID(record['saved_id']).hex}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix=".pending-", dir=LIBRARY_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(record, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.flush()
            os.fsync(target.fileno())
        os.replace(path, destination)
    finally:
        Path(path).unlink(missing_ok=True)


def list_records():
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    records, errors = [], []
    for path in LIBRARY_DIR.glob("*.json"):
        if path.name.startswith("."):
            continue
        try:
            if path.is_symlink():
                raise ValueError("Symbolic links are not supported.")
            record = json.loads(path.read_text(encoding="utf-8"))
            if UUID(record["saved_id"]).hex != path.stem:
                raise ValueError("Saved ID does not match its filename.")
            if record.get("batch_id") and not read_batch(record["batch_id"]).get("committed"):
                continue
            record = hydrate(record)
            validate_metadata(record["metadata"])
            if record["source_fingerprint"] != fingerprint(record["metadata"]):
                raise ValueError("Saved metadata fingerprint does not match.")
            datetime.fromisoformat(record.get("generated_at") or record["saved_at"])
            records.append(record)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            errors.append((path.name, str(error)))
    records.sort(key=lambda r: datetime.fromisoformat(r.get("generated_at") or r["saved_at"]).timestamp(), reverse=True)
    return records, errors


def save_stimulus(metadata):
    validate_metadata(metadata)
    token = fingerprint(metadata)
    with locked():
        records, _ = list_records()
        for record in records:
            if (record["source_fingerprint"] == token or
                    (record.get("record_type") == "collected" and
                     record["metadata"].get("stimulus_id") == metadata.get("stimulus_id"))):
                raw = read_record(record["saved_id"])
                changed = _status(raw, "saved")
                if changed:
                    _atomic_record(raw)
                return hydrate(raw), changed
        record = {"saved_id": uuid4().hex, "saved_at": datetime.now(timezone.utc).isoformat(),
                  "source_fingerprint": token, "metadata": metadata,
                  "record_type": "manual_saved", "schema_version": 2,
                  "status": "saved", "notes": "", "latest_decision_at": now(),
                  "status_history": [{"status": "saved", "at": now()}]}
        _atomic_record(record)
    return record, True


def delete_saved(identity):
    identity = UUID(identity).hex
    protect_study_stimulus(identity)
    with locked():
        path = LIBRARY_DIR / f"{identity}.json"
        if path.exists():
            raw = read_record(identity)
            if raw.get("record_type") == "collected":
                if _status(raw, "unreviewed"):
                    _atomic_record(raw)
                return
        # Prevent a deleted migrated record from being imported again. Retain
        # unverified legacy WAVs and metadata together, outside the active scan.
        for directory in LIBRARY_DIR.iterdir():
            if not directory.is_dir() or directory.is_symlink() or directory.name.startswith("."):
                continue
            try:
                legacy = json.loads((directory / "metadata.json").read_text())
                matches = UUID(legacy["saved_id"]).hex == identity
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if matches:
                directory.rename(LIBRARY_DIR / f".deleted-legacy-{uuid4().hex}")
        (LIBRARY_DIR / f"{identity}.json").unlink(missing_ok=True)


def migrate_legacy(render=None):
    """Copy known per-directory WAV entries to JSON; only remove verified audio.

    Unknown or unreconstructable entries are retained and reported. A WAV is
    removed only after a fresh reconstruction matches its bytes exactly.
    """
    notes = []
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    for directory in LIBRARY_DIR.iterdir():
        if not directory.is_dir() or directory.is_symlink() or directory.name.startswith("."):
            continue
        try:
            original = json.loads((directory / "metadata.json").read_text())
            metadata = original["metadata"]
            validate_metadata(metadata)
            identity = UUID(original["saved_id"]).hex
            record = {"saved_id": identity, "saved_at": original["saved_at"],
                      "source_fingerprint": fingerprint(metadata), "metadata": metadata}
            datetime.fromisoformat(record["saved_at"])
            with locked():
                destination = LIBRARY_DIR / f"{identity}.json"
                if not destination.exists():
                    _atomic_record(record)
                elif json.loads(destination.read_text())["source_fingerprint"] != record["source_fingerprint"]:
                    raise ValueError("Conflicting saved ID; original entry and WAV retained.")
            audio = directory / "audio.wav"
            if audio.exists():
                if render is None:
                    notes.append(f"Legacy entry {directory.name}: audio retained; no reconstruction requested.")
                    continue
                reconstructed = render(metadata)
                if hashlib.sha256(reconstructed).digest() != hashlib.sha256(audio.read_bytes()).digest():
                    raise ValueError("Reconstructed audio differs; legacy WAV retained.")
                audio.unlink()
            # Keep the old JSON as a lightweight backup, not a second entry.
        except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, ImportError) as error:
            notes.append(f"Legacy entry {directory.name}: {error}")
    return notes


STATUSES = ("unreviewed", "saved", "bypassed")
SCHEMA_VERSION = "hsg-ambient-collection-v1"


def now():
    return datetime.now(timezone.utc).isoformat()


def read_record(identity):
    return json.loads((LIBRARY_DIR / f"{UUID(identity).hex}.json").read_text())


def read_batch(identity):
    return json.loads((LIBRARY_DIR / ".batches" / f"{UUID(identity).hex}.json").read_text())


def hydrate(record):
    result = copy.deepcopy(record)
    if record.get("batch_id"):
        batch = read_batch(record["batch_id"])
        for key in ("selection_settings", "rendering"):
            result["metadata"][key] = {**batch["shared"][key], **result["metadata"].get(key, {})}
    result.setdefault("status", "saved")
    result.setdefault("notes", "")
    result.setdefault("favorite", False)
    result.setdefault("status_history", [])
    result.setdefault("latest_decision_at", None)
    result.setdefault("provenance", "legacy_saved" if "record_type" not in record else record["record_type"])
    if result["status"] not in STATUSES:
        raise ValueError("Unknown collection status.")
    return result


def list_saved():
    records, errors = list_records()
    return [r for r in records if r["status"] == "saved"], errors


def _status(record, status):
    if status not in STATUSES:
        raise ValueError("Unknown collection status.")
    if record.get("status", "saved") == status:
        return False
    at = now()
    record.setdefault("notes", "")
    record.setdefault("provenance", "legacy_saved" if "record_type" not in record else record["record_type"])
    record["status"] = status
    if status != "bypassed" and "bypass_reasons" in record:
        record["bypass_reasons"] = {"incoherent_or_multi_emotional":False,"overly_unpleasant":False}
    if status == "saved":
        record["last_saved_at"] = at
        if not record.get("saved_at"):
            record["saved_at"] = at
    record["latest_decision_at"] = at
    record.setdefault("status_history", []).append({"status": status, "at": at})
    return True



def study_usage():
    """Index frozen membership separately from submitted-trial participation."""
    import ambient_study_store as study
    usage, errors = {}, []
    if not study.STUDY_DIR.exists(): return usage, errors
    for path in study.STUDY_DIR.iterdir():
        if not path.is_dir() or path.name.startswith("."): continue
        try:
            manifest = study.read(path / "manifest.json")
            if manifest["session_id"] != path.name: raise ValueError("Invalid study identity")
            try: state = study.read(path / "state.json")
            except (OSError, ValueError): state = {}
            completed, trial_errors = study.trials(path.name)
            errors.extend(trial_errors)
            for item in manifest["inventory"]:
                identity = item["stimulus_id"]
                entry = usage.setdefault(identity, {"studies": [], "trials": 0, "tags": []})
                entry["studies"].append({"id":path.name,"name":state.get("name",manifest.get("initial_name",path.name))})
                entry["trials"] += sum(identity in trial["stimulus_ids"] for trial in completed)
                tag = state.get("stimulus_tags",{}).get(identity)
                if tag and tag not in entry["tags"]: entry["tags"].append(tag)
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"Study {path.name}: {error}")
    return usage, errors


def protect_study_stimulus(identity):
    usage, errors = study_usage()
    if errors: raise ValueError("Study membership could not be fully verified; destructive changes are disabled.")
    if UUID(identity).hex in usage:
        raise ValueError("This stimulus belongs to a relational study and cannot be bypassed, unsaved or deleted.")


def set_tag(identity, tag):
    if not isinstance(tag, str) or len(tag) > 64: raise ValueError("Tags are limited to 64 characters.")
    with locked():
        record = read_record(identity)
        record["tag"] = tag.strip()
        record["tag_updated_at"] = now()
        _atomic_record(record)


BYPASS_REASON_KEYS = ("incoherent_or_multi_emotional", "overly_unpleasant")


def set_status(identity, status, bypass_reasons=None):
    if bypass_reasons is not None and (status != "bypassed" or not isinstance(bypass_reasons,dict)
            or set(bypass_reasons) != set(BYPASS_REASON_KEYS)
            or any(type(value) is not bool for value in bypass_reasons.values())):
        raise ValueError("Bypass reasons must be the two boolean reason flags for a bypassed stimulus.")
    if status != "saved": protect_study_stimulus(identity)
    with locked():
        record = read_record(identity)
        changed = _status(record, status)
        if status == "bypassed":
            reasons = bypass_reasons if bypass_reasons is not None else record.get("bypass_reasons",dict.fromkeys(BYPASS_REASON_KEYS,False))
            reasons_changed = record.get("bypass_reasons") != reasons
            if changed or reasons_changed:
                record["bypass_reasons"] = dict(reasons)
                record["bypass_reasons_updated_at"] = now()
                if not changed:
                    record.setdefault("status_history",[]).append({"status":"bypassed","at":now()})
                record["status_history"][-1]["bypass_reasons"] = dict(reasons)
                changed = True
        if changed: _atomic_record(record)
    return hydrate(record)


def bypass_stimulus(metadata, reasons):
    """Persist an individually bypassed card without a fictitious Save decision."""
    validate_metadata(metadata)
    if (not isinstance(reasons,dict) or set(reasons)!=set(BYPASS_REASON_KEYS)
            or any(type(value) is not bool for value in reasons.values())):
        raise ValueError("Bypass reasons must be two boolean flags.")
    token=fingerprint(metadata)
    with locked():
        records,_=list_records()
        existing=next((record for record in records if record["source_fingerprint"]==token or
                       (record.get("record_type")=="collected" and record["metadata"].get("stimulus_id")==metadata.get("stimulus_id"))),None)
        if existing is None:
            at=now()
            record={"saved_id":uuid4().hex,"saved_at":at,"source_fingerprint":token,"metadata":metadata,
                    "record_type":"manual_saved","schema_version":2,"status":"bypassed","notes":"",
                    "latest_decision_at":at,"bypass_reasons":dict(reasons),"bypass_reasons_updated_at":at,
                    "status_history":[{"status":"bypassed","at":at,"bypass_reasons":dict(reasons)}]}
            _atomic_record(record)
            return hydrate(record)
    return set_status(existing["saved_id"],"bypassed",bypass_reasons=reasons)


def set_favorite(identity, favorite):
    if type(favorite) is not bool: raise ValueError("Favorite must be a boolean.")
    with locked():
        record=read_record(identity)
        record["favorite"]=favorite;record["favorite_updated_at"]=now()
        _atomic_record(record)
    return hydrate(record)


def favorite_stimulus(metadata, favorite):
    """Keep a starred, uncollected card without changing its review decision."""
    validate_metadata(metadata)
    if type(favorite) is not bool: raise ValueError("Favorite must be a boolean.")
    token=fingerprint(metadata)
    with locked():
        records,_=list_records()
        existing=next((r for r in records if r["source_fingerprint"]==token or
                       (r.get("record_type")=="collected" and r["metadata"].get("stimulus_id")==metadata.get("stimulus_id"))),None)
        if existing:
            record=read_record(existing["saved_id"])
        elif favorite:
            at=now()
            record={"saved_id":uuid4().hex,"saved_at":at,"source_fingerprint":token,"metadata":metadata,
                    "record_type":"manual_saved","schema_version":2,"status":"unreviewed","notes":"",
                    "latest_decision_at":None,"status_history":[]}
        else:return None
        record["favorite"]=favorite;record["favorite_updated_at"]=now()
        _atomic_record(record)
        return hydrate(record)


def set_notes(identity, notes):
    with locked():
        record = read_record(identity)
        if record.get("notes", "") != notes:
            record["notes"] = notes
            record["notes_updated_at"] = now()
            _atomic_record(record)


def collection_preference():
    path = LIBRARY_DIR / ".preferences.json"
    if not path.exists():
        return False
    preferences = json.loads(path.read_text())
    if not isinstance(preferences, dict):
        raise ValueError("Invalid Collection Mode preference file.")
    value = preferences.get("collection_mode", False)
    if not isinstance(value, bool):
        raise ValueError("Invalid Collection Mode preference.")
    return value


def set_collection_preference(enabled):
    with locked():
        _atomic_record({"collection_mode": bool(enabled)}, LIBRARY_DIR / ".preferences.json")


def build_info():
    files = ("ambient_app.py", "ambient_harmony.py", "ambient_expanded.py",
             "midi_generator.py", "ambient_audio.py", "ambient_soundfont.py")
    digest = hashlib.sha256()
    for name in files:
        digest.update(name.encode())
        digest.update((Path(__file__).parent / name).read_bytes())
    return {"application": "HSG Ambient", "source_sha256": digest.hexdigest(),
            "reconstruction_schema": SCHEMA_VERSION}


def collect_batch(metadata, batch_id, session_id, generated_at, requested):
    """Commit a complete batch before the UI publishes it. Safe to retry by ID."""
    identity = UUID(batch_id).hex
    if not metadata:
        raise ValueError("Cannot collect an empty batch.")
    for item in metadata:
        validate_metadata(item)
        UUID(item["stimulus_id"])
    shared = {}
    for key in ("selection_settings", "rendering"):
        shared[key] = {k: v for k, v in metadata[0][key].items()
                       if all(item[key].get(k) == v for item in metadata)}
    batch = {"schema_version": SCHEMA_VERSION, "batch_id": identity,
             "generated_at": generated_at, "collection_session_id": session_id,
             "build": build_info(), "source_mode": "Ambient", "requested_settings": requested,
             "shared": shared, "stimulus_ids": [UUID(m["stimulus_id"]).hex for m in metadata],
             "reconstruction_requirements": "Exact event data plus matching renderer version and SoundFont SHA-256 where applicable",
             "rng_seed": None, "rng_note": "No seed captured; exact realized events are authoritative.",
             "committed": False}
    with locked():
        destination = LIBRARY_DIR / ".batches" / f"{identity}.json"
        if destination.exists() and read_batch(identity).get("committed"):
            old = read_batch(identity)
            if (old["stimulus_ids"] != batch["stimulus_ids"] or
                    any(read_record(UUID(item["stimulus_id"]).hex)["source_fingerprint"] != fingerprint(item)
                        for item in metadata)):
                raise ValueError("Batch ID already refers to different stimuli.")
            return
        _atomic_record(batch, destination)
        for item in metadata:
            saved_id = UUID(item["stimulus_id"]).hex
            record_path = LIBRARY_DIR / f"{saved_id}.json"
            if record_path.exists():
                existing = read_record(saved_id)
                if existing.get("source_fingerprint") != fingerprint(item):
                    raise ValueError("Stimulus ID collision; existing record retained.")
                continue
            realized = copy.deepcopy(item)
            for key in shared:
                realized[key] = {k: v for k, v in realized[key].items() if k not in shared[key]}
            record = {"saved_id": saved_id, "stimulus_id": saved_id, "batch_id": identity,
                      "generated_at": item["created_at"], "collection_session_id": session_id,
                      "record_type": "collected", "schema_version": SCHEMA_VERSION,
                      "saved_at": None, "status": "unreviewed", "latest_decision_at": None,
                      "notes": "", "status_history": [{"status": "unreviewed", "at": item["created_at"]}],
                      "source_fingerprint": fingerprint(item),
                      "metadata": realized}
            _atomic_record(record)
        batch["committed"] = True
        _atomic_record(batch, destination)


def export_collection():
    # Snapshot under the same lock used by batch commits and decisions.
    with locked():
        return _export_collection()


def _export_collection():
    records, errors = list_records()
    batches = {}
    for record in records:
        if record.get("batch_id"):
            batches[record["batch_id"]] = read_batch(record["batch_id"])
    # Export compact authoritative disk records; legacy metadata stays standalone.
    stimuli = []
    for record in records:
        raw = read_record(record["saved_id"])
        for key in ("status", "notes", "status_history", "latest_decision_at", "provenance", "favorite"):
            raw.setdefault(key, record[key])
        stimuli.append(raw)
    return {"export_schema_version": SCHEMA_VERSION, "exported_at": now(),
            "application": build_info(), "ordering": "generation timestamp; legacy save timestamp",
            "batches": list(batches.values()), "stimuli": stimuli,
            "unreadable_entries": [{"file": name, "error": error} for name, error in errors]}
