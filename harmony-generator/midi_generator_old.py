import pretty_midi
import random
import os
import json
from datetime import datetime

def generate_sequences(
    sequence_count,
    beats_per_bar,
    bars,
    harmonic_events,
    tonic,
    mode,
    register_low,
    register_high,
    scale_degree_weights,
    chord_type_weights,
    inversion_weights,
    run_name,
    bpm
):
    current_scale = scales[mode]

    total_beats = beats_per_bar * bars
    beats_per_event = total_beats / harmonic_events

    duration_seconds = total_beats * (60 / bpm)

    temporal_scale_metadata = classify_temporal_integration_scale(duration_seconds)

    print("generate_sequences function is running")
    # -----------------------------------
    # CREATE MIDI
    # -----------------------------------

    run_metadata = {
        "generator_version": "v1",
        "created_at": datetime.now().isoformat(),
        "run_name": run_name,
        "global_settings": {
            "mode": mode,
            "tonic_midi": tonic,
            "harmonic_events": harmonic_events,
            "bars": bars,
            "beats_per_bar": beats_per_bar,
            "bpm": bpm,
            "duration_beats": total_beats,
            "duration_seconds": duration_seconds,
            **temporal_scale_metadata,
            "register_low": register_low,
            "register_high": register_high,
            "scale_name": mode,
            "scale_intervals": current_scale,
        },
            "samples": []
    }

    for sequence_index in range(sequence_count):

        midi = pretty_midi.PrettyMIDI()
        instrument = pretty_midi.Instrument(program=0)
        sequence_events = []

        for event_index in range(harmonic_events):

            chord_metadata = build_chord(
                tonic=tonic,
                current_scale=current_scale,
                register_low=register_low,
                register_high=register_high,
                scale_degree_weights=scale_degree_weights,
                chord_type_weights=chord_type_weights,
                inversion_weights=inversion_weights,
                mode=mode,
            )

            chord_notes = chord_metadata["notes_midi"]

            start_time = event_index * beats_per_event
            end_time = start_time + beats_per_event

            event_metadata = {
            "event_index": event_index,
            "start_beat": start_time,
            "end_beat": end_time,
            "duration_beats": beats_per_event,
            **chord_metadata
            }

            sequence_events.append(event_metadata)

            print("Event:", event_index)
            print("Start:", start_time)
            print("End:", end_time)

           
            
            for pitch in chord_notes:

                note = pretty_midi.Note(
                    velocity=100,
                    pitch=pitch,
                    start=start_time,
                    end=end_time
                )

                instrument.notes.append(note)

        midi.instruments.append(instrument)
        filename = f"{run_name}_{sequence_index + 1:02d}.mid"
        sample_id = f"{run_name}_{sequence_index + 1:02d}"

        scale_degree_sequence = [
            event["scale_degree"]
            for event in sequence_events
        ]

        roman_numeral_sequence = [
            event["roman_numeral"]
            for event in sequence_events
        ]

        sample_metadata = {
            "sample_id": sample_id,
            "midi_file": filename,
            "audio_file": None,
            "sequence_index": sequence_index,
            "events": sequence_events,
            "scale_degree_sequence": scale_degree_sequence,
            "roman_numeral_sequence": roman_numeral_sequence,    
        }

        run_metadata["samples"].append(sample_metadata)
        
        print("Created:", filename)

        print("Generated progression MIDI created!")

    return run_metadata


# -----------------------------------
# SETTINGS
# -----------------------------------

scales = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10]
}

scale_degrees = [0, 1, 2, 3, 4, 5, 6]
inversion_options = ["root", "first", "second"]


def midi_note_name(midi_note):
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    pitch_class = midi_note % 12
    octave = (midi_note // 12) - 1

    return f"{note_names[pitch_class]}{octave}"

def classify_temporal_integration_scale(duration_seconds):
    if duration_seconds < 3:
        return {
            "temporal_integration_scale": "Micro Scale",
            "temporal_integration_window_seconds": [0.5, 3],
            "temporal_integration_scale_description": (
                "Local perceptual responses and immediate harmonic qualities before substantial higher-order emotional narratives emerge."
            )
        }

    elif duration_seconds < 10:
        return {
            "temporal_integration_scale": "Local Scale",
            "temporal_integration_window_seconds": [3, 10],
            "temporal_integration_scale_description": (
                "Short perceptual trajectories and simple affective contours."
            )
        }

    elif duration_seconds < 30:
        return {
            "temporal_integration_scale": "Phrase Scale",
            "temporal_integration_window_seconds": [10, 30],
            "temporal_integration_scale_description": (
                "Extended affective gestures and the emergence of higher-order emotional organization."
            )
        }

    else:
        return {
            "temporal_integration_scale": "Extended Scale",
            "temporal_integration_window_seconds": [30, None],
            "temporal_integration_scale_description": (
                "Sustained emotional worlds, narratives, and larger-scale affective development."
            )
        }

def roman_numeral_for_degree(scale_degree, mode, chord_type):
    major_romans = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
    minor_romans = ["i", "ii°", "III", "iv", "v", "VI", "VII"]

    if mode == "major":
        roman = major_romans[scale_degree - 1]
    else:
        roman = minor_romans[scale_degree - 1]

    if chord_type == "dyad":
        roman += "(dyad)"

    return roman

# -----------------------------------
# BUILD CHORD
# -----------------------------------

def build_chord(
    tonic,
    current_scale,
    mode,
    register_low,
    register_high,
    scale_degree_weights,
    chord_type_weights,
    inversion_weights
):

    scale_degree = random.choices(
        scale_degrees,
        weights=scale_degree_weights
    )[0]

    root_index = scale_degree
    third_index = scale_degree + 2
    fifth_index = scale_degree + 4

    root_pitch_class = (tonic + current_scale[root_index % 7]) % 12

    possible_roots = []

    for midi_note in range(register_low, register_high + 1):
        if midi_note % 12 == root_pitch_class:
            possible_roots.append(midi_note)

    root = random.choice(possible_roots)

    third = root + (
        current_scale[third_index % 7]
        - current_scale[root_index % 7]
        + (third_index // 7) * 12
    )

    fifth = root + (
        current_scale[fifth_index % 7]
        - current_scale[root_index % 7]
        + (fifth_index // 7) * 12
    )

    chord_type = random.choices(
        ["dyad", "triad"],
        weights=chord_type_weights
    )[0]

    if chord_type == "triad":

        inversion = random.choices(
            inversion_options,
            weights=inversion_weights
        )[0]

        if inversion == "root":
            chord_notes = [root, third, fifth]

        elif inversion == "first":
            chord_notes = [third, fifth, root + 12]

        else:
            chord_notes = [fifth, root + 12, third + 12]

    else:

        inversion = "none"

        dyad_type = random.choice(["third", "fifth"])

        if dyad_type == "third":
            chord_notes = [root, third]

        else:
            chord_notes = [root, fifth]

    print("Scale degree:", scale_degree)
    print("Chord type:", chord_type)
    print("Inversion:", inversion)
    print("Chord notes:", chord_notes)

    chord_metadata = {
    "scale_degree": scale_degree + 1,
    "roman_numeral": roman_numeral_for_degree(scale_degree + 1, mode, chord_type),
    "chord_type": chord_type,
    "dyad_type": dyad_type if chord_type == "dyad" else None,
    "inversion": inversion,
    "notes_midi": chord_notes,
    "notes_names": [midi_note_name(note) for note in chord_notes],
    "bass_note_midi": chord_notes[0],
    "bass_note_name": midi_note_name(chord_notes[0]),
    "root_note_midi": root,
    "root_note_name": midi_note_name(root),
    "voicing_span_semitones": max(chord_notes) - min(chord_notes)
    }

    return chord_metadata




# generate_sequences(
#     sequence_count=5,
#     beats_per_bar=4,
#     bars=2,
#     harmonic_events=2,
#     tonic=60,
#     mode="major",
#     register_low=48,
#     register_high=72,
#     scale_degree_weights=[20, 5, 10, 20, 20, 20, 5],
#     chord_type_weights=[50, 50],
#     inversion_weights=[70, 20, 10]
# )