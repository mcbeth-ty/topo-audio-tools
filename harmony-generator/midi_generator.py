import random
from datetime import datetime

import pretty_midi


# -----------------------------------------------------------------------------
# 48-object harmonic field
# -----------------------------------------------------------------------------
# Each harmonic object is a chromatic root relative to the tonic plus an intended
# triad quality. Dyads are generated from these source objects, but exported with
# separate sounded labels so Topology Explorer does not mistake a partial dyad for
# a full triad.

ROOTS = [
    {"root_degree": "I", "root_semitone": 0},
    {"root_degree": "♭II", "root_semitone": 1},
    {"root_degree": "II", "root_semitone": 2},
    {"root_degree": "♭III", "root_semitone": 3},
    {"root_degree": "III", "root_semitone": 4},
    {"root_degree": "IV", "root_semitone": 5},
    {"root_degree": "♭V", "root_semitone": 6},
    {"root_degree": "V", "root_semitone": 7},
    {"root_degree": "♭VI", "root_semitone": 8},
    {"root_degree": "VI", "root_semitone": 9},
    {"root_degree": "♭VII", "root_semitone": 10},
    {"root_degree": "VII", "root_semitone": 11},
]

QUALITY_DEFINITIONS = {
    "major": {"third": 4, "fifth": 7, "case": "upper", "suffix": ""},
    "minor": {"third": 3, "fifth": 7, "case": "lower", "suffix": ""},
    "diminished": {"third": 3, "fifth": 6, "case": "lower", "suffix": "°"},
    "augmented": {"third": 4, "fifth": 8, "case": "upper", "suffix": "+"},
}

MAJOR_DIATONIC = {"I", "ii", "iii", "IV", "V", "vi", "vii°"}
MINOR_DIATONIC = {"i", "ii°", "♭III", "iv", "v", "♭VI", "♭VII"}

# Extra common borrowing options. This intentionally includes the Neapolitan even
# though it is not part of natural minor. It behaves well as a first-pass
# "parallel / modal borrowing" object in a major-key preset.
MAJOR_COMMON_BORROWED = {"i", "♭II", "ii°", "♭III", "iv", "v", "♭VI", "♭VII"}

# In minor, the major-key diatonic set usefully captures the common raised-third
# dominant adjustment too: V and vii° are especially important.
MINOR_COMMON_BORROWED = {"I", "ii", "iii", "IV", "V", "vi", "vii°", "♭II"}

TRIAD_INVERSION_OPTIONS = ["root", "first", "second"]
DYAD_OPTIONS = ["root_third", "root_fifth"]


def roman_for_root_quality(root_degree, quality):
    if quality in ("minor", "diminished"):
        roman = root_degree.lower()
    else:
        roman = root_degree

    return f"{roman}{QUALITY_DEFINITIONS[quality]['suffix']}"


def build_harmonic_field():
    field = []

    for root in ROOTS:
        for quality in ["major", "minor", "diminished", "augmented"]:
            roman = roman_for_root_quality(root["root_degree"], quality)

            if roman in MAJOR_DIATONIC:
                major_role = "diatonic"
            elif roman in MAJOR_COMMON_BORROWED:
                major_role = "parallel_borrowing"
            elif quality in ("major", "minor"):
                major_role = "uncommon_1"
            else:
                major_role = "uncommon_2"

            if roman in MINOR_DIATONIC:
                minor_role = "diatonic"
            elif roman in MINOR_COMMON_BORROWED:
                minor_role = "parallel_borrowing"
            elif quality in ("major", "minor"):
                minor_role = "uncommon_1"
            else:
                minor_role = "uncommon_2"

            field.append({
                "roman_numeral": roman,
                "root_degree": root["root_degree"],
                "root_semitone": root["root_semitone"],
                "quality": quality,
                "triad_intervals_from_root": [
                    0,
                    QUALITY_DEFINITIONS[quality]["third"],
                    QUALITY_DEFINITIONS[quality]["fifth"],
                ],
                "major_preset_role": major_role,
                "minor_preset_role": minor_role,
            })

    return field


HARMONIC_FIELD = build_harmonic_field()


def build_probability_field(
    modal_preset,
    diatonic_weight,
    parallel_borrowing_weight,
    uncommon_1_weight,
    uncommon_2_weight,
    diatonic_object_weights=None,
):
    role_key = f"{modal_preset}_preset_role"
    role_weights = {
        "diatonic": diatonic_weight,
        "parallel_borrowing": parallel_borrowing_weight,
        "uncommon_1": uncommon_1_weight,
        "uncommon_2": uncommon_2_weight,
    }

    # Optional per-object weights for the seven active diatonic objects.
    # These preserve the large category slider while letting each diatonic
    # Roman numeral lean slightly stronger or weaker inside that category.
    diatonic_object_weights = diatonic_object_weights or {}

    weighted_field = []

    for item in HARMONIC_FIELD:
        role = item[role_key]
        weight = role_weights.get(role, 0)

        if role == "diatonic":
            object_weight = diatonic_object_weights.get(item["roman_numeral"], 100)
            weight = weight * (object_weight / 100)

        weighted_item = dict(item)
        weighted_item["active_preset"] = modal_preset
        weighted_item["active_role"] = role
        weighted_item["weight"] = weight
        weighted_item["diatonic_object_weight"] = (
            diatonic_object_weights.get(item["roman_numeral"], None)
            if role == "diatonic"
            else None
        )
        weighted_field.append(weighted_item)

    return weighted_field

# -----------------------------------------------------------------------------
# Public generation function
# -----------------------------------------------------------------------------

def generate_sequences(
    sequence_count,
    beats_per_bar,
    bars,
    harmonic_events,
    tonic,
    mode,
    register_low,
    register_high,
    chord_type_weights,
    inversion_weights,
    run_name,
    bpm,
    diatonic_weight=100,
    parallel_borrowing_weight=0,
    uncommon_1_weight=0,
    uncommon_2_weight=0,
    diatonic_object_weights=None,
):
    total_beats = beats_per_bar * bars
    beats_per_event = total_beats / harmonic_events
    duration_seconds = total_beats * (60 / bpm)
    temporal_scale_metadata = classify_temporal_integration_scale(duration_seconds)

    probability_field = build_probability_field(
        modal_preset=mode,
        diatonic_weight=diatonic_weight,
        parallel_borrowing_weight=parallel_borrowing_weight,
        uncommon_1_weight=uncommon_1_weight,
        uncommon_2_weight=uncommon_2_weight,
        diatonic_object_weights=diatonic_object_weights,
    )

    active_labels = [item["roman_numeral"] for item in probability_field if item["weight"] > 0]

    run_metadata = {
        "generator_version": "v2_probability_field",
        "created_at": datetime.now().isoformat(),
        "run_name": run_name,
        "global_settings": {
            "mode": mode,
            "modal_preset": mode,
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
            "harmonic_field_size": len(HARMONIC_FIELD),
            "active_harmonic_labels": active_labels,
            "field_weights": {
                "diatonic": diatonic_weight,
                "parallel_borrowing": parallel_borrowing_weight,
                "uncommon_1": uncommon_1_weight,
                "uncommon_2": uncommon_2_weight,
            },
            "diatonic_object_weights": diatonic_object_weights or {},
            "chord_type_weights": {
                "dyad": chord_type_weights[0],
                "triad": chord_type_weights[1],
            },
        },
        "harmonic_probability_field": probability_field,
        "samples": [],
    }

    for sequence_index in range(sequence_count):
        sequence_events = []

        for event_index in range(harmonic_events):
            chord_metadata = build_chord(
                tonic=tonic,
                register_low=register_low,
                register_high=register_high,
                probability_field=probability_field,
                chord_type_weights=chord_type_weights,
                inversion_weights=inversion_weights,
            )

            start_time = event_index * beats_per_event
            end_time = start_time + beats_per_event

            event_metadata = {
                "event_index": event_index,
                "start_beat": start_time,
                "end_beat": end_time,
                "duration_beats": beats_per_event,
                **chord_metadata,
            }

            sequence_events.append(event_metadata)

        filename = f"{run_name}_{sequence_index + 1:02d}.mid"
        sample_id = f"{run_name}_{sequence_index + 1:02d}"

        sample_metadata = {
            "sample_id": sample_id,
            "midi_file": filename,
            "audio_file": None,
            "sequence_index": sequence_index,
            "events": sequence_events,
            "roman_numeral_sequence": [event["roman_numeral"] for event in sequence_events],
            "display_label_sequence": [event["display_label"] for event in sequence_events],
            "intended_roman_numeral_sequence": [
                event["intended_roman_numeral"] for event in sequence_events
            ],
            "root_degree_sequence": [event["root_degree"] for event in sequence_events],
            "root_semitone_sequence": [event["root_semitone"] for event in sequence_events],
            "quality_sequence": [event["intended_quality"] for event in sequence_events],
        }

        run_metadata["samples"].append(sample_metadata)

    return run_metadata


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------

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
            ),
        }

    if duration_seconds < 10:
        return {
            "temporal_integration_scale": "Local Scale",
            "temporal_integration_window_seconds": [3, 10],
            "temporal_integration_scale_description": (
                "Short perceptual trajectories and simple affective contours."
            ),
        }

    if duration_seconds < 30:
        return {
            "temporal_integration_scale": "Phrase Scale",
            "temporal_integration_window_seconds": [10, 30],
            "temporal_integration_scale_description": (
                "Extended affective gestures and the emergence of higher-order emotional organization."
            ),
        }

    return {
        "temporal_integration_scale": "Extended Scale",
        "temporal_integration_window_seconds": [30, None],
        "temporal_integration_scale_description": (
            "Sustained emotional worlds, narratives, and larger-scale affective development."
        ),
    }


def find_root_in_register(tonic, root_semitone, register_low, register_high):
    target_pitch_class = (tonic + root_semitone) % 12
    possible_roots = [
        midi_note
        for midi_note in range(register_low, register_high + 1)
        if midi_note % 12 == target_pitch_class
    ]

    if possible_roots:
        return random.choice(possible_roots)

    # Fallback for very narrow ranges. Choose the closest octave placement, then
    # clamp into a musically usable neighborhood rather than failing.
    root = tonic + root_semitone
    while root < register_low:
        root += 12
    while root > register_high:
        root -= 12
    return root


def describe_sounded_dyad(source_chord, dyad_type):
    quality = source_chord["quality"]
    root_degree = source_chord["root_degree"]
    intended = source_chord["roman_numeral"]

    third_interval = QUALITY_DEFINITIONS[quality]["third"]
    fifth_interval = QUALITY_DEFINITIONS[quality]["fifth"]

    if dyad_type == "root_third":
        if third_interval == 4:
            return {
                "sounded_quality_label": "major_third_dyad",
                "display_label": f"{root_degree}(M3 dyad)",
                "dyad_interval_name": "major third",
            }
        return {
            "sounded_quality_label": "minor_third_dyad",
            "display_label": f"{root_degree.lower()}(m3 dyad)",
            "dyad_interval_name": "minor third",
        }

    if fifth_interval == 6:
        return {
            "sounded_quality_label": "diminished_fifth_dyad",
            "display_label": f"{intended}(no3)",
            "dyad_interval_name": "diminished fifth",
        }

    if fifth_interval == 8:
        return {
            "sounded_quality_label": "augmented_fifth_dyad",
            "display_label": f"{intended}(no3)",
            "dyad_interval_name": "augmented fifth",
        }

    return {
        "sounded_quality_label": "perfect_fifth_dyad",
        "display_label": f"{root_degree}(P5 dyad)",
        "dyad_interval_name": "perfect fifth",
    }


# -----------------------------------------------------------------------------
# Chord construction
# -----------------------------------------------------------------------------

def build_chord(
    tonic,
    register_low,
    register_high,
    probability_field,
    chord_type_weights,
    inversion_weights,
):
    source_chord = random.choices(
        probability_field,
        weights=[item["weight"] for item in probability_field],
    )[0]

    quality = source_chord["quality"]
    quality_def = QUALITY_DEFINITIONS[quality]

    root = find_root_in_register(
        tonic=tonic,
        root_semitone=source_chord["root_semitone"],
        register_low=register_low,
        register_high=register_high,
    )

    third = root + quality_def["third"]
    fifth = root + quality_def["fifth"]

    chord_type = random.choices(
        ["dyad", "triad"],
        weights=chord_type_weights,
    )[0]

    if chord_type == "triad":
        inversion = random.choices(
            TRIAD_INVERSION_OPTIONS,
            weights=inversion_weights,
        )[0]
        dyad_type = None
        sounded_intervals = [0, quality_def["third"], quality_def["fifth"]]
        sounded_quality_label = quality
        display_label = source_chord["roman_numeral"]

        if inversion == "root":
            chord_notes = [root, third, fifth]
        elif inversion == "first":
            chord_notes = [third, fifth, root + 12]
        else:
            chord_notes = [fifth, root + 12, third + 12]

    else:
        inversion = "none"
        dyad_type = random.choice(DYAD_OPTIONS)

        if dyad_type == "root_third":
            chord_notes = [root, third]
            sounded_intervals = [0, quality_def["third"]]
        else:
            chord_notes = [root, fifth]
            sounded_intervals = [0, quality_def["fifth"]]

        dyad_description = describe_sounded_dyad(source_chord, dyad_type)
        sounded_quality_label = dyad_description["sounded_quality_label"]
        display_label = dyad_description["display_label"]

    chord_metadata = {
        # Primary display/export labels
        "roman_numeral": display_label,
        "display_label": display_label,

        # Source harmonic object sampled from the 48-object field
        "intended_roman_numeral": source_chord["roman_numeral"],
        "intended_quality": quality,
        "root_degree": source_chord["root_degree"],
        "root_semitone": source_chord["root_semitone"],
        "triad_intervals_from_root": source_chord["triad_intervals_from_root"],
        "active_preset": source_chord["active_preset"],
        "active_role": source_chord["active_role"],
        "source_weight": source_chord["weight"],

        # Sounded object, which may be a partial dyad rather than a full triad
        "chord_type": chord_type,
        "dyad_type": dyad_type,
        "inversion": inversion,
        "sounded_intervals_from_root": sounded_intervals,
        "sounded_quality_label": sounded_quality_label,
        "is_full_triad": chord_type == "triad",

        # Voicing / audio notes
        "notes_midi": chord_notes,
        "notes_names": [midi_note_name(note) for note in chord_notes],
        "bass_note_midi": chord_notes[0],
        "bass_note_name": midi_note_name(chord_notes[0]),
        "root_note_midi": root,
        "root_note_name": midi_note_name(root),
        "voicing_span_semitones": max(chord_notes) - min(chord_notes),
    }

    return chord_metadata
