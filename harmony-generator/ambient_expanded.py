"""Structured Ambient starting collections; Diatonic Basic keeps its legacy sampler."""

from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
import random

from midi_generator import midi_note_name

FAMILIES = ("All", "Triadic", "Seventh", "Suspended/Added", "Quartal/Interval-based")
# Priority order retains the root and defining color when three voices require
# omitting the fifth. The full intended collection is also recorded.
TEMPLATES = {
    "Triadic": (("major triad", (0, 4, 7)), ("minor triad", (0, 3, 7))),
    "Seventh": (("major seventh", (0, 4, 11, 7)),
                ("minor seventh", (0, 3, 10, 7)),
                ("dominant seventh", (0, 4, 10, 7))),
    "Suspended/Added": (("suspended second", (0, 2, 7)),
                        ("suspended fourth", (0, 5, 7)),
                        ("added second", (0, 4, 2, 7)),
                        ("added ninth", (0, 4, 14, 7)),
                        ("minor added ninth", (0, 3, 14, 7))),
    "Quartal/Interval-based": (("quartal stack", (0, 5, 10)),
                               ("fourth stack", (0, 5, 10, 15)),
                               ("fifth stack", (0, 7, 14))),
}


def eligible_voicings(root_pc, intervals, voice_count, low, high):
    """Cover every selected harmonic tone; extras may only double its octave."""
    required = {(root_pc + interval) % 12 for interval in intervals}
    pool = [note for note in range(low, high + 1) if note % 12 in required]
    # Bound spread to two octaves for useful, tractable exploratory voicings.
    for bass_index, bass in enumerate(pool):
        upper = [note for note in pool[bass_index + 1:] if note <= bass + 24]
        for rest in combinations(upper, voice_count - 1):
            notes = (bass, *rest)
            if {note % 12 for note in notes} == required:
                yield notes


def generate_expanded(tonic, mode, low, high, voice_count=4, family="All", generation_framework="diatonic"):
    if generation_framework not in ("diatonic", "chromatic"):
        raise ValueError("Choose Diatonic or Chromatic generation.")
    chromatic = generation_framework == "chromatic"
    if voice_count not in (2, 3, 4, 5) or family not in FAMILIES or (not chromatic and mode not in ("major", "minor")):
        raise ValueError("Invalid Expanded vocabulary settings.")
    if not 0 <= low <= high <= 127:
        raise ValueError("Choose a valid MIDI register.")
    scale = tuple(range(12)) if chromatic else ((0, 2, 4, 5, 7, 9, 11) if mode == "major" else (0, 2, 3, 5, 7, 8, 10))
    groups = FAMILIES[1:] if family == "All" else (family,)
    eligible = {}
    for group in groups:
        templates = []
        for name, full_intervals in TEMPLATES[group]:
            selected = full_intervals[:voice_count]
            roots = []
            for degree, offset in enumerate(scale, 1):
                root_pc = offset if chromatic else (tonic + offset) % 12
                # Check feasibility without retaining the full voicing catalog.
                if next(eligible_voicings(root_pc, selected, voice_count, low, high), None) is not None:
                    roots.append((degree, offset, root_pc))
            if roots:
                templates.append((name, full_intervals, selected, roots))
        if templates:
            eligible[group] = templates
    if not eligible:
        raise ValueError("No Expanded sonority fits this voice count and register. Widen the register.")
    rng = random.Random()
    group = rng.choice(tuple(eligible))
    if chromatic:
        # Root probability is independent of how many templates implement it.
        root_pc = rng.choice(sorted({root[2] for template in eligible[group] for root in template[3]}))
        name, full, selected, roots = rng.choice([
            template for template in eligible[group] if any(root[2] == root_pc for root in template[3])
        ])
        degree, offset = None, None
    else:
        # Keep the original Diatonic sampling order and weights unchanged.
        name, full, selected, roots = rng.choice(eligible[group])
        degree, offset, root_pc = rng.choice(roots)
    notes = rng.choice(list(eligible_voicings(root_pc, selected, voice_count, low, high)))
    counts = Counter(note % 12 for note in notes)
    doublings = [{"pitch_class": pc, "notes_midi": [note for note in notes if note % 12 == pc],
                  "extra_voices": count - 1} for pc, count in sorted(counts.items()) if count > 1]
    root_name = midi_note_name(root_pc + 60)[:-1]
    omitted = sorted(set(full) - set(selected))
    # Interval structures are described literally, without a functional chord label.
    label = f"{root_name} {name}" + (" (fifth omitted)" if omitted and group != "Quartal/Interval-based" else "")
    if voice_count == 2:
        label = f"{root_name} two-tone subset of {name} (intervals {', '.join(map(str,selected))})"
    bass_interval = (notes[0] - root_pc) % 12
    inversion = sorted({interval % 12 for interval in selected}).index(bass_interval)
    voicing = f"{'Root' if inversion == 0 else f'Tone {inversion + 1}'} in bass; "
    voicing += f"{'open' if notes[-1] - notes[0] > 12 else 'close'} voicing"
    chord = {
        "display_label": label, "roman_numeral": None, "intended_roman_numeral": None,
        "intended_quality": name, "sonority_type": name, "harmonic_family": group,
        "chord_type": "sonority", "notes_midi": list(notes),
        "notes_names": [midi_note_name(note) for note in notes],
        "voice_count": voice_count, "root_pitch_class": root_pc,
        "root_degree": None, "root_semitone": offset,
        "template_intervals_from_root": list(full),
        "selected_harmonic_intervals": list(selected), "omitted_intervals": omitted,
        "distinct_pitch_class_count": len(counts), "octave_doublings": doublings,
        "bass_note_midi": notes[0], "bass_note_name": midi_note_name(notes[0]),
        "root_note_midi": next(note for note in notes if note % 12 == root_pc),
        "voicing_span_semitones": notes[-1] - notes[0],
        "inversion": inversion, "bass_interval_from_root": bass_interval,
        "voicing_description": voicing,
        "construction": {"reference": "chromatic root pitch class" if chromatic else "root on selected mode's scale degree",
                         "scale_degree": degree, "scale_offsets": None if chromatic else list(scale),
                         "intervals_semitones": list(full),
                         "voicing_policy": "all selected pitch classes, octave displacements, span <= 24 semitones"},
    }
    return {
        "generation_mode": "ambient", "generation_framework": generation_framework,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_settings": {"harmonic_vocabulary": "Expanded", "generation_framework": generation_framework,
                               "tonic_midi": None if chromatic else tonic,
                               "modal_preset": None if chromatic else mode, "register_low": low, "register_high": high,
                               "voice_count": voice_count, "harmonic_family": family,
                               "sampling_policy": ("uniform eligible family, then chromatic root, then eligible template, then voicing" if chromatic
                                                   else "uniform eligible family, then template, then modal root, then voicing")},
        "chord": chord,
    }



def generate_chromatic_basic(low, high):
    """Basic closed root-position major/minor triads, without any external key.

    Uniform eligible pitch class, then eligible quality, then octave placement.
    In a narrow register, only roots/qualities with a complete fitting triad enter
    the draw. Multiple octave placements never increase a root's probability.
    """
    if not 0 <= low <= high <= 127:
        raise ValueError("Choose a valid MIDI register.")
    eligible = {}
    for pc in range(12):
        templates = []
        for name, intervals in TEMPLATES["Triadic"]:
            roots = [note for note in range(low, high - max(intervals) + 1) if note % 12 == pc]
            if roots:
                templates.append((name, intervals, roots))
        if templates:
            eligible[pc] = templates
    if not eligible:
        raise ValueError("This register cannot contain a Chromatic Basic triad. Widen it.")
    rng = random.Random()
    pc = rng.choice(tuple(eligible))
    name, intervals, roots = rng.choice(eligible[pc])
    root = rng.choice(roots)
    notes = [root + interval for interval in intervals]
    chord = {
        "display_label": f"{midi_note_name(pc + 60)[:-1]} {name}",
        "roman_numeral": None, "intended_roman_numeral": None,
        "intended_quality": name.split()[0], "sonority_type": name,
        "harmonic_family": "Triadic", "chord_type": "triad", "is_full_triad": True,
        "voice_count": 3, "notes_midi": notes,
        "notes_names": [midi_note_name(note) for note in notes],
        "root_pitch_class": pc, "root_degree": None, "root_semitone": None,
        "root_note_midi": root, "root_note_name": midi_note_name(root),
        "bass_note_midi": root, "bass_note_name": midi_note_name(root),
        "inversion": "root", "voicing_description": "Root-position close triad",
        "triad_intervals_from_root": list(intervals),
        "template_intervals_from_root": list(intervals),
        "selected_harmonic_intervals": list(intervals), "sounded_intervals_from_root": list(intervals),
        "voicing_span_semitones": max(intervals), "distinct_pitch_class_count": 3,
        "octave_doublings": [], "omitted_intervals": [],
        "construction": {"reference": "chromatic root pitch class", "intervals_semitones": list(intervals)},
    }
    return {"generation_mode": "ambient", "generation_framework": "chromatic",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "selection_settings": {"harmonic_vocabulary": "Basic", "generation_framework": "chromatic",
                                   "tonic_midi": None, "modal_preset": None,
                                   "register_low": low, "register_high": high,
                                   "chord_type_weights": [0, 100], "inversion_weights": [100, 0, 0],
                                   "sampling_policy": "uniform eligible chromatic root, then major/minor quality, then octave placement"},
            "chord": chord}


def framework_description(metadata):
    """Read-only interpretation of legacy context; never rewrite old records."""
    selected = metadata.get("selection_settings", {})
    explicit = selected.get("generation_framework") or metadata.get("generation_framework")
    if explicit in ("diatonic", "chromatic", "chord_targeting"):
        return explicit
    chord = metadata.get("chord", {})
    has_context = isinstance(selected.get("tonic_midi"), int) and selected.get("modal_preset") in ("major", "minor")
    known_sampler = (chord.get("construction", {}).get("reference") == "root on selected mode's scale degree"
                     or (chord.get("active_role") == "diatonic" and "field_weights" in selected))
    return "diatonic (legacy metadata)" if has_context and known_sampler else "legacy/unknown"
