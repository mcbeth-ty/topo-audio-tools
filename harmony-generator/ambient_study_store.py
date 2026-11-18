"""Small JSON study store: frozen inventories, immutable trials, mutable drafts."""

from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import combinations
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import tempfile
from uuid import UUID, uuid4

from ambient_library import validate_metadata, build_info

STUDY_DIR = Path(__file__).parent / "data" / "ambient_studies"
SCHEMA = "hsg-relational-study-v1"
CLASSIFICATION = "virtual-1000x600-v1"
SCHEDULER = "coverage-context-disagreement-v1"
COVERAGE_SCHEDULER = "coverage-first-exhaustive-v1"
SCHEDULING_MODES = ("Coverage First", "Adaptive")
SETTINGS = {"canvas": {"width": 1000, "height": 600, "margin": 50},
            "distance_thresholds": [0.10, 0.23, 0.40],
            "distance_normalization": "Euclidean virtual distance / 1000",
            "categories": {"0": "Unrelated", "1": "Weakly related", "2": "Moderately related", "3": "Strongly related"},
            "category_descriptions": {"0": "No meaningful perceived emotional relationship",
                                      "1": "Some shared emotional character", "2": "A clear emotional relationship",
                                      "3": "Very similar emotional character"},
            "scheduler": {"version": SCHEDULER, "candidate_limit": 600,
                          "weights": {"unobserved": 8, "undermeasured": 3,
                                      "disagreement": 1, "exposure_penalty": .15,
                                      "same_group_penalty": 6, "random_jitter": 1, "uncertain_discount": .5}},
            "analysis": {"version": "observed-weighted-nonmetric-smacof-v1", "seed": 1729,
                         "starts": 4, "max_iterations": 200, "tolerance": 1e-6,
                         "aggregation": "lower ordinal median; ties share disparities",
                         "weight": "min(valid observation count, 3)",
                         "minimum_pair_coverage": .35, "minimum_degree": 3,
                         "minimum_edges": "max(3*N-6, ceil(.35*possible_pairs))",
                         "connectivity": "connected after removal of any zero, one or two vertices"}}


def now():
    return datetime.now(timezone.utc).isoformat()


def folder(identity):
    return STUDY_DIR / UUID(identity).hex


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(value, target, ensure_ascii=False, allow_nan=False, indent=2)
            target.flush(); os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def locked(identity):
    with (folder(identity) / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def initial_stimulus_tags(records):
    """Snapshot library tags, falling back to the newest prior study annotation."""
    wanted={r["saved_id"] for r in records}
    prior=[]
    if STUDY_DIR.exists():
        for path in STUDY_DIR.iterdir():
            if not path.is_dir() or path.name.startswith("."):continue
            try:
                manifest=read(path/"manifest.json");state=read(path/"state.json")
                prior.append((manifest.get("created_at",""),path.name,state.get("stimulus_tags",{})))
            except (OSError,ValueError,KeyError,TypeError):continue
    inherited={}
    for _,_,tags in sorted(prior,reverse=True):
        for identity,text in tags.items():
            if identity in wanted and identity not in inherited and isinstance(text,str) and text.strip():
                inherited[identity]=text.strip()[:64]
    for record in records:
        text=record.get("tag")
        if isinstance(text,str) and text.strip():inherited[record["saved_id"]]=text.strip()[:64]
    return inherited


def create_session(name, records, policy, inventory_selection=None):
    if not name.strip() or not 10 <= len(records) <= 40 or policy not in ("Exploratory", "Feedback Hidden"):
        raise ValueError("Name the session and select 10–40 Saved stimuli and a feedback policy.")
    ids = [record["saved_id"] for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Session stimuli must be unique.")
    for record in records:
        validate_metadata(record["metadata"])
    identity = uuid4().hex
    study_source = hashlib.sha256()
    for source_name in ("ambient_study_store.py", "ambient_study_analysis.py", "ambient_study.py",
                        "ambient_frontend/study.js", "ambient_frontend/study.css"):
        study_source.update(source_name.encode()); study_source.update((Path(__file__).parent / source_name).read_bytes())
    manifest = {"schema_version": SCHEMA, "session_id": identity, "created_at": now(),
                "initial_name": name.strip(), "build": {**build_info(), "study_source_sha256": study_source.hexdigest()}, "settings": copy.deepcopy(SETTINGS),
                "feedback_policy": policy,
                "inventory": [{"stimulus_id": r["saved_id"], "metadata": copy.deepcopy(r["metadata"]),
                               "source_saved_at": r.get("saved_at"), "source_provenance": r.get("provenance")}
                              for r in records]}
    if inventory_selection is not None:
        manifest["inventory_selection"]=copy.deepcopy(inventory_selection)
    state = {"name": name.strip(), "updated_at": now(), "view": "Arrange",
             "scheduler_seed": random.SystemRandom().getrandbits(64), "scheduling_mode": "Coverage First",
             "revealed_at": None, "collection_closed": False, "exposures": [], "view_token": uuid4().hex,
             "stimulus_tags":initial_stimulus_tags(records)}
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".creating-", dir=STUDY_DIR))
    try:
        atomic(temporary / "manifest.json", manifest)
        atomic(temporary / "state.json", state)
        temporary.rename(folder(identity))
    finally:
        if temporary.exists():
            for path in temporary.iterdir(): path.unlink()
            temporary.rmdir()
    return identity


def load_session(identity):
    manifest, state = read(folder(identity) / "manifest.json"), read(folder(identity) / "state.json")
    if manifest["session_id"] != UUID(identity).hex or manifest["schema_version"] != SCHEMA:
        raise ValueError("Unsupported or inconsistent session manifest.")
    state.setdefault("scheduling_mode","Coverage First")
    return manifest, state


def list_sessions():
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    sessions, errors = [], []
    for path in STUDY_DIR.iterdir():
        if path.is_dir() and not path.name.startswith("."):
            try:
                manifest, state = load_session(path.name)
                sessions.append({"session_id": path.name, "name": state["name"], "created_at": manifest["created_at"]})
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append(f"{path.name}: {error}")
    return sorted(sessions, key=lambda s: s["created_at"], reverse=True), errors


def update_state(identity, **changes):
    if not set(changes) <= {"name", "view", "scheduling_mode"}:
        raise ValueError("Only name, navigation and scheduling mode are directly editable.")
    with locked(identity):
        manifest, state = load_session(identity)
        if "scheduling_mode" in changes and changes["scheduling_mode"] not in SCHEDULING_MODES:
            raise ValueError("Unknown scheduling mode.")
        if "name" in changes and not changes["name"].strip(): raise ValueError("Session name cannot be empty.")
        if "view" in changes:
            if changes["view"] not in ("Arrange", "Explore"): raise ValueError("Invalid view.")
            if changes["view"] == "Explore" and manifest["feedback_policy"] == "Feedback Hidden" and not state["revealed_at"]:
                raise ValueError("Explore is locked by the fixed feedback policy.")
            if changes["view"] != state["view"]: state["view_token"] = uuid4().hex
        state.update(changes); state["updated_at"] = now()
        atomic(folder(identity) / "state.json", state)


def set_stimulus_tag(identity, stimulus_id, text):
    """Personal annotations, separate from frozen stimuli and submitted evidence."""
    if not isinstance(text, str) or len(text) > 64:
        raise ValueError("Tags must contain at most 64 characters.")
    text = " ".join(text.split())
    with locked(identity):
        manifest, state = load_session(identity)
        if stimulus_id not in {item["stimulus_id"] for item in manifest["inventory"]}:
            raise ValueError("Unknown stimulus for this study.")
        tags = state.setdefault("stimulus_tags", {})
        if text: tags[stimulus_id] = text
        else: tags.pop(stimulus_id, None)
        state["updated_at"] = now()
        atomic(folder(identity) / "state.json", state)


def reveal(identity):
    with locked(identity):
        manifest, state = load_session(identity)
        if manifest["feedback_policy"] != "Feedback Hidden": raise ValueError("This session already permits feedback.")
        if not state["revealed_at"]:
            state["revealed_at"] = now(); state["collection_closed"] = True; state["view"] = "Explore"
            state["view_token"] = uuid4().hex
            state["exposures"].append({"kind": "feedback_unlocked_collection_closed", "at": now()})
            atomic(folder(identity) / "state.json", state)


def exposure(identity, kind, token):
    with locked(identity):
        manifest, state = load_session(identity)
        if manifest["feedback_policy"] == "Feedback Hidden" and not state["revealed_at"]:
            return
        if not any(e.get("token") == token and e["kind"] == kind for e in state["exposures"]):
            state["exposures"].append({"kind": kind, "token": token, "at": now()})
            atomic(folder(identity) / "state.json", state)


def trials(identity):
    rows, errors = [], []
    for path in (folder(identity) / "trials").glob("*.json"):
        try:
            trial = read(path)
            if trial["session_id"] != UUID(identity).hex or trial["trial_id"] != path.stem or len(trial["pairs"]) != 6:
                raise ValueError("Invalid trial identity or relationships.")
            ids = trial["stimulus_ids"]
            expected = {pair_key(a,b) for a,b in combinations(ids,2)}
            if (len(ids)!=4 or len(set(ids))!=4 or {pair_key(*p["ids"]) for p in trial["pairs"]}!=expected
                    or any(p["submitted"] is not None and (type(p["submitted"]) is not int or not 0<=p["submitted"]<=3) for p in trial["pairs"])):
                raise ValueError("Invalid trial pair judgments.")
            rows.append(trial)
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"{path.name}: {error}")
    return sorted(rows, key=lambda t: t["sequence"]), errors


def pair_key(a, b):
    return "|".join(sorted((a, b)))


def summarize(manifest, completed):
    ids = [item["stimulus_id"] for item in manifest["inventory"]]
    pairs = {pair_key(a, b): {"ids": [a, b], "counts": [0, 0, 0, 0], "valid_count": 0,
                             "uncertain_count": 0, "history": []} for a, b in combinations(ids, 2)}
    exposures = {identity: 0 for identity in ids}
    for trial in completed:
        for identity in trial["stimulus_ids"]: exposures[identity] += 1
        for observation in trial["pairs"]:
            pair = pairs[pair_key(*observation["ids"])]
            value = observation["submitted"]
            pair["history"].append({"trial_id": trial["trial_id"], "sequence": trial["sequence"],
                                    "value": value, "at": trial["submitted_at"], "context": trial["stimulus_ids"]})
            if value is None: pair["uncertain_count"] += 1
            else: pair["counts"][value] += 1; pair["valid_count"] += 1
    for pair in pairs.values():
        ordered = [category for category, n in enumerate(pair["counts"]) for _ in range(n)]
        pair["relatedness"] = ordered[(len(ordered) - 1) // 2] if ordered else None
        pair["disagreement"] = 1 - max(pair["counts"]) / len(ordered) if ordered else None
    repetitions = {}
    for pair in pairs.values(): repetitions[str(pair["valid_count"])] = repetitions.get(str(pair["valid_count"]), 0) + 1
    repeated = [p["disagreement"] for p in pairs.values() if p["valid_count"] >= 2]
    observed = sum(p["valid_count"] > 0 for p in pairs.values())
    return {"pairs": pairs, "stimulus_exposures": exposures, "completed_trials": len(completed),
            "possible_pairs": len(pairs), "observed_pairs": observed, "coverage": observed / len(pairs),
            "unobserved_pairs": len(pairs) - observed, "repetitions": repetitions,
            "uncertain_responses": sum(p["uncertain_count"] for p in pairs.values()),
            "repeated_pair_disagreement": sum(repeated) / len(repeated) if repeated else None}


def _schedule_adaptive(manifest, state, completed):
    ids = sorted(item["stimulus_id"] for item in manifest["inventory"])
    sequence = max((t["sequence"] for t in completed), default=0) + 1
    seed = f"{state['scheduler_seed']}:{sequence}:{SCHEDULER}"
    rng = random.Random(seed)
    summary = summarize(manifest, completed)
    groups = list(combinations(ids, 4))
    limit = manifest["settings"]["scheduler"]["candidate_limit"]
    if len(groups) > limit: groups = rng.sample(groups, limit)
    previous = [set(t["stimulus_ids"]) for t in completed]
    weights = manifest["settings"]["scheduler"]["weights"]
    def score(group):
        pairs = [summary["pairs"][pair_key(a, b)] for a, b in combinations(group, 2)]
        return (sum(weights["unobserved"] * (p["valid_count"] == 0) / (1 + weights["uncertain_discount"] * p["uncertain_count"])
                    + weights["undermeasured"] / (1 + p["valid_count"])
                    + weights["disagreement"] * (p["disagreement"] or 0) for p in pairs)
                - weights["exposure_penalty"] * sum(summary["stimulus_exposures"][i] for i in group)
                - weights["same_group_penalty"] * sum(set(group) == old for old in previous)
                + rng.random() * weights["random_jitter"])
    chosen = max(groups, key=score)
    order = list(chosen); rng.shuffle(order)
    corners = [(0.12, .15), (.88, .15), (.12, .85), (.88, .85)]
    rng.shuffle(corners)
    positions = {identity: {"x": xy[0], "y": xy[1]} for identity, xy in zip(order, corners)}
    return {"trial_id": uuid4().hex, "session_id": manifest["session_id"], "sequence": sequence,
            "stimulus_ids": list(chosen), "presentation_order": order, "initial_positions": positions,
            "positions": copy.deepcopy(positions), "overrides": {},
            "interactions": {identity: {"moved": False, "auditioned": False, "considered": False} for identity in chosen},
            "confirmed": False, "revision": 0, "started_at": now(),
            "scheduler": {"version": SCHEDULER, "seed": seed, "candidate_count": len(groups),
                          "selected_subset": list(chosen), "parameters": manifest["settings"]["scheduler"]},
            "classification_version": CLASSIFICATION}


def new_pair_count(stimulus_ids, summary):
    """Distinct pairs lacking valid submitted ordinal evidence; drafts never count."""
    return sum(summary["pairs"][key]["valid_count"]==0
               for key in {pair_key(a,b) for a,b in combinations(stimulus_ids,2)})


def schedule(manifest, state, completed):
    mode=state.get("scheduling_mode","Coverage First")
    if mode not in SCHEDULING_MODES:raise ValueError("Unknown scheduling mode.")
    summary=summarize(manifest,completed)
    if mode=="Adaptive" or summary["unobserved_pairs"]==0:
        pending=_schedule_adaptive(manifest,state,completed)
        pending["scheduler"].update(requested_mode=mode,effective_mode="Adaptive",
                                    first_pass_complete=summary["unobserved_pairs"]==0,
                                    new_pair_count=new_pair_count(pending["stimulus_ids"],summary))
        return pending
    ids=sorted(item["stimulus_id"] for item in manifest["inventory"])
    sequence=max((t["sequence"] for t in completed),default=0)+1
    seed=f"{state['scheduler_seed']}:{sequence}:{COVERAGE_SCHEDULER}"
    rng=random.Random(seed)
    groups=list(combinations(ids,4))
    previous={}
    for trial in completed:
        group=tuple(sorted(trial["stimulus_ids"]))
        previous[group]=previous.get(group,0)+1
    def score(group):
        # Lexicographic comparison makes the new-pair count inviolable.
        return (new_pair_count(group,summary),
                -sum(summary["stimulus_exposures"][i] for i in group),
                -previous.get(group,0),rng.random())
    chosen=max(groups,key=score)
    order=list(chosen);rng.shuffle(order)
    corners=[(.12,.15),(.88,.15),(.12,.85),(.88,.85)];rng.shuffle(corners)
    positions={identity:{"x":xy[0],"y":xy[1]} for identity,xy in zip(order,corners)}
    return {"trial_id":uuid4().hex,"session_id":manifest["session_id"],"sequence":sequence,
            "stimulus_ids":list(chosen),"presentation_order":order,"initial_positions":positions,
            "positions":copy.deepcopy(positions),"overrides":{},
            "interactions":{identity:{"moved":False,"auditioned":False,"considered":False} for identity in chosen},
            "confirmed":False,"revision":0,"started_at":now(),
            "scheduler":{"version":COVERAGE_SCHEDULER,"seed":seed,"candidate_count":len(groups),
                         "selected_subset":list(chosen),"requested_mode":mode,"effective_mode":"Coverage First",
                         "new_pair_count":new_pair_count(chosen,summary),"first_pass_complete":False,
                         "parameters":{"exhaustive":True,"priority":["maximum new pairs","minimum total stimulus exposure","minimum identical quartet repetitions","seeded random tie-break"]}},
            "classification_version":CLASSIFICATION}


def ensure_pending(identity):
    with locked(identity):
        manifest, state = load_session(identity)
        path = folder(identity) / "pending.json"
        if path.exists():
            pending = read(path)
            if not (folder(identity) / "trials" / f"{UUID(pending['trial_id']).hex}.json").exists():
                return pending
            path.unlink()  # recover a crash between immutable commit and draft removal
        if state["collection_closed"]: return None
        completed, errors = trials(identity)
        if errors: raise ValueError("Repair unreadable trial files before scheduling; they were retained.")
        pending = schedule(manifest, state, completed)
        atomic(path, pending)
        return pending


def validate_draft(pending, payload):
    ids = pending["stimulus_ids"]
    if len(ids) != 4 or len(set(ids)) != 4 or payload.get("trial_id") != pending["trial_id"]:
        raise ValueError("The trial identity changed; reopen the active trial.")
    if set(payload["positions"]) != set(ids): raise ValueError("Four node positions are required.")
    for point in payload["positions"].values():
        if (set(point) != {"x", "y"} or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in point.values())
                or not .05 <= point["x"] <= .95 or not 50/600 <= point["y"] <= 550/600):
            raise ValueError("Node coordinates are outside the fixed virtual canvas.")
    keys = {pair_key(a, b) for a, b in combinations(ids, 2)}
    if not set(payload.get("overrides", {})) <= keys: raise ValueError("Unknown pair override.")
    for value in payload.get("overrides", {}).values():
        if not (type(value) is int and 0 <= value <= 3) and value != "uncertain":
            raise ValueError("Overrides must be 0–3 or Unable to judge.")
    if set(payload.get("interactions", {})) != set(ids): raise ValueError("Missing interaction indicators.")
    if type(payload.get("confirmed")) is not bool: raise ValueError("Invalid completion confirmation.")
    if type(payload.get("revision")) is not int or payload["revision"] < 1: raise ValueError("Invalid draft revision.")


def _update_pending(identity, payload):
    pending = read(folder(identity) / "pending.json")
    validate_draft(pending, payload)
    if payload["revision"] <= pending["revision"]: return pending
    pending["positions"] = copy.deepcopy(payload["positions"])
    pending["overrides"] = copy.deepcopy(payload.get("overrides", {}))
    for node in pending["stimulus_ids"]:
        for action in ("moved", "auditioned", "considered"):
            if type(payload["interactions"][node].get(action)) is not bool: raise ValueError("Invalid interaction flag.")
            pending["interactions"][node][action] |= payload["interactions"][node][action]
    pending["confirmed"] = payload["confirmed"]; pending["revision"] = payload["revision"]
    pending["updated_at"] = now()
    atomic(folder(identity) / "pending.json", pending)
    return pending


def update_pending(identity, payload):
    with locked(identity):
        return _update_pending(identity,payload)


def inferred_category(a, b, settings=SETTINGS):
    distance = math.hypot((a["x"] - b["x"]) * 1000, (a["y"] - b["y"]) * 600) / 1000
    thresholds = settings["distance_thresholds"]
    return distance, 3 if distance <= thresholds[0] else 2 if distance <= thresholds[1] else 1 if distance <= thresholds[2] else 0


def submit(identity, payload):
    # Update is separately atomic so the last explicit response survives a failed submit.
    trial_id = UUID(payload["trial_id"]).hex
    path = folder(identity) / "trials" / f"{trial_id}.json"
    with locked(identity):
        if path.exists(): return read(path)
        current = read(folder(identity) / "pending.json")
        if payload["revision"] < current["revision"]:
            raise ValueError("A newer draft exists. Reopen the current arrangement before submitting.")
        _update_pending(identity,payload)
        manifest, state = load_session(identity)
        if state["collection_closed"]: raise ValueError("Feedback was revealed; collection is closed for this session.")
        pending = read(folder(identity) / "pending.json")
        inventory = {item["stimulus_id"] for item in manifest["inventory"]}
        if (not set(pending["stimulus_ids"]) <= inventory or
                set(pending["presentation_order"]) != set(pending["stimulus_ids"]) or
                len(pending["presentation_order"]) != 4):
            raise ValueError("Trial stimuli must belong to the frozen session inventory.")
        if pending["trial_id"] != trial_id: raise ValueError("This is not the active trial.")
        if not pending["confirmed"] and not all(any(flags.values()) for flags in pending["interactions"].values()):
            raise ValueError("Consider all four stimuli or explicitly confirm the final arrangement before submitting.")
        observations = []
        for a, b in combinations(pending["stimulus_ids"], 2):
            key = pair_key(a, b)
            distance, inferred = inferred_category(pending["positions"][a], pending["positions"][b], manifest["settings"])
            override = pending["overrides"].get(key)
            observations.append({"ids": sorted((a, b)), "distance": distance, "inferred": inferred,
                                 "override": override, "uncertain": override == "uncertain",
                                 "submitted": None if override == "uncertain" else override if override is not None else inferred})
        completed = {**pending, "submitted_at": now(), "pairs": observations,
                     "final_positions": copy.deepcopy(pending["positions"]),
                     "virtual_positions": {i: {"x": p["x"]*1000, "y": p["y"]*600} for i, p in pending["positions"].items()},
                     "feedback_policy": manifest["feedback_policy"], "feedback_revealed_at": state["revealed_at"],
                     "settings": manifest["settings"], "schema_version": SCHEMA}
        atomic(path, completed)
        (folder(identity) / "pending.json").unlink(missing_ok=True)
        return completed


def export_session(identity):
    with locked(identity):
        manifest, state = load_session(identity)
        completed, errors = trials(identity)
        pending = read(folder(identity) / "pending.json") if (folder(identity) / "pending.json").exists() else None
        derived = read(folder(identity) / "analysis.json") if (folder(identity) / "analysis.json").exists() else None
        if derived:
            digest = hashlib.sha256(json.dumps([derived["model_version"],manifest["settings"]["analysis"],completed],sort_keys=True).encode()).hexdigest()
            derived = {**derived, "n_components":derived.get("n_components",2), "stale": derived["input_hash"] != digest}
        additional = None
        path3 = folder(identity) / "analysis_3d.json"
        if path3.exists():
            try:
                additional = read(path3)
                digest3 = hashlib.sha256(json.dumps([additional["model_version"],manifest["settings"]["analysis"],completed,3],sort_keys=True).encode()).hexdigest()
                additional = {**additional,"stale":additional["input_hash"] != digest3}
            except (OSError,ValueError,KeyError,TypeError):
                additional = {"derived":True,"n_components":3,"status":"Unreadable derived cache; can be regenerated"}
        additional4 = None
        path4 = folder(identity) / "analysis_4d.json"
        if path4.exists():
            try:
                additional4 = read(path4)
                digest4 = hashlib.sha256(json.dumps([additional4["model_version"],manifest["settings"]["analysis"],completed,4],sort_keys=True).encode()).hexdigest()
                additional4 = {**additional4,"stale":additional4["input_hash"] != digest4}
            except (OSError,ValueError,KeyError,TypeError):
                additional4 = {"derived":True,"n_components":4,"status":"Unreadable derived cache; can be regenerated"}
        affinity = {}
        for dimension in (2,3,4):
            path = folder(identity)/f"analysis_affinity_{dimension}d.json"
            if path.exists():
                try:
                    from ambient_study_affinity import fingerprint
                    result = read(path)
                    digest = fingerprint(identity,manifest["settings"]["analysis"],completed,dimension,result["parameters"])
                    affinity[f"{dimension}D"] = {**result,"stale":result["input_hash"] != digest}
                except (OSError,ValueError,KeyError,TypeError):
                    affinity[f"{dimension}D"] = {"derived":True,"status":"Unreadable derived cache; can be regenerated"}
        return {**({"derived_analysis_4d":additional4} if additional4 is not None else {}),**({"derived_affinity":affinity} if affinity else {}),**({"derived_analysis_3d":additional} if additional is not None else {}), "export_schema_version": SCHEMA, "exported_at": now(), "manifest": manifest,
                "operational_state": state, "pending_trial": pending, "submitted_trials": completed,
                "pair_summaries": summarize(manifest, completed), "derived_analysis": derived,
                "unreadable_trials": errors}
