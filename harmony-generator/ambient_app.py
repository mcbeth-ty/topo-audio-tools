"""Full-application-only Ambient controls and harmonic-state generation."""

import copy
import io
import json
import math
import wave
import os
import random
from uuid import uuid4, uuid5, NAMESPACE_URL
from datetime import datetime, timezone

import streamlit as st

from ambient_audio import RENDERER_VERSION, SAMPLE_RATE, TIMBRES, TRANSITION_SECONDS, render_states_wav
from midi_generator import build_chord, build_probability_field
from ambient_harmony import build_states, time_states
from ambient_chord_targeting import RELATIONSHIPS, QUALITY_BALANCES, generate_targeted
from ambient_expanded import FAMILIES, generate_expanded, generate_chromatic_basic, framework_description
from ambient_playback import playback_scope, render_player, render_arrangement, stimulus_id
import ambient_library as saved_library
from ambient_saved import render_saved, save_action, save_control, bypass_action, render_detail, close_detail, open_detail, record_for
from ambient_soundfont import (
    RENDERER_VERSION as SOUNDFONT_VERSION, REVERB_SETTINGS, SETUP,
    TAIL_THRESHOLD_DBFS, MIN_RELEASE_SECONDS, MAX_TAIL_SECONDS,
    SoundFontUnavailable, fluid_module, soundfont_identity, available_presets,
    render_soundfont_wav,
)


@st.cache_data(max_entries=8, show_spinner=False)
def cached_audio(states, duration, timbre, reverb, renderer_version,
                 soundfont=None, program=None, reverb_mode="Dry", effect_level=0.0):
    # Musical content and every effective audio setting are explicit cache keys.
    if soundfont is not None:
        return render_soundfont_wav(states, duration, soundfont, program,
                                    reverb_mode, effect_level)
    return render_states_wav(states, duration, timbre, reverb)


def generate_sonority(tonic, mode, register_low, register_high):
    if register_low > register_high:
        raise ValueError("Register low must be at or below register high.")
    field = build_probability_field(mode, 100, 0, 0, 0)
    # The legacy bounds select roots only. Restrict candidates here so the
    # complete root-position triad fits within Ambient's displayed register.
    for item in field:
        span = max(item["triad_intervals_from_root"])
        fits = any(
            note % 12 == (tonic + item["root_semitone"]) % 12
            for note in range(register_low, register_high - span + 1)
        )
        if not fits:
            item["weight"] = 0
    if not any(item["weight"] > 0 for item in field):
        raise ValueError("This register cannot contain an active triad. Widen it.")
    # Keep root selection inside the range for the widest supported triad.
    # Each candidate uses its own legal root range, preserving legacy builders.
    import random

    source = random.choices(field, weights=[item["weight"] for item in field])[0]
    span = max(source["triad_intervals_from_root"])
    chord = build_chord(
        tonic, register_low, register_high - span, [source], [0, 100], [100, 0, 0]
    )
    chord["root_pitch_class"] = chord["root_note_midi"] % 12
    chord["sonority_type"] = f"{chord['intended_quality']} triad"
    return {
        "generation_mode": "ambient", "generation_framework": "diatonic",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_settings": {
            "harmonic_vocabulary": "Basic", "generation_framework": "diatonic",
            "tonic_midi": tonic, "modal_preset": mode,
            "register_low": register_low, "register_high": register_high,
            "field_weights": {"diatonic": 100, "parallel_borrowing": 0,
                              "uncommon_1": 0, "uncommon_2": 0},
            "chord_type_weights": [0, 100], "inversion_weights": [100, 0, 0],
        },
        "chord": chord,
    }


def harmonic_state_distribution(weights):
    if (not isinstance(weights,(tuple,list)) or len(weights)!=3
            or any(type(w) not in (int,float) or not math.isfinite(w) or w<0 for w in weights)):
        raise ValueError("Provide three finite, nonnegative harmonic-state weights.")
    total=sum(weights)
    if not math.isfinite(total) or total<=0:raise ValueError("At least one harmonic-state weight must be greater than zero.")
    return tuple(w/total for w in weights)


def generate_batch(batch_size, tonic, mode, low, high, state_count,
                   maximum_voices_moved, maximum_movement, vocabulary="Basic", voice_count=4, family="All",
                   hold_bass_note=False, generation_framework="diatonic", state_weights=None,
                   harmonic_relationship="Mixed", chord_quality_balance="Balanced"):
    probabilities=harmonic_state_distribution(state_weights) if state_weights is not None else None
    if probabilities is not None:state_count=max(i+1 for i,w in enumerate(state_weights) if w>0)
    if generation_framework not in ("diatonic", "chromatic", "chord_targeting"):
        raise ValueError("Choose Diatonic, Chromatic or Chord Targeting generation.")
    if vocabulary not in ("Basic", "Expanded"):
        raise ValueError("Choose Basic or Expanded vocabulary.")
    if batch_size not in (4, 6, 8):
        raise ValueError("Choose a batch of four, six, or eight stimuli.")
    if state_count not in (1, 2, 3):
        raise ValueError("Maximum harmonic states must be one, two, or three.")
    if vocabulary == "Expanded":
        voice_min, voice_max = voice_count if isinstance(voice_count, (tuple, list)) else (voice_count, voice_count)
        if (type(voice_min) is not int or type(voice_max) is not int
                or not 2 <= voice_min <= voice_max <= 5):
            raise ValueError("Choose an ordered voice-count range within two to five voices.")
    state_rng = random.Random()
    batch = []
    for _ in range(batch_size):
        if generation_framework == "chord_targeting":
            actual_voice_count = (state_rng.randint(voice_min,voice_max) if voice_min != voice_max else voice_min) if vocabulary == "Expanded" else 3
            actual_state_count = (state_rng.choices((1,2,3),weights=state_weights,k=1)[0]
                                  if state_weights is not None else state_rng.randint(1,state_count))
            stimulus=generate_targeted(low,high,vocabulary,actual_voice_count,family,actual_state_count,
                                      maximum_voices_moved,maximum_movement,hold_bass_note,
                                      relationship=harmonic_relationship,balance=chord_quality_balance)
        else:
            if vocabulary == "Basic":
                stimulus = (generate_chromatic_basic(low, high) if generation_framework == "chromatic"
                            else generate_sonority(tonic, mode, low, high))
            else:
                actual_voice_count = state_rng.randint(voice_min, voice_max) if voice_min != voice_max else voice_min
                stimulus = generate_expanded(tonic, mode, low, high, actual_voice_count, family,
                                             generation_framework=generation_framework)
            actual_state_count = (state_rng.choices((1,2,3),weights=state_weights,k=1)[0]
                                  if state_weights is not None else state_rng.randint(1, state_count))
            stimulus["states"] = build_states(
                stimulus["chord"]["notes_midi"], actual_state_count,
                maximum_voices_moved, maximum_movement, low, high, hold_bass_note=hold_bass_note
            )
        if vocabulary == "Expanded":
            stimulus["selection_settings"].update(minimum_voice_count=voice_min, maximum_voice_count=voice_max)
        stimulus["generation_framework"] = generation_framework
        stimulus["stimulus_id"] = uuid4().hex
        stimulus["selection_settings"].update({
            "maximum_harmonic_states": state_count,
            "harmonic_states": actual_state_count,
            "hold_bass_note": bool(hold_bass_note),
            "maximum_voices_moved": maximum_voices_moved,
            "maximum_voice_movement_semitones": maximum_movement,
        })
        if probabilities is not None:
            stimulus["selection_settings"].update(
                harmonic_state_weights={str(i+1):w for i,w in enumerate(state_weights)},
                harmonic_state_probabilities={str(i+1):p for i,p in enumerate(probabilities)})
        batch.append(stimulus)
    return batch


def metadata_table(values):
    """Small readable key/value tables; the complete original payload is downloadable."""
    st.table([
        {"Parameter": key.replace("_", " ").capitalize(),
         "Value": json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, tuple))
                  else "—" if value is None else str(value)}
        for key, value in values.items()
    ])


def render_details(metadata, index):
    selected = metadata["selection_settings"]
    chord = metadata["chord"]
    states = metadata["states"]
    audio = metadata["rendering"]
    tonics = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    st.markdown("**Harmony**")
    framework = framework_description(metadata)
    if framework in ("chromatic","chord_targeting"):
        context = "Tonal center / mode: not applicable (no global key)"
        local=metadata.get("chord_targeting",{}).get("local_tonal_collection")
        if local:context+=f" · compatible local collection: {tonics[local['tonic_pitch_class']]} {local['mode']}"
    elif isinstance(selected.get("tonic_midi"), int) and selected.get("modal_preset") in ("major", "minor"):
        context = f"Tonal center: {tonics[selected['tonic_midi'] % 12]} {selected['modal_preset']}"
    else:
        context = "Tonal context: legacy/unknown"
    st.write(f"Framework: {framework} · {context} · "
             f"Initial harmony: {chord['display_label']} ({chord['intended_quality']}) · "
             f"Vocabulary: {selected.get('harmonic_vocabulary', 'Basic')}")
    metadata_table({
        "generation_framework": framework,
        "initial_root_pitch_class": chord.get("root_pitch_class", chord.get("root_note_midi", 0) % 12
                                             if isinstance(chord.get("root_note_midi"), int) else None),
        "initial_intervals": chord.get("template_intervals_from_root", chord.get("triad_intervals_from_root")),
        "harmonic_family": chord.get("harmonic_family", "Triadic"),
        "hold_bass_note": selected.get("hold_bass_note", False),
        "sonority_type": chord.get("sonority_type", f"{chord['intended_quality']} triad"),
        "voice_count": len(chord["notes_midi"]),
        "voicing_description": chord.get("voicing_description", "Root-position close triad"),
        "inversion": chord["inversion"],
        "distinct_pitch_class_count": len({note % 12 for note in chord["notes_midi"]}),
        "octave_doublings": chord.get("octave_doublings", []),
        "omitted_intervals": chord.get("omitted_intervals", []),
    })
    st.table([{"State": number + 1, **({"Harmony":state["chord"]["display_label"]} if "chord" in state else {}),
               "Notes": ", ".join(state["notes_names"]),
               "MIDI": ", ".join(map(str, state["notes_midi"])),
               "Start (s)": state["start_seconds"], "End (s)": state["end_seconds"]}
              for number, state in enumerate(states)])
    st.markdown("**Transformations**")
    if len(states) == 1:
        st.caption("One sustained state; no transformations.")
    for number, state in enumerate(states[1:], 1):
        previous = states[number - 1]
        if "target_relationship" in state:
            st.caption(state["target_relationship"]["class"] + " · " + state["chord"]["display_label"])
        st.caption(f"State {number} → {number + 1} at {state['start_seconds']:.2f}s · "
                   f"{state['common_tone_count']} common tones · "
                   f"Total displacement: {state['total_voice_leading_distance']} semitones")
        st.table([
            {"Voice": voice["voice_id"] + 1,
             "MIDI movement": f"{previous['notes_midi'][voice['voice_id']]} → {voice['pitch_midi']}",
             "Semitones": f"{voice['displacement_semitones']:+d}"}
            for voice in state["voices"] if voice["displacement_semitones"]
        ])
    st.markdown("**Audio**")
    mode = audio["reverb"]
    if isinstance(mode, bool):
        mode = "On" if mode else "Dry"
    metadata_table({
        "instrument / preset": audio["timbre"], "backend": audio["backend"],
        "musical duration (s)": audio["duration_seconds"],
        "rendered duration (s)": round(audio["rendered_duration_seconds"], 3),
        "reverb mode": mode, "effect level": audio["effect_level"],
    })
    st.markdown("**Generation metadata**")
    metadata_table({"stimulus_id": metadata.get("stimulus_id"),
                    "created_at": metadata["created_at"], "generation_mode": metadata["generation_mode"]})
    with st.expander("Selection parameters and weights"):
        metadata_table(selected)
    with st.expander("Technical harmony, timing and rendering metadata"):
        st.caption("Initial harmonic object")
        metadata_table(chord)
        for number, state in enumerate(states):
            st.caption(f"State {number + 1} — complete metadata")
            metadata_table(state)
        st.caption("Transition timing")
        if metadata["transitions"]:
            st.table(metadata["transitions"])
        else:
            st.caption("No transitions.")
        st.caption("Rendering settings")
        metadata_table(audio)
    st.download_button("Download complete metadata (JSON)",
                       json.dumps(metadata, ensure_ascii=False, indent=2),
                       file_name=f"ambient_stimulus_{index + 1:02d}_metadata.json",
                       mime="application/json", key=f"ambient_metadata_download_{index}", on_click="ignore")


def render_stimulus(stimulus, index, duration, timbre, reverb,
                    requested_backend, font, program, preset_name, reverb_mode, effect_level,
                    *, display=True, epoch=None):
    metadata = copy.deepcopy(stimulus)
    chord = metadata["chord"]
    if "states" not in metadata:
        selected = metadata["selection_settings"]
        metadata["states"] = build_states(chord["notes_midi"], 1, 1, 1,
                                           selected["register_low"], selected["register_high"])
    states = metadata["states"]
    metadata["transitions"] = time_states(states, duration)
    content = tuple(tuple(state["notes_midi"]) for state in states)
    effective_backend = "SoundFont" if font is not None else "Procedural"
    with st.spinner(f"Rendering stimulus {index + 1}…"):
        try:
            if font is not None:
                wav = cached_audio(content, duration, None, False, SOUNDFONT_VERSION,
                                   font, program, reverb_mode, effect_level)
            else:
                wav = cached_audio(content, duration, timbre, reverb, RENDERER_VERSION)
        except (SoundFontUnavailable, OSError, ValueError, RuntimeError, AttributeError, TypeError) as error:
            if font is None:
                st.error(f"Audio rendering failed: {error}")
                return metadata
            st.warning(f"Sample playback unavailable; using {timbre}. {error}")
            effective_backend = "Procedural"
            wav = cached_audio(content, duration, timbre, reverb, RENDERER_VERSION)
    sampled = effective_backend == "SoundFont"
    with wave.open(io.BytesIO(wav), "rb") as rendered:
        rendered_duration = rendered.getnframes() / rendered.getframerate()
    metadata["rendering"] = {
        "duration_seconds": duration, "backend": effective_backend,
        "requested_backend": requested_backend,
        "timbre": preset_name if sampled else timbre,
        "reverb": reverb_mode if sampled else reverb,
        "effect_level": effect_level if sampled else None,
        "reverb_engine": "FluidSynth native" if sampled else "procedural taps",
        "native_reverb_settings": REVERB_SETTINGS[reverb_mode] if sampled else None,
        "tail_seconds": max(0.0, rendered_duration - duration),
        "rendered_duration_seconds": rendered_duration,
        "final_note_off_seconds": duration,
        "tail_trim_threshold_dbfs": TAIL_THRESHOLD_DBFS if sampled else None,
        "minimum_release_seconds": MIN_RELEASE_SECONDS if sampled else None,
        "maximum_tail_seconds": MAX_TAIL_SECONDS if sampled else None,
        "tail_limit_reached": sampled and rendered_duration >= duration + MAX_TAIL_SECONDS,
        "sample_rate": SAMPLE_RATE, "channels": 2 if sampled else 1,
        "renderer_version": SOUNDFONT_VERSION if sampled else RENDERER_VERSION,
        "soundfont": {"path": font[0], "sha256": font[1], "bank": 0,
                      "program": program} if sampled else None,
        "states_midi": [state["notes_midi"] for state in states],
        "transition_overlap_seconds": TRANSITION_SECONDS,
    }
    if not display:
        return metadata, wav
    identity = stimulus_id(metadata, index)
    with st.container(key=f"ambient_card_heading_{index}"):
        heading=st.columns([1,.08],gap="small",vertical_alignment="center")
        with heading[0]:st.markdown(f"**Stimulus {index + 1} · {identity[:8]}**")
        with heading[1]:
            record=record_for(metadata)
            st.button("↗",key=f"ambient_card_open_{index}",help="Open stimulus details",type="tertiary",
                      on_click=open_detail,args=(metadata,index,wav,record["saved_id"] if record else None))
    render_player(wav, identity, epoch)
    save_control(metadata, index, wav=wav, details=False, card_reasons=True, epoch=epoch)
    return metadata


def collect_current_batch():
    """Collect the displayed recipes without regenerating or changing decisions."""
    try:
        metadata=st.session_state.get("ambient_batch_metadata",[])
        batch=st.session_state.get("ambient_batch",[])
        if (not batch or len(metadata)!=len(batch)
                or [m.get("stimulus_id") for m in metadata]!=[m.get("stimulus_id") for m in batch]):
            raise ValueError("Wait for the complete current batch to finish rendering before collecting.")
        for item in metadata:saved_library.validate_metadata(item)
        records,errors=saved_library.list_records()
        if errors:raise ValueError("Resolve unreadable library entries before collecting; existing data was retained.")
        known_ids={r["metadata"].get("stimulus_id") for r in records}
        known_recipes={r["source_fingerprint"] for r in records}
        missing=[m for m in metadata if m.get("stimulus_id") not in known_ids and saved_library.fingerprint(m) not in known_recipes]
        if missing:
            token=json.dumps([saved_library.fingerprint(m) for m in missing])
            identity=uuid5(NAMESPACE_URL,"hsg-ambient-manual-collection:"+token).hex
            session_id=st.session_state.setdefault("ambient_collection_session_id",uuid4().hex)
            saved_library.collect_batch(missing,identity,session_id,missing[0]["created_at"],
                                        {"collection_method":"manual","displayed_stimulus_ids":[m["stimulus_id"] for m in metadata]})
        st.session_state["ambient_save_notice"]=f"Batch collected · {len(missing)} added; {len(metadata)-len(missing)} existing records and decisions preserved."
    except (OSError,ValueError,KeyError,TypeError) as error:
        st.session_state["ambient_save_notice"]=f"Could not collect batch: {error}"


def refresh_collection():
    try:
        records, _ = saved_library.list_records()
        st.session_state["ambient_saved_tokens"] = {r["source_fingerprint"] for r in records if r["status"] == "saved"}
        st.session_state["ambient_collection_records"] = {
            r["metadata"].get("stimulus_id"): r for r in records if r["metadata"].get("stimulus_id")
        }
    except OSError as error:
        st.warning(f"Collection library unavailable: {error}")


def render_ambient():
    st.set_page_config(layout="wide")
    st.title("HSG · Ambient")
    st.caption("Controlled harmonic transformations · stimulus batches")
    view = st.radio("VIEW", ["Cards", "Arrange", "Saved", "Relational Study", "Models"], horizontal=True,
                    label_visibility="collapsed", key="ambient_view", on_change=close_detail)
    for key in ("ambient_saved_status_filter","ambient_saved_status_excluded","ambient_saved_study_filter","ambient_saved_study_counts","ambient_saved_page","ambient_saved_page_size"):
        if key in st.session_state:st.session_state[key]=st.session_state[key]
    st.markdown("""<style>
    /* The legacy entry point caps .block-container at 760px !important.
       Override only the container that actually contains Ambient's toolbar. */
    .block-container:has(.st-key-ambient_toolbar),
    .block-container:has(.st-key-ambient_study_workspace),
    .block-container:has(.st-key-ambient_library_workspace),
    .block-container:has(.st-key-ambient_models_workspace) {
      max-width: none !important; width: 100%;
      padding-inline: clamp(16px, 2vw, 32px) !important;
    }
    /* Keep equal-value range handles independently visible and clickable.
       Individual translate preserves BaseWeb's value-positioning transform. */
    .st-key-ambient_voice_count_range [role="slider"][aria-valuenow="2"]:has(+ [role="slider"][aria-valuenow="2"]),
    .st-key-ambient_voice_count_range [role="slider"][aria-valuenow="5"]:has(+ [role="slider"][aria-valuenow="5"]),
    .st-key-ambient_voice_count_range [role="slider"][aria-valuenow="3"]:has(+ [role="slider"][aria-valuenow="3"]),
    .st-key-ambient_voice_count_range [role="slider"][aria-valuenow="4"]:has(+ [role="slider"][aria-valuenow="4"]) { translate:-7px 0; }
    .st-key-ambient_voice_count_range [role="slider"][aria-valuenow="2"] + [role="slider"][aria-valuenow="2"],
    .st-key-ambient_voice_count_range [role="slider"][aria-valuenow="5"] + [role="slider"][aria-valuenow="5"],
    .st-key-ambient_voice_count_range [role="slider"][aria-valuenow="3"] + [role="slider"][aria-valuenow="3"],
    .st-key-ambient_voice_count_range [role="slider"][aria-valuenow="4"] + [role="slider"][aria-valuenow="4"] { translate:7px 0; }
    [class*="st-key-ambient_card_preview_"] [data-testid="stButton"] { margin-top:0 !important; }
    [class*="st-key-ambient_card_preview_"] button { width:28px; min-width:28px; min-height:28px; padding:0 !important; border:0 !important; }
    [class*="st-key-ambient_card_preview_"] button p { font-size:12px !important; }
    [class*="st-key-ambient_card_favorite_"] [data-testid="stButton"] { margin-top:0 !important; }
    [class*="st-key-ambient_card_favorite_"] button { width:32px; min-width:32px; min-height:32px; padding:0 !important; border:0 !important; font-size:25px !important; line-height:1; }
    [class*="st-key-ambient_card_favorite_"] button p { font-size:25px !important; line-height:1; }
    [class*="st-key-ambient_library_favorite_"] button p { font-size:18px !important; line-height:1; }
    [class*="st-key-ambient_card_heading_"] [data-testid="stButton"] { margin-top:0 !important; }
    [class*="st-key-ambient_bypass_reason_fields_"] { gap:0 !important; }
    [class*="st-key-ambient_bypass_reason_fields_"] [data-testid="stElementContainer"] { margin:0 !important; gap:0; }
    [class*="st-key-ambient_bypass_reason_fields_"] [data-testid="stCheckbox"] { height:16px; min-height:16px; margin:0 !important; }
    [class*="st-key-ambient_bypass_reason_fields_"] [data-testid="stCheckbox"] label { height:16px; align-items:center; }
    [class*="st-key-ambient_bypass_reason_fields_"] [data-testid="stCheckbox"] label > div { padding-left:0 !important; }
    [class*="st-key-ambient_card_heading_"] button { min-height:22px; width:22px; padding:0 !important; border:0 !important; font-size:15px !important; }
    [class*="st-key-ambient_bypass_reason_fields_"] [data-testid="stVerticalBlock"] { gap:0; }
    [class*="st-key-ambient_bypass_reason_fields_"] [data-testid="stCheckbox"] label { min-height:15px; padding:0; }
    [class*="st-key-ambient_bypass_reason_fields_"] [data-testid="stCheckbox"] p { font-size:9px !important; line-height:12px; margin:0; white-space:nowrap; }
    [class*="st-key-ambient_bypass_reason_fields_"] [data-testid="stCheckbox"] label > span { width:12px; height:12px; min-width:12px; margin:0 4px 0 0 !important; }
    .st-key-ambient_saved_pagination [data-testid="stButton"] { margin-top:0 !important; }
    .st-key-ambient_saved_pagination button { min-height:28px; padding:0 6px !important; }
    .st-key-ambient_batch_grid { container: ambient-cards / inline-size; }
    .st-key-ambient_batch_grid [data-testid="stVerticalBlock"] { gap: .4rem; }
    @container ambient-cards (max-width: 600px) {
      .st-key-ambient_batch_grid > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
      .st-key-ambient_batch_grid > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        width: 100% !important; flex: 1 1 100% !important; min-width: 0 !important;
      }
    }
    .st-key-ambient_batch_grid [data-testid="stVerticalBlockBorderWrapper"] { padding: .65rem; }
    [class*="st-key-ambient_library_row_"] {
      container: ambient-library-row / inline-size;
      border-bottom: 1px solid #252525; padding-block: 1px;
    }
    [class*="st-key-ambient_library_row_"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
      display: grid !important;
      grid-template-columns: 34px 90px minmax(140px, 1fr) 145px minmax(130px, 220px) 110px;
      gap: 8px; align-items: center; width: 100%;
    }
    [class*="st-key-ambient_library_row_"] [data-testid="stColumn"] {
      min-width: 0 !important; width: 100% !important;
    }
    [class*="st-key-ambient_library_row_"] [data-testid="stVerticalBlock"] { gap: .15rem; }
    [class*="st-key-ambient_library_row_"] p { margin-bottom: 0; overflow-wrap: anywhere; }
    [class*="st-key-ambient_library_row_"] .element-container,
    [class*="st-key-ambient_library_row_"] .stMarkdown { margin-bottom: 0 !important; }
    [class*="st-key-ambient_library_row_"] .stButton { margin-top: 0 !important; }
    [class*="st-key-ambient_library_row_"] [data-testid="stCaptionContainer"] { margin-block: 0 !important; }
    [class*="st-key-ambient_library_row_"] button {
      padding: 4px 6px; white-space: nowrap; font-size: 12px;
      min-height:26px; min-width:0; border:0 !important; padding:0 3px !important;
    }
    [class*="st-key-ambient_library_row_"].ambient-playing-row { background: #ffffff10; }
    @container ambient-library-row (max-width: 720px) {
      [class*="st-key-ambient_library_row_"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
        grid-template-columns: 28px 74px minmax(115px, 1fr) 104px; gap: 1px 6px;
      }
      [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(1) { grid-column:1; grid-row:1; }
      [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(2) { grid-column:2; grid-row:1; }
      [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(3) { grid-column:1 / 3; grid-row:2; overflow:hidden; }
      [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(3) p { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:10px; }
      [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(4) { grid-column:3; grid-row:1; }
      [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(5) { grid-column:3 / 5; grid-row:2; }
      [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(6) { grid-column:4; grid-row:1; }
      [class*="st-key-ambient_library_row_"] .ambient-study-count { font-size:10px; }
    }
    [class*="st-key-ambient_library_row_"] [data-testid="stTextInput"] input { min-height:26px; height:26px; font-size:11px; padding:2px 6px; text-overflow:ellipsis; }
    [class*="st-key-ambient_library_row_"] [data-baseweb="input"] { border-color:#333; background:transparent; min-height:26px; }
    [class*="st-key-ambient_library_row_"] [data-testid="stTextInput"] { padding:0; }
    [class*="st-key-ambient_library_row_"] .ambient-study-count { color:#888; font-size:11px; white-space:nowrap; }
    [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(6) [data-testid="stHorizontalBlock"] { flex-wrap:nowrap; gap:0; }
    [class*="st-key-ambient_library_row_"] [data-testid="stColumn"]:nth-child(6) [data-testid="stColumn"] { grid-column:auto; grid-row:auto; }
    @media (max-width: 900px) {
      .st-key-ambient_toolbar [data-testid="stHorizontalBlock"] { display: grid !important; grid-template-columns: 1fr 1fr; gap: 6px; }
      .st-key-ambient_toolbar [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
      .st-key-ambient_toolbar [data-testid="stColumn"]:nth-child(3) { grid-column: 1 / -1; }
      .st-key-ambient_library_header [data-testid="stHorizontalBlock"] { display: grid !important; grid-template-columns: 150px minmax(235px, 1fr) 65px; gap: 6px; }
      .st-key-ambient_library_header [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
      .st-key-ambient_batch_grid > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    }
    @media (max-width: 520px) {
      .st-key-ambient_library_header [data-testid="stHorizontalBlock"] { grid-template-columns: 1fr 65px; }
      .st-key-ambient_library_header [data-testid="stColumn"]:nth-child(2) { grid-column: 1 / -1; grid-row: 2; }
      .st-key-ambient_library_header [data-testid="stColumn"]:nth-child(3) { grid-column: 2; grid-row: 1; }
    }
    </style>""", unsafe_allow_html=True)
    if view in ("Relational Study", "Saved", "Models"):
        # Preserve generator widgets while the dedicated study workspace hides
        # them. Session inventories and pending trials live on disk separately.
        for key in ("ambient_tonic", "ambient_mode", "ambient_generation_framework", "ambient_register",
                    "ambient_vocabulary", "ambient_voice_count", "ambient_voice_count_range", "ambient_harmonic_family", "ambient_state_count", "ambient_state_weight_1", "ambient_state_weight_2", "ambient_state_weight_3", "ambient_target_relationship", "ambient_quality_balance",
                    "ambient_maximum_voices_moved", "ambient_maximum_movement", "ambient_hold_bass_note",
                    "ambient_batch_size", "ambient_collection_mode", "ambient_duration", "ambient_backend",
                    "ambient_timbre", "ambient_reverb", "ambient_sf2_path", "ambient_sf_preset", "ambient_sf_reverb",
                    "ambient_sf_effect", "ambient_library_filter", "ambient_library_page"):
            if key in st.session_state:
                st.session_state[key] = st.session_state[key]
        if notice := st.session_state.pop("ambient_save_notice", None):st.toast(notice)
        if view == "Saved":
            import ambient_saved as saved_ui
            with st.container(key="ambient_library_workspace"):
                if "ambient_detail" in st.session_state:saved_ui.render_detail(cached_audio,render_details)
                else:saved_ui.render_saved(cached_audio,render_details)
        elif view=="Models":
            from ambient_models import render_models
            with st.container(key="ambient_models_workspace"):render_models(cached_audio)
        else:
            from ambient_study import render_study
            with st.container(key="ambient_study_workspace"):render_study(cached_audio)
        return
    # Keyed widgets use these defaults only when their session setting is absent.
    font, program, preset_name = None, None, None
    reverb_mode, effect_level = "Dry", 0.3
    with st.sidebar:
        st.subheader("HARMONY")
        tonics = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        framework = st.selectbox("GENERATION FRAMEWORK", ["Diatonic", "Chromatic", "Chord Targeting"], index=1,
                                 key="ambient_generation_framework",
                                 help="Chromatic uses structured sonorities on any eligible pitch class, without a global key.")
        generation_framework = framework.lower().replace(" ","_")
        tonic_name, mode = None, None
        if generation_framework == "diatonic":
            tonic_name = st.selectbox("TONAL CENTER", tonics,
                                      index=tonics.index(st.session_state.get("ambient_tonic", "C")), key="ambient_tonic")
            mode = st.selectbox("MODE", ["major", "minor"],
                                index=["major", "minor"].index(st.session_state.get("ambient_mode", "major")), key="ambient_mode")
        else:
            for key in ("ambient_tonic", "ambient_mode"):
                if key in st.session_state:
                    st.session_state[key] = st.session_state[key]
        low, high = st.slider("REGISTER (ALL PITCHES)", 24, 96, (48, 72), key="ambient_register")
        vocabulary = st.selectbox("HARMONIC VOCABULARY", ["Basic", "Expanded"], index=1, key="ambient_vocabulary")
        voice_count, family = 3, "Triadic"
        if vocabulary == "Expanded":
            voice_count = st.slider("VOICE COUNT · MIN / MAX", 2, 5, (3, 4), step=1,
                                    key="ambient_voice_count_range",
                                    help="Each new stimulus independently samples a voice count within this range. Applies on Generate Batch.")
            family = st.selectbox("HARMONIC FAMILY", FAMILIES, key="ambient_harmonic_family")
        harmonic_relationship,chord_quality_balance="Mixed","Balanced"
        if generation_framework=="chord_targeting":
            harmonic_relationship=st.selectbox("HARMONIC RELATIONSHIP",RELATIONSHIPS,index=RELATIONSHIPS.index("Mixed"),key="ambient_target_relationship",
                                              help="Diatonic uses a consistent local collection. Mixed tries Diatonic, Chromatic and Common-Tone with equal nominal weights, conditioned on feasibility. Hard movement and bass constraints always apply.")
            chord_quality_balance=st.selectbox("CHORD QUALITY BALANCE",QUALITY_BALANCES,key="ambient_quality_balance",
                                              disabled=vocabulary=="Expanded" and family=="Quartal/Interval-based",
                                              help="Balanced equalizes major/minor/neutral template-category mass within each family/root. Favor presets use 3:1 or 1:3 major/minor mass; neutral material remains eligible. Quartal-only families are unaffected.")
        else:
            for key in ("ambient_target_relationship","ambient_quality_balance"):
                if key in st.session_state:st.session_state[key]=st.session_state[key]
        st.caption("HARMONIC STATES · RELATIVE WEIGHTS")
        state_weights=tuple(st.slider(f"{count} {'state' if count==1 else 'states'}",0,100,
                                      25 if count==1 else 100,key=f"ambient_state_weight_{count}",
                                      help="Relative sampling weight. Zero excludes this state count. Applies on Generate Batch.")
                            for count in (1,2,3))
        valid_state_weights=any(state_weights)
        if valid_state_weights:
            percentages=harmonic_state_distribution(state_weights)
            st.caption(" · ".join(f"{i+1} {'state' if i==0 else 'states'}: {value:.1%}" for i,value in enumerate(percentages)))
        else:st.warning("Set at least one harmonic-state weight above zero to generate a batch.")
        state_count=max((i+1 for i,w in enumerate(state_weights) if w),default=1)
        voice_limit = voice_count[1] if isinstance(voice_count, tuple) else voice_count
        if st.session_state.get("ambient_maximum_voices_moved", 3) > voice_limit:
            st.session_state["ambient_maximum_voices_moved"] = voice_limit
        maximum_voices = st.selectbox("MAXIMUM VOICES MOVED", list(range(1, voice_limit + 1)), index=min(2,voice_limit-1),
                                      disabled=state_count == 1, key="ambient_maximum_voices_moved")
        maximum_movement = st.slider("MAXIMUM VOICE MOVEMENT (SEMITONES)", 1, 16, 7,
                                     disabled=state_count == 1, key="ambient_maximum_movement")
        hold_bass_note = st.checkbox("Hold Bass Note", value=False, key="ambient_hold_bass_note")
        batch_size = st.selectbox("STIMULI", [4, 6, 8], key="ambient_batch_size")
        st.caption((("Initial states: diatonic root-position triads. " if generation_framework == "diatonic"
                     else "Initial states: major/minor root-position triads on chromatic roots. ") if vocabulary == "Basic"
                    else "Initial states: structured sonorities with varied voicings. ")
                   + ("Destinations are valid chord targets with optimized voice leading. " if generation_framework=="chord_targeting" else "")
                   + "Harmony changes apply on Generate Batch.")
        st.subheader("DURATION")
        duration = st.slider("SECONDS", 10, 90, 15, key="ambient_duration")
        st.subheader("SOUND")
        # Keep these settings while hiding their former widgets, including on
        # the first rerun after upgrading from a version that displayed them.
        for key,default in (("ambient_backend","SoundFont"),("ambient_timbre","Strings"),("ambient_reverb",False)):
            st.session_state[key]=st.session_state.get(key,default)
        backend=st.session_state["ambient_backend"]
        timbre=st.session_state["ambient_timbre"]
        reverb=st.session_state["ambient_reverb"]
        if backend == "SoundFont" and view == "Saved":
            # Keep inactive widget selections without touching FluidSynth or SF2
            # files: filtering, notes and export must remain metadata-only.
            for key in ("ambient_sf2_path", "ambient_sf_preset", "ambient_sf_reverb", "ambient_sf_effect"):
                if key in st.session_state:
                    st.session_state[key] = st.session_state[key]
            st.caption("Library playback uses each record's captured sound settings.")
        if backend == "SoundFont" and view != "Saved":
            path = st.text_input("LOCAL SF2 PATH", value=os.getenv("AMBIENT_SF2_PATH", ""),
                                 key="ambient_sf2_path")
            try:
                fluid_module()
                font = soundfont_identity(path)
                presets = available_presets(font)
                if not presets:
                    raise SoundFontUnavailable("None of the requested presets exist in this SF2.")
                preset_labels = {label: f"{label} · {actual_name}" for label, _, actual_name in presets}
                preset_names = [item[0] for item in presets]
                preset_name = st.selectbox("SAMPLED PRESET", preset_names,
                                           index=preset_names.index("Warm Pad") if "Warm Pad" in preset_names else 0,
                                           format_func=preset_labels.get, key="ambient_sf_preset")
                program = next(item[1] for item in presets if item[0] == preset_name)
                reverb_mode = st.selectbox("SAMPLED REVERB", list(REVERB_SETTINGS), index=list(REVERB_SETTINGS).index("Room"), key="ambient_sf_reverb")
                effect_level = st.slider("EFFECT LEVEL", 0.0, 1.0, 0.60, 0.05,
                                         disabled=reverb_mode == "Dry", key="ambient_sf_effect")
            except (SoundFontUnavailable, OSError, ValueError, RuntimeError, AttributeError, TypeError) as error:
                font = None
                st.warning(str(error))
                st.caption("Using procedural playback until SoundFont setup is complete.")
                with st.expander("SoundFont setup"):
                    st.code(SETUP, language="text")

    with st.container(key="ambient_toolbar"):
        controls=st.columns([1.3,1.7,4],vertical_alignment="center")
        with controls[0]:
            generate=st.button("Generate Batch",key="ambient_generate",disabled="ambient_detail" in st.session_state or not valid_state_weights)
        with controls[1]:
            st.button("Collect Batch",key="ambient_collect",on_click=collect_current_batch,
                      disabled=not st.session_state.get("ambient_batch") or "ambient_detail" in st.session_state)
        with controls[2]:
            st.caption("Collect the current batch · existing decisions are preserved · no automatic collection")
    if notice := st.session_state.pop("ambient_save_notice", None):
        st.toast(notice)
    if "ambient_detail" in st.session_state:
        refresh_collection()
        render_detail(cached_audio, render_details)
        return
    if view == "Saved":
        render_saved(cached_audio, render_details)
        return
    refresh_collection()
    if generate:
        try:
            batch = generate_batch(batch_size, 60 + tonics.index(tonic_name) if generation_framework == "diatonic" else None, mode,
                                   low, high, state_count, maximum_voices, maximum_movement,
                                   vocabulary, voice_count, family, hold_bass_note=hold_bass_note,
                                   generation_framework=generation_framework,state_weights=state_weights,
                                   harmonic_relationship=harmonic_relationship,chord_quality_balance=chord_quality_balance)
            st.session_state["ambient_batch"] = batch
            refresh_collection()
            st.session_state.pop("ambient_sonority", None)
        except (OSError, ValueError) as error:
            st.error(str(error))
            st.info("No new batch generated. The previous batch is retained.")
    if "ambient_batch" not in st.session_state and "ambient_sonority" in st.session_state:
        st.session_state["ambient_batch"] = [st.session_state["ambient_sonority"]]
    if "ambient_batch" not in st.session_state:
        st.info("Generate a batch to begin auditioning.")
        return
    batch = st.session_state["ambient_batch"]
    arrange_preview=False
    if view=="Arrange":
        arrange_preview=st.toggle("5-second preview",value=False,key="ambient_arrange_preview",
            help="Compress playback to 5 seconds without changing the saved stimulus. Release/reverb tails may extend playback.")
    batch_id, epoch = playback_scope(batch, view, (duration, backend, timbre, reverb, font,
                                                  program, preset_name, reverb_mode, effect_level,arrange_preview))
    batch_metadata = []
    if view == "Arrange":
        prepared = [render_stimulus(stimulus, index, duration, timbre, reverb, backend, font,
                                    program, preset_name, reverb_mode, effect_level, display=False)
                    for index, stimulus in enumerate(batch)]
        prepared = [item for item in prepared if isinstance(item, tuple)]
        batch_metadata = [metadata for metadata, _ in prepared]
        if arrange_preview:
            from ambient_preview import preview_audio
            try:prepared=[(metadata,preview_audio(metadata)) for metadata,_ in prepared]
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError) as error:
                st.warning(f"Fast preview unavailable: {error}")
                return
        render_arrangement(prepared, batch_id, epoch, on_save=save_action,
                           saved_tokens=st.session_state.get("ambient_saved_tokens", set()),
                           on_bypass=bypass_action, records=st.session_state.get("ambient_collection_records", {}))
    else:
        with st.container(key="ambient_batch_grid"):
            for start in range(0, len(batch), 2):
                columns = st.columns(2)
                for index in range(start, min(start + 2, len(batch))):
                    with columns[index - start]:
                        with st.container(border=True, key=f"ambient_stimulus_card_{index}"):
                            batch_metadata.append(render_stimulus(
                                batch[index], index, duration, timbre, reverb, backend, font,
                                program, preset_name, reverb_mode, effect_level, epoch=epoch
                            ))
    st.session_state["ambient_batch_metadata"] = batch_metadata
    st.caption("Sound settings retain every stimulus's pitches and transformations. "
               "Reverb and note release may extend playback beyond the musical duration.")
