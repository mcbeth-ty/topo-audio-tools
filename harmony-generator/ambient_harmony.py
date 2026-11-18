"""Constrained transformations of ordered Ambient voices."""

from itertools import combinations, product
import random

from midi_generator import midi_note_name


from ambient_audio import TRANSITION_SECONDS


def transformation_candidates(pitches, voices_moved, maximum_movement, low, high, hold_bass_note=False):
    """Enumerate only legal targets; voice indices remain fixed low to high."""
    if not 1 <= voices_moved <= len(pitches) or not 1 <= maximum_movement <= 16:
        raise ValueError("Invalid voice movement settings.")
    eligible_voices = range(1 if hold_bass_note else 0, len(pitches))
    for moving in combinations(eligible_voices, voices_moved):
        options = [
            [note for note in range(max(low, pitch - maximum_movement),
                                    min(high, pitch + maximum_movement) + 1)
             if note != pitch] if index in moving else [pitch]
            for index, pitch in enumerate(pitches)
        ]
        if len(pitches) == 3:
            # Preserve Basic's candidate ordering and sampling behavior exactly.
            for target in product(*options):
                if all(a < b for a, b in zip(target, target[1:])):
                    yield target
        else:
            def ordered_targets(prefix):
                if len(prefix) == len(options):
                    yield tuple(prefix)
                    return
                for note in options[len(prefix)]:
                    if not prefix or note > prefix[-1]:
                        yield from ordered_targets([*prefix, note])
            yield from ordered_targets([])


def build_states(initial_pitches, state_count, maximum_voices_moved, maximum_movement, low, high,
                 hold_bass_note=False):
    if state_count not in (1, 2, 3):
        raise ValueError("Choose one, two, or three harmonic states.")
    if maximum_voices_moved not in (1, 2, 3, 4, 5):
        raise ValueError("Maximum voices moved must be between one and five.")
    pitches = tuple(initial_pitches)
    states = []
    rng = random.Random()
    for index in range(state_count):
        previous = pitches
        if index:
            # Select uniformly among feasible counts, then among legal targets.
            # No arbitrary retries or silent expansion of the maximum.
            feasible = {}
            movable_count = len(previous) - int(hold_bass_note)
            for count in range(1, min(maximum_voices_moved, movable_count) + 1):
                candidates = list(transformation_candidates(
                    previous, count, maximum_movement, low, high, hold_bass_note=hold_bass_note
                ))
                if candidates:
                    feasible[count] = candidates
            if not feasible:
                raise ValueError(
                    f"State {index + 1} is impossible: cannot move 1–{min(maximum_voices_moved, movable_count)} "
                    f"voices by 1–{maximum_movement} semitones within register {low}–{high}. "
                    "Widen the register or change the movement settings."
                )
            actual_count = rng.choice(tuple(feasible))
            pitches = rng.choice(feasible[actual_count])
        displacement = [b - a for a, b in zip(previous, pitches)]
        states.append({
            "state_index": index,
            "notes_midi": list(pitches),
            "notes_names": [midi_note_name(note) for note in pitches],
            "voices": [{"voice_id": voice, "pitch_midi": pitch,
                        "displacement_semitones": displacement[voice]}
                       for voice, pitch in enumerate(pitches)],
            "actual_voices_moved": sum(delta != 0 for delta in displacement),
            "moved_voice_ids": [voice for voice, delta in enumerate(displacement) if delta],
            "common_tone_count": len(set(previous) & set(pitches)) if index else None,
            "retained_voice_count": sum(a == b for a, b in zip(previous, pitches)) if index else None,
            "total_voice_leading_distance": sum(abs(delta) for delta in displacement),
            "intervals_above_lowest_semitones": [pitch - pitches[0] for pitch in pitches],
        })
    return states


def time_states(states, duration):
    """Attach proportional timing to a copied metadata sequence."""
    transitions = []
    for index, state in enumerate(states):
        state["start_seconds"] = duration * index / len(states)
        state["end_seconds"] = duration * (index + 1) / len(states)
        if index:
            midpoint = state["start_seconds"]
            transitions.append({
                "from_state": index - 1, "to_state": index,
                "time_seconds": midpoint,
                "overlap_start_seconds": midpoint - TRANSITION_SECONDS / 2,
                "overlap_end_seconds": midpoint + TRANSITION_SECONDS / 2,
            })
    return transitions
