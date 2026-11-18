"""Ambient-only browser playback and arrangement, using existing rendered media."""

import hashlib
import json
from pathlib import Path

import streamlit as st
from streamlit import runtime
from streamlit.components.v2 import component

_ASSETS = Path(__file__).with_name("ambient_frontend")
_frontend = component("ambient_audition", html='<div class="ambient-root"></div>',
                      js=(_ASSETS / "audition.js").read_text(),
                      css=(_ASSETS / "audition.css").read_text())


def stimulus_id(stimulus, index):
    return stimulus.get("stimulus_id") or f"legacy-{index}-{stimulus['created_at']}"


def playback_scope(batch, view, settings):
    batch_id = hashlib.sha256(json.dumps([
        stimulus_id(stimulus, index) for index, stimulus in enumerate(batch)
    ]).encode()).hexdigest()
    epoch = hashlib.sha256(json.dumps([batch_id, view, settings], default=str).encode()).hexdigest()
    _frontend(key="ambient_playback_scope", data={"kind": "scope", "epoch": epoch}, height=0)
    return batch_id, epoch


def audio_url(wav, identity):
    # Streamlit's session-managed media store serves one content-addressed URL.
    # The component receives URLs, never base64 WAVs or pointer-event payloads.
    if not runtime.exists():
        return ""
    return runtime.get_instance().media_file_mgr.add(wav, "audio/wav", f"ambient/audio/{identity}")


def render_player(wav, identity, epoch, compact=False, play_request=None, preview_seconds=None):
    _frontend(key=f"ambient_player_{identity}",
              data={"kind": "player", "id": identity, "url": audio_url(wav, identity), "epoch": epoch, "compact": compact, "play_request": play_request, "preview_seconds":preview_seconds},
              height=32 if preview_seconds is not None else 38 if compact else 58)


def render_arrangement(stimuli, batch_id, epoch, on_save=None, saved_tokens=(), on_bypass=None, records=None):
    from ambient_library import fingerprint
    items = []
    for index, (metadata, wav) in enumerate(stimuli):
        identity = stimulus_id(metadata, index)
        audio = metadata["rendering"]
        record = (records or {}).get(identity)
        items.append({
            "id": identity, "number": index + 1, "url": audio_url(wav, identity),
            "save_token": fingerprint(metadata),
            "saved": record["status"] == "saved" if record else fingerprint(metadata) in saved_tokens,
            "status": record["status"] if record else None,
            "can_bypass": bool(record),
            "label": metadata["chord"]["display_label"],
            "family": metadata["chord"].get("harmonic_family", "Triadic"),
            "states": [{"notes": state["notes_names"], "midi": state["notes_midi"],
                        "time": state["start_seconds"],
                        "movement": [{"voice": voice["voice_id"] + 1,
                                      "semitones": voice["displacement_semitones"]}
                                     for voice in state["voices"] if voice["displacement_semitones"]]}
                       for state in metadata["states"]],
            "duration": audio["duration_seconds"], "preset": audio["timbre"],
            "reverb": audio["reverb"], "level": audio["effect_level"],
        })
    # The callback captures the exact metadata displayed before the click; no
    # chord selection or audio rendering is needed to persist it.
    snapshots = {fingerprint(metadata): metadata for metadata, _ in stimuli}
    def handle_save():
        event = st.session_state.get("ambient_arrangement", {}).get("save")
        if on_save and isinstance(event, dict) and event.get("token") in snapshots:
            on_save(snapshots[event["token"]])
    def handle_bypass():
        event = st.session_state.get("ambient_arrangement", {}).get("bypass")
        if on_bypass and isinstance(event, dict) and event.get("token") in snapshots:
            on_bypass(snapshots[event["token"]])
    _frontend(key="ambient_arrangement", data={"kind": "arrange", "batch": batch_id,
                                              "epoch": epoch, "items": items}, height="content",
              on_save_change=handle_save, on_bypass_change=handle_bypass)
