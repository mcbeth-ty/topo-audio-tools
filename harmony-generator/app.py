from datetime import datetime
import os

import streamlit as st
import pretty_midi
import random
from midi_generator import generate_sequences, build_probability_field
import textwrap
import numpy as np
import wave
import io
import json
import copy


st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@300;400;500&display=swap');

/* =========================
   GLOBAL
========================= */

.stApp {
    background-color: #0a0a0a;
    color: #d0d0d0;
    font-family: 'Roboto Mono', monospace !important;
}
            
.stTextInput input {
    font-size: 10px !important;
    padding-top: 4px !important;
    padding-bottom: 4px !important;
}
            


/* =========================
   SIDEBAR
========================= */        

section[data-testid="stSidebar"] {
    background-color: #161616;
    border-right: 1px solid #222222;
    width: 260px !important;
}

section[data-testid="stSidebar"] * {
    color: #cfcfcf !important;
}

/* =========================
   MAIN CONTENT
========================= */

.block-container {
    padding-top: 2rem !important;
    max-width: 760px !important;
}

/* =========================
   TYPOGRAPHY
========================= */

h1 {
    font-size: 26px !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    color: #e0e0e0 !important;
}

h2, h3 {
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
    color: #d0d0d0 !important;
}

p, label, div {
    color: #c8c8c8 !important;
    font-size: 10px !important;
}
        
.compact-label {
    font-size: 11px;
    line-height: 1.0;
    padding-top: 6px;
    color: #c8c8c8;
}
            
/* section headers */

h3 {
    margin-bottom: 14px !important;
    margin-top: 14px !important;
}

/* =========================
   SLIDERS
========================= */

.stSlider {
    padding-top: 0px !important;
    padding-bottom: 2px !important;
}

.stSlider label {
    font-size: 11px !important;
    margin-bottom: -6px !important;
}

/* slider track */
.stSlider [data-baseweb="slider"] > div > div {
    background-color: #5f5f5f !important;
}

/* slider handle */
.stSlider [role="slider"] {
    background-color: #b0b0b0 !important;
    border: none !important;
    box-shadow: none !important;
}
        
/* slider track thickness */
.stSlider [data-baseweb="slider"] > div > div > div {
    height: 1px !important;
}
            
/* slider handle size */
.stSlider [role="slider"] {
    width: 10px !important;
    height: 10px !important;
}

/* =========================
   SELECTBOXES
========================= */

.stSelectbox > div > div {
    background-color: #101010 !important;
    border: 1px solid #2a2a2a !important;
    color: #d0d0d0 !important;
}

/* =========================
   BUTTONS
========================= */

.stButton button {
    background-color: transparent !important;
    border: 1px solid #4a4a4a !important;
    border-radius: 2px !important;
    color: #d0d0d0 !important;

    font-size: 11px !important;
    font-weight: 500 !important;

    text-transform: uppercase;
    letter-spacing: 0.08em;

    padding: 0.4rem 0.8rem !important;
}

.stButton button:hover {
    border-color: #888888 !important;
    color: #ffffff !important;
}

/* =========================
   SUCCESS MESSAGE
========================= */

.stAlert {
    background-color: #111111 !important;
    border: 1px solid #2c2c2c !important;
    color: #d0d0d0 !important;
}
            
/* =========================
   COMPACT SPACING
========================= */

div[data-testid="stVerticalBlock"] > div {
    gap: 0.2rem !important;
}

.stMarkdown {
    margin-bottom: -10px !important;
}

.element-container {
    margin-bottom: -8px !important;
}

div[data-baseweb="slider"] {
    margin-top: -8px !important;
    margin-bottom: -14px !important;
}
            
/* spacing above generate button */

.stButton {
    margin-top: 16px !important;
}

            

.sample-card {
    border: 1px solid #303030;
    background-color: #111111;
    padding: 10px;
    margin-bottom: 12px;
    min-height: 220px;
}

.sample-index {
    font-size: 18px !important;
    letter-spacing: 0.08em;
    color: #eeeeee !important;
    margin-bottom: 4px;
}

.sample-id {
    font-size: 7px !important;
    color: #bdbdbd !important;
    word-break: break-all;
    margin-bottom: 2px;
}

.sample-file {
    font-size: 7px !important;
    color: #888888 !important;
    word-break: break-all;
    margin-bottom: 8px;
}

.event-block {
    border-top: 1px solid #272727;
    padding-top: 6px;
    margin-top: 6px;
    font-size: 7px !important;
    line-height: 1.35;
    color: #c8c8c8 !important;
}

.event-title {
    font-size: 8px !important;
    letter-spacing: 0.08em;
    color: #eeeeee !important;
    margin-bottom: 3px;
}

.global-metadata {
    border: 1px solid #2a2a2a;
    background-color: #101010;
    padding: 14px;
    margin-bottom: 20px;
}

.global-title {
    font-size: 14px;
    letter-spacing: 0.08em;
    margin-bottom: 14px;
    color: #f0f0f0;
}

.global-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 14px;
}

.meta-label {
    font-size: 7px;
    color: #777777;
    margin-bottom: 4px;
    letter-spacing: 0.08em;
}

.meta-value {
    font-size: 10px;
    color: #d0d0d0;
}

audio {
    height: 28px !important;
    width: 120px !important;
}

:root {
    --topo-cyan: #59d8ff;
}

.diatonic-label {
    color: #59d8ff !important;
    font-weight: 500 !important;
}

.diatonic-chip {
    color: #59d8ff !important;
    border: 1px solid #245767;
    background: rgba(89, 216, 255, 0.07);
    padding: 1px 4px;
    margin-right: 4px;
    display: inline-block;
    margin-bottom: 3px;
}

.field-chip {
    color: #b8b8b8 !important;
    border: 1px solid #333333;
    padding: 1px 4px;
    margin-right: 4px;
    display: inline-block;
    margin-bottom: 3px;
}

.event-role-diatonic {
    color: #59d8ff !important;
}

.event-label-diatonic {
    color: #59d8ff !important;
    font-weight: 500 !important;
}
            
</style>
""", unsafe_allow_html=True)

st.set_page_config(
    page_title="Harmonic Sequence Generator",
    layout="wide"
)

st.title("Harmonic Sequence Generator")
st.caption("V2 probability-field prototype")

def compact_slider(label, min_val, max_val, default, key=None, label_class="compact-label"):
    col1, col2 = st.columns([1, 2.2])

    with col1:
        st.markdown(
            f"<div class='{label_class}'>{label}</div>",
            unsafe_allow_html=True
        )

    with col2:
        value = st.slider(
            label,
            min_val,
            max_val,
            default,
            key=key,
            label_visibility="collapsed"
        )

    return value

def compact_selectbox(label, options, default_index=0):

    col1, col2 = st.columns([1, 2.2])

    with col1:
        st.markdown(
            f"<div class='compact-label'>{label}</div>",
            unsafe_allow_html=True
        )

    with col2:
        value = st.selectbox(
            label,
            options,
            index=default_index,
            label_visibility="collapsed"
        )

    return value



MAJOR_DIATONIC_DEFAULTS = {
    "I": 95,
    "ii": 85,
    "iii": 75,
    "IV": 90,
    "V": 95,
    "vi": 85,
    "vii°": 65,
}

MINOR_DIATONIC_DEFAULTS = {
    "i": 95,
    "ii°": 65,
    "♭III": 95,
    "iv": 85,
    "v": 85,
    "♭VI": 95,
    "♭VII": 95,
}


def render_label_chips(items, diatonic_set=None, max_items=None):
    diatonic_set = diatonic_set or set()
    visible_items = items[:max_items] if max_items else items
    html_parts = []

    for item in visible_items:
        chip_class = "diatonic-chip" if item in diatonic_set else "field-chip"
        html_parts.append(f"<span class='{chip_class}'>{item}</span>")

    if max_items and len(items) > max_items:
        html_parts.append("<span class='field-chip'>...</span>")

    return "".join(html_parts)

def midi_to_freq(midi_note):
    return 440.0 * (2 ** ((midi_note - 69) / 12))


def render_sine_preview(sample, bpm=90, sample_rate=44100):
    duration_beats = max(event["end_beat"] for event in sample["events"])
    duration_seconds = duration_beats * (60 / bpm)

    audio = np.zeros(int(duration_seconds * sample_rate))

    for event in sample["events"]:
        start_sample = int(event["start_beat"] * (60 / bpm) * sample_rate)
        end_sample = int(event["end_beat"] * (60 / bpm) * sample_rate)

        t = np.linspace(
            0,
            (end_sample - start_sample) / sample_rate,
            end_sample - start_sample,
            endpoint=False
        )

        chord_audio = np.zeros_like(t)

        for note in event["notes_midi"]:
            freq = midi_to_freq(note)
            chord_audio += np.sin(2 * np.pi * freq * t)

        chord_audio /= max(len(event["notes_midi"]), 1)

        fade_len = min(256, len(chord_audio) // 10)
        fade = np.linspace(0, 1, fade_len)

        chord_audio[:fade_len] *= fade
        chord_audio[-fade_len:] *= fade[::-1]

        audio[start_sample:end_sample] += chord_audio

    audio = audio / max(np.max(np.abs(audio)), 1e-9)
    audio_int16 = (audio * 32767 * 0.4).astype(np.int16)

    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())

    buffer.seek(0)
    return buffer

def save_midi_from_metadata(sample, filepath):
    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)

    for event in sample["events"]:
        for pitch in event["notes_midi"]:
            note = pretty_midi.Note(
                velocity=100,
                pitch=pitch,
                start=event["start_beat"],
                end=event["end_beat"]
            )

            instrument.notes.append(note)

    midi.instruments.append(instrument)
    midi.write(filepath)

def save_generated_files(metadata, topo_explorer_dir, save_midi=True, save_wav=True, bpm=90):
    run_name = metadata["run_name"]

    archive_dir = os.path.join(topo_explorer_dir, "archive")
    sample_sets_dir = os.path.join(archive_dir, "sample_sets")
    audio_dir = os.path.join(archive_dir, "audio", run_name)
    midi_dir = os.path.join(archive_dir, "midi", run_name)

    os.makedirs(sample_sets_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(midi_dir, exist_ok=True)

    metadata_to_save = copy.deepcopy(metadata)

    for sample in metadata_to_save["samples"]:
        sample_id = sample["sample_id"]

        if save_midi:
            midi_filename = f"{sample_id}.mid"
            midi_path = os.path.join(midi_dir, midi_filename)
            save_midi_from_metadata(sample, midi_path)
            sample["midi_file"] = midi_filename
        else:
            sample["midi_file"] = None

        if save_wav:
            wav_filename = f"{sample_id}.wav"
            wav_path = os.path.join(audio_dir, wav_filename)

            audio_buffer = render_sine_preview(sample, bpm=bpm)

            with open(wav_path, "wb") as wav_file:
                wav_file.write(audio_buffer.getvalue())

            sample["audio_file"] = wav_filename
        else:
            sample["audio_file"] = None

    metadata_filename = f"{run_name}_sampleset.json"
    metadata_path = os.path.join(sample_sets_dir, metadata_filename)

    with open(metadata_path, "w") as json_file:
        json.dump(metadata_to_save, json_file, indent=4)

    return {
        "archive_dir": archive_dir,
        "metadata_path": metadata_path,
        "audio_dir": audio_dir,
        "midi_dir": midi_dir,
    }

with st.sidebar:
    
    st.subheader("HARMONIC SEQUENCE SETTINGS")
    
    sequence_count = compact_slider("SEQUENCES", 1, 50, 6)
    beats_per_bar = compact_slider("BEATS PER BAR", 1, 8, 4)
    bars = compact_slider("BARS", 1, 8, 2)
    harmonic_events = compact_slider("HARMONIC EVENTS", 1, 8, 2)
    bpm = compact_slider("BPM", 40, 200, 120)

    preview_total_beats = beats_per_bar * bars
    preview_duration_seconds = preview_total_beats * (60 / bpm)

    if preview_duration_seconds < 3:
        preview_time_scale = "Micro Scale"
    elif preview_duration_seconds < 10:
        preview_time_scale = "Local Scale"
    elif preview_duration_seconds < 30:
        preview_time_scale = "Phrase Scale"
    else:
        preview_time_scale = "Extended Scale"

    st.markdown(
        f"""
        <div style="
            border: 1px solid #2a2a2a;
            padding: 8px;
            margin-top: 12px;
            margin-bottom: 16px;
            line-height: 1.4;
        ">
            <div style="font-size:8px; color:#777;">DURATION</div>
            <div>{preview_duration_seconds:.1f}s</div>
            <div style="font-size:8px; color:#777; margin-top:6px;">TIME SCALE</div>
            <div>{preview_time_scale}</div>
        </div>
        """,
        unsafe_allow_html=True
    )   

    tonic_name = compact_selectbox(
        "TONAL CENTER",
        ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    )

    mode = compact_selectbox(
        "MODE",
        ["major", "minor"]
    )
    register_low = compact_slider("REGISTER LOW", 24, 84, 48)
    register_high = compact_slider("REGISTER HIGH", 36, 96, 66)

    st.subheader("CHORD TYPE WEIGHTS")

    dyad_weight = compact_slider("DYAD", 0, 100, 20)
    triad_weight = compact_slider("TRIAD", 0, 100, 80)

    chord_type_weights = [dyad_weight, triad_weight]

    st.subheader("HARMONIC FIELD WEIGHTS")

    diatonic_weight = compact_slider("DIATONIC", 0, 100, 100, label_class="compact-label diatonic-label")

    if mode == "major":
        diatonic_defaults = MAJOR_DIATONIC_DEFAULTS
    else:
        diatonic_defaults = MINOR_DIATONIC_DEFAULTS

    diatonic_object_weights = {}

    st.markdown(
        "<div style='font-size:8px; color:#777; margin-top:8px;'>DIATONIC OBJECT WEIGHTS</div>",
        unsafe_allow_html=True
    )

    st.write("")
    st.write("")

    for roman_label, default_weight in diatonic_defaults.items():
        diatonic_object_weights[roman_label] = compact_slider(
            roman_label,
            0,
            100,
            default_weight,
            key=f"diatonic_{mode}_{roman_label}",
            label_class="compact-label diatonic-label",
        )

    parallel_borrowing_weight = compact_slider("PARALLEL BORROWING", 0, 100, 0)
    uncommon_1_weight = compact_slider("UNCOMMON 1", 0, 100, 0)
    uncommon_2_weight = compact_slider("UNCOMMON 2", 0, 100, 0)

    preview_field = build_probability_field(
        modal_preset=mode,
        diatonic_weight=diatonic_weight,
        parallel_borrowing_weight=parallel_borrowing_weight,
        uncommon_1_weight=uncommon_1_weight,
        uncommon_2_weight=uncommon_2_weight,
        diatonic_object_weights=diatonic_object_weights,
    )

    active_preview_labels = [
        item["roman_numeral"]
        for item in preview_field
        if item["weight"] > 0
    ]

    active_diatonic_labels = [
        item["roman_numeral"]
        for item in preview_field
        if item["weight"] > 0 and item["active_role"] == "diatonic"
    ]

    st.markdown(
        f"""
        <div style="
            border: 1px solid #2a2a2a;
            padding: 8px;
            margin-top: 12px;
            margin-bottom: 16px;
            line-height: 1.4;
        ">
            <div style="font-size:8px; color:#777;">ACTIVE HARMONIC OBJECTS</div>
            <div>{len(active_preview_labels)} / 48</div>
            <div style="font-size:8px; color:#777; margin-top:6px;">DIATONIC LABELS</div>
            <div>{render_label_chips(active_diatonic_labels, set(active_diatonic_labels))}</div>
            <div style="font-size:8px; color:#777; margin-top:6px;">ACTIVE LABELS</div>
            <div>{render_label_chips(active_preview_labels, set(active_diatonic_labels), max_items=18)}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.subheader("INVERSION WEIGHTS")

    root_inversion_weight = compact_slider("ROOT", 0, 100, 70)
    first_inversion_weight = compact_slider("FIRST INVERSION", 0, 100, 20)
    second_inversion_weight = compact_slider("SECOND INVERSION", 0, 100, 10)

    inversion_weights = [
        root_inversion_weight,
        first_inversion_weight,
        second_inversion_weight
    ]

    st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)

    export_dir = st.text_input(
        "export directory",
        "/Users/tylermcbeth/Applications/topo-audio/topo-analysis"
    )

    export_tag = st.text_input(
        "export tag",
        ""
    )

    now_string = datetime.now().strftime("%y%m%d_%H_%M")

    key_label = tonic_name

    if mode == "minor":
        key_label += "m"

    he_label = f"{harmonic_events}HE"

    tag_clean = export_tag.strip().replace("/", "-")

    folder_parts = [now_string, key_label, he_label]

    if tag_clean:
        folder_parts.append(tag_clean)

    run_name = "_".join(folder_parts)

    generate = st.button("GENERATE MIDI")

    if "run_metadata" in st.session_state:

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

        save_midi = st.checkbox("SAVE MIDI", value=True)
        save_wav = st.checkbox("SAVE WAV", value=True)

        save_files = st.button("SAVE FILES")

        if save_files:
            export_folder = save_generated_files(
                metadata=st.session_state["run_metadata"],
                topo_explorer_dir=export_dir,
                save_midi=save_midi,
                save_wav=save_wav,
                bpm=st.session_state.get("display_bpm", 90)
            )

            st.session_state["last_export_folder"] = export_folder


tonic_map = {
    "C": 60,
    "C#": 61,
    "D": 62,
    "D#": 63,
    "E": 64,
    "F": 65,
    "F#": 66,
    "G": 67,
    "G#": 68,
    "A": 69,
    "A#": 70,
    "B": 71,
}

tonic = tonic_map[tonic_name]




if generate:
    run_metadata = generate_sequences(
        sequence_count=sequence_count,
        beats_per_bar=beats_per_bar,
        bars=bars,
        harmonic_events=harmonic_events,
        tonic=tonic,
        mode=mode,
        register_low=register_low,
        register_high=register_high,
        chord_type_weights=chord_type_weights,
        diatonic_weight=diatonic_weight,
        parallel_borrowing_weight=parallel_borrowing_weight,
        uncommon_1_weight=uncommon_1_weight,
        uncommon_2_weight=uncommon_2_weight,
        diatonic_object_weights=diatonic_object_weights,
        inversion_weights=inversion_weights,
        run_name=run_name,
        bpm=bpm
    )

    st.session_state["run_metadata"] = run_metadata
    st.session_state["display_key_label"] = key_label
    st.session_state["display_run_name"] = run_name
    st.session_state["generation_complete"] = True
    st.session_state["display_bpm"] = bpm

    st.rerun()

if "last_export_folder" in st.session_state:
    export_info = st.session_state["last_export_folder"]

    st.success("Saved files.")

    st.write("Archive:", export_info["archive_dir"])
    st.write("Metadata JSON:", export_info["metadata_path"])
    st.write("Audio folder:", export_info["audio_dir"])
    st.write("MIDI folder:", export_info["midi_dir"])

if "run_metadata" in st.session_state:

    metadata = st.session_state["run_metadata"]

    settings = metadata["global_settings"]

    display_key_label = st.session_state.get("display_key_label", "")

    st.markdown(
    textwrap.dedent(f"""
    <div class="global-metadata">

    <div class="global-title">
    {metadata["run_name"]}
    </div>

    <div class="global-grid">

    <div>
    <div class="meta-label">TONIC</div>
    <div class="meta-value">{display_key_label}</div>
    </div>

    <div>
    <div class="meta-label">EVENTS</div>
    <div class="meta-value">{settings["harmonic_events"]}</div>
    </div>

    <div>
    <div class="meta-label">BPM</div>
    <div class="meta-value">{settings["bpm"]}</div>
    </div>

    <div>
    <div class="meta-label">SEQUENCES</div>
    <div class="meta-value">{len(metadata["samples"])}</div>
    </div>

    <div>
    <div class="meta-label">REGISTER</div>
    <div class="meta-value">
    {settings["register_low"]}–{settings["register_high"]}
    </div>
    </div>

    <div>
    <div class="meta-label">LENGTH</div>
    <div class="meta-value">
    {settings["duration_seconds"]:.1f}s
    </div>
    </div>

    <div>
        <div class="meta-label">TIME SCALE</div>
        <div class="meta-value">
            {settings["temporal_integration_scale"]}<br>
            [{settings["temporal_integration_window_seconds"][0]},
            {settings["temporal_integration_window_seconds"][1]}s]
        </div>
    </div>

    </div>

    </div>
    """),
    unsafe_allow_html=True
    )

    st.markdown("### GENERATED SEQUENCES")

    cols = st.columns(3)

    for i, sample in enumerate(metadata["samples"]):
        col = cols[i % 3]

        with col:
            audio_buffer = render_sine_preview(
                sample,
                bpm=st.session_state.get("display_bpm", 90)
            )
            st.audio(audio_buffer, format="audio/wav")

            events_html = ""

            for event in sample["events"]:
                role_class = "event-role-diatonic" if event.get("active_role") == "diatonic" else ""
                label_class = "event-label-diatonic" if event.get("active_role") == "diatonic" else ""
                events_html += f"""
                <div class="event-block">
                    <div class="event-title">EVENT {event["event_index"] + 1}</div>
                    <div>LABEL: <span class="{label_class}">{event.get("display_label", event.get("roman_numeral", ""))}</span></div>
                    <div>SOURCE: <span class="{label_class}">{event.get("intended_roman_numeral", event.get("roman_numeral", ""))}</span></div>
                    <div>ROLE: <span class="{role_class}">{event.get("active_role", "")}</span></div>
                    <div>TYPE: {event["chord_type"]}</div>
                    <div>SOUND: {event.get("sounded_quality_label", "")}</div>
                    <div>INV: {event["inversion"]}</div>
                    <div>NOTES: {", ".join(event["notes_names"])}</div>
                    <div>MIDI: {event["notes_midi"]}</div>
                    <div>SPAN: {event["voicing_span_semitones"]}</div>
                </div>
                """

            st.markdown(
                f"""
                <div class="sample-card">
                    <div class="sample-index">{i + 1:02d}</div>
                    <div class="sample-id">{sample["sample_id"]}</div>
                    <div class="sample-file">{sample["midi_file"]}</div>
                    {events_html}
                </div>
                """,
                unsafe_allow_html=True
            )