import pretty_midi
import random

# -----------------------------------
# SETTINGS
# -----------------------------------

sequence_count = 5

beats_per_bar = 4
bars = 2
harmonic_events = 2
tempo = 90

total_beats = beats_per_bar * bars
beats_per_event = total_beats / harmonic_events

tonic = 60  # C4
register_low = 48   # C3
register_high = 72  # C5

mode = "major"

scales = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10]
}

current_scale = scales[mode]

scale_degrees = [0, 1, 2, 3, 4, 5, 6]
scale_degree_weights = [20, 10, 10, 20, 20, 20, 5]
inversion_options = ["root", "first", "second"]
inversion_weights = [70, 20, 10]

# -----------------------------------
# BUILD CHORD
# -----------------------------------

def build_chord():

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
        weights=[50, 50]
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

    return chord_notes


# -----------------------------------
# CREATE MIDI
# -----------------------------------
for sequence_index in range(sequence_count):

    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)

    for event_index in range(harmonic_events):

        chord_notes = build_chord()

        start_time = event_index * beats_per_event
        end_time = start_time + beats_per_event

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
    filename = f"generated_progression_{sequence_index + 1}.mid"
    midi.write(filename)
    print("Created:", filename)

    print("Generated progression MIDI created!")