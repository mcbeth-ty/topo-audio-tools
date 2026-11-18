"""Chord identities first, constrained deterministic voice leading second.

No rendering or persistence code. Existing templates/voicings are authoritative.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from pathlib import Path
import random

from ambient_expanded import FAMILIES, TEMPLATES, eligible_voicings
from midi_generator import midi_note_name

VERSION = "ambient_chord_targeting_v1"
SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
RELATIONSHIPS = ("Diatonic Relationships", "Chromatic Relationships", "Common-Tone Relationships",
                 "Mixed", "Unrestricted Chord Targets")
QUALITY_BALANCES = ("Balanced", "Favor Major", "Favor Minor", "Original Vocabulary Weights")
MIXED_PROBABILITIES = dict.fromkeys(RELATIONSHIPS[:3], 1 / 3)
QUALITY_FACTORS = {"Balanced": {"major": 1, "minor": 1, "other": 1},
                   "Favor Major": {"major": 3, "minor": 1, "other": 1},
                   "Favor Minor": {"major": 1, "minor": 3, "other": 1}}
CHROMATIC_ROOT_SHIFTS = (0, 1, 3, 4, 6, 8, 9, 11)
MAX_INITIAL_ATTEMPTS = 8
COST_POLICY = ("total absolute displacement", "most unchanged voice pitches", "most exact common tones",
               "smallest maximum leap", "smallest voicing span", "lexicographically lowest MIDI pitches")


@dataclass(frozen=True)
class Target:
    family: str
    name: str
    root: int
    full: tuple
    selected: tuple
    quality: str
    voicings: tuple

    @property
    def pcs(self):
        return frozenset((self.root + interval) % 12 for interval in self.selected)

    @property
    def full_pcs(self):
        return frozenset((self.root + interval) % 12 for interval in self.full)

    @property
    def identity(self):
        return f"{self.family}:{self.name}:root={self.root}:intervals={','.join(map(str,self.selected))}"


def quality(name):
    if name.startswith("minor"): return "minor"
    if name.startswith(("major", "dominant", "added")): return "major"
    return "other"


@lru_cache(maxsize=8)
def catalog(vocabulary, voice_count, family, low, high):
    if vocabulary not in ("Basic", "Expanded") or family not in FAMILIES:
        raise ValueError("Invalid Chord Targeting vocabulary/family.")
    if (voice_count not in (2, 3, 4, 5) or not 0 <= low <= high <= 127
            or vocabulary == "Basic" and voice_count != 3):
        raise ValueError("Invalid Chord Targeting voice count/register; Basic requires three voices.")
    groups = ("Triadic",) if vocabulary == "Basic" else FAMILIES[1:] if family == "All" else (family,)
    targets = []
    for group in groups:
        for name, full in TEMPLATES[group]:
            selected = full[:voice_count]
            for root in range(12):
                if vocabulary == "Basic":
                    voicings = tuple(tuple(bass + interval for interval in full)
                                     for bass in range(low, high - max(full) + 1) if bass % 12 == root)
                else:
                    voicings = tuple(eligible_voicings(root, selected, voice_count, low, high))
                if voicings: targets.append(Target(group, name, root, full, selected, quality(name), voicings))
    return tuple(targets)


def sampling_weights(targets, balance):
    """Equal family/root mass; balance quality-category mass within each root.

    Original = equal templates, matching the existing Chromatic hierarchy.
    Other presets: major/minor/neutral category masses 1:1:1, 3:1:1 or 1:3:1.
    Absent categories are omitted. Neutral-only families are unaffected.
    """
    groups = {target.family for target in targets}
    weights = []
    for target in targets:
        roots = {t.root for t in targets if t.family == target.family}
        peers = [t for t in targets if (t.family,t.root) == (target.family,target.root)]
        counts = Counter(t.quality for t in peers)
        conditional = (1 / len(peers) if balance == "Original Vocabulary Weights" else
                       QUALITY_FACTORS[balance][target.quality] / counts[target.quality]
                       / sum(QUALITY_FACTORS[balance][category] for category in counts))
        weights.append(conditional / len(groups) / len(roots))
    return weights


def sampling_table(targets, weights):
    return [{"target": t.identity, "quality_category": t.quality, "probability": w}
            for t, w in zip(targets, weights)]


def collections_for(target):
    # Major and natural minor contexts are explicit plausible local contexts,
    # not claims that the stimulus established a tonic. Use the full template.
    return tuple((root, mode) for root in range(12) for mode, scale in
                 (("major", (0,2,4,5,7,9,11)), ("natural minor", (0,2,3,5,7,8,10)))
                 if target.full_pcs <= {(root + interval) % 12 for interval in scale})


def collection_metadata(context):
    if context is None: return None
    root, mode = context
    scale = (0,2,4,5,7,9,11) if mode == "major" else (0,2,3,5,7,8,10)
    return {"tonic_pitch_class": root, "mode": mode,
            "pitch_classes": sorted((root + interval) % 12 for interval in scale),
            "interpretation": "compatible local collection; no asserted global tonic or Roman numerals"}


def related(previous, target, relationship, context=None):
    if previous.pcs == target.pcs: return False  # A new harmony, not just revoicing.
    if relationship == "Diatonic Relationships":
        return (context in collections_for(previous) and context in collections_for(target) if context is not None else
                bool(set(collections_for(previous)) & set(collections_for(target))))
    if relationship == "Chromatic Relationships":
        return (target.root - previous.root) % 12 in CHROMATIC_ROOT_SHIFTS
    if relationship == "Common-Tone Relationships": return bool(previous.pcs & target.pcs)
    return relationship == "Unrestricted Chord Targets"


def optimize_voicing(previous, target, maximum_voices_moved, maximum_movement, hold_bass_note=False):
    """Only legal template realizations enter the lexicographic cost comparison."""
    best = None
    valid_count = 0
    for notes in target.voicings:
        delta = tuple(b - a for a,b in zip(previous,notes))
        moved = sum(d != 0 for d in delta)
        if (not 1 <= moved <= min(maximum_voices_moved,len(previous)-int(hold_bass_note))
                or any(abs(d) > maximum_movement for d in delta)
                or hold_bass_note and notes[0] != previous[0]): continue
        valid_count += 1
        cost = (sum(abs(d) for d in delta), -sum(d == 0 for d in delta),
                -len(set(previous) & set(notes)), max(map(abs,delta)), notes[-1]-notes[0], notes)
        if best is None or cost < best[1]: best = (notes,cost)
    return None if best is None else (*best,valid_count)


def describe_chord(target, notes, vocabulary):
    counts = Counter(note % 12 for note in notes)
    name = midi_note_name(target.root + 60)[:-1]
    omitted = sorted(set(target.full) - set(target.selected))
    label = f"{name} {target.name}"
    if len(notes) == 2: label = f"{name} two-tone subset of {target.name} (intervals {', '.join(map(str,target.selected))})"
    elif omitted: label += f" (omitted template intervals: {', '.join(map(str,omitted))})"
    bass_interval = (notes[0] - target.root) % 12
    inversion = sorted({i % 12 for i in target.selected}).index(bass_interval)
    return {"display_label": label, "roman_numeral": None, "intended_roman_numeral": None,
            "intended_quality": target.name, "sonority_type": target.name, "harmonic_family": target.family,
            "chord_type": "triad" if vocabulary == "Basic" else "sonority",
            "notes_midi": list(notes), "notes_names": [midi_note_name(n) for n in notes],
            "voice_count": len(notes), "root_pitch_class": target.root, "root_degree": None, "root_semitone": None,
            "root_role": "structural reference" if target.family == "Quartal/Interval-based" else "chord root",
            "root_note_midi": next(n for n in notes if n % 12 == target.root),
            "template_intervals_from_root": list(target.full), "selected_harmonic_intervals": list(target.selected),
            "omitted_intervals": omitted, "distinct_pitch_class_count": len(counts),
            "octave_doublings": [{"pitch_class": pc, "notes_midi": [n for n in notes if n % 12 == pc], "extra_voices": c-1}
                                 for pc,c in sorted(counts.items()) if c > 1],
            "bass_note_midi": notes[0], "bass_note_name": midi_note_name(notes[0]),
            "voicing_span_semitones": notes[-1]-notes[0], "inversion": "root" if vocabulary == "Basic" else inversion,
            "bass_interval_from_root": bass_interval,
            "voicing_description": "Root-position close triad" if vocabulary == "Basic" else
                f"{'Root' if inversion == 0 else f'Tone {inversion+1}'} in bass; {'open' if notes[-1]-notes[0] > 12 else 'close'} voicing",
            "construction": {"reference": "selected chord target template", "intervals_semitones": list(target.full),
                             "voicing_policy": "Basic closed root position" if vocabulary == "Basic" else
                                 "existing Expanded pitch-class coverage, octave displacements and span <= 24 semitones"}}


def state_record(notes, previous, index, chord):
    delta = [b-a for a,b in zip(previous,notes)]
    return {"state_index": index, "notes_midi": list(notes), "notes_names": [midi_note_name(n) for n in notes],
            "voices": [{"voice_id": i, "pitch_midi": n, "displacement_semitones": delta[i]} for i,n in enumerate(notes)],
            "actual_voices_moved": sum(d != 0 for d in delta), "moved_voice_ids": [i for i,d in enumerate(delta) if d],
            "common_tone_count": len(set(previous) & set(notes)) if index else None,
            "retained_voice_count": sum(d == 0 for d in delta) if index else None,
            "total_voice_leading_distance": sum(map(abs,delta)),
            "intervals_above_lowest_semitones": [n-notes[0] for n in notes], "chord": chord}


def choose_transition(previous_target, previous_notes, targets, rng, relationship, balance,
                      maximum_voices_moved, maximum_movement, hold_bass_note, context=None):
    pool = [t for t in targets if related(previous_target,t,relationship,context)]
    weights = sampling_weights(pool,balance) if pool else []
    table = sampling_table(pool,weights)
    rejected = []
    while pool:  # Bounded, without replacement: at most the finite catalog size.
        index = rng.choices(range(len(pool)),weights=weights,k=1)[0]
        target, probability = pool.pop(index), weights.pop(index)
        conditional = probability / (probability + sum(weights))
        result = optimize_voicing(previous_notes,target,maximum_voices_moved,maximum_movement,hold_bass_note)
        if result is None:
            rejected.append(target.identity);continue
        notes,cost,valid_count = result
        local = context
        if relationship == "Diatonic Relationships" and local is None:
            local = rng.choice(sorted(set(collections_for(previous_target)) & set(collections_for(target))))
        shift=(target.root-previous_target.root)%12
        description=(f"structural reference shift ({shift} semitones)" if "Quartal/Interval-based" in (target.family,previous_target.family) else
                     "chromatic mediant" if shift in (3,4,8,9) and target.name in ("major triad","minor triad")
                         and previous_target.name==target.name else
                     "third-related roots" if shift in (3,4,8,9) else
                     "parallel template/quality change" if shift==0 else
                     f"root shift ({shift} semitones)")
        return target,notes,{"class": relationship, "relationship_description":description,
                            "local_tonal_collection": collection_metadata(local),
                            "root_or_reference_shift_semitones": (target.root-previous_target.root)%12,
                            "common_pitch_classes": sorted(previous_target.pcs & target.pcs),
                            "chromatic_root_shift_policy": list(CHROMATIC_ROOT_SHIFTS) if relationship == "Chromatic Relationships" else None,
                            "sampling": {"proposal_probabilities": table, "rejected_target_ids": rejected,
                                         "accepted_conditional_probability": conditional},
                            "voice_leading_cost": {"policy": list(COST_POLICY), "value": list(cost[:-1]),
                                                   "midi_tie_break": list(notes), "valid_voicings": valid_count}}
    raise ValueError(f"No {relationship} target has a legal voicing ({len(rejected)} chord identities examined).")


def generate_targeted(low, high, vocabulary="Expanded", voice_count=4, family="All", state_count=3,
                      maximum_voices_moved=3, maximum_movement=7, hold_bass_note=False,
                      relationship="Mixed", balance="Balanced", seed=None):
    if (relationship not in RELATIONSHIPS or balance not in QUALITY_BALANCES or state_count not in (1,2,3)
            or maximum_voices_moved not in (1,2,3,4,5) or maximum_movement not in range(1,17)):
        raise ValueError("Invalid Chord Targeting relationship, quality balance, states or movement constraints.")
    targets = catalog(vocabulary,voice_count,family,low,high)
    if not targets: raise ValueError("No chord target fits this voice count and register. Widen the register.")
    seed = random.SystemRandom().getrandbits(64) if seed is None else seed
    rng = random.Random(seed)
    weights = sampling_weights(targets,balance)
    initial_table = sampling_table(targets,weights)
    failures = []
    for attempt in range(1,MAX_INITIAL_ATTEMPTS+1):
        initial = rng.choices(targets,weights=weights,k=1)[0]
        notes = rng.choice(initial.voicings)
        context = rng.choice(collections_for(initial)) if relationship == "Diatonic Relationships" else None
        chord = describe_chord(initial,notes,vocabulary)
        states = [state_record(notes,notes,0,chord)]
        current = initial
        try:
            for index in range(1,state_count):
                classes = list(MIXED_PROBABILITIES) if relationship == "Mixed" else [relationship]
                class_failures = []
                class_draws = []
                while classes:
                    # Equal nominal Mixed weights; remove only classes with no legal targets.
                    chosen = rng.choice(classes)
                    class_draws.append({"class":chosen,"conditional_probability":1/len(classes),"feasible":False})
                    try:
                        target,new_notes,details = choose_transition(current,notes,targets,rng,chosen,balance,
                            maximum_voices_moved,maximum_movement,hold_bass_note,context)
                        class_draws[-1]["feasible"]=True
                        break
                    except ValueError as error:
                        class_failures.append(str(error));classes.remove(chosen)
                else: raise ValueError("; ".join(class_failures))
                details["infeasible_relationship_attempts"] = class_failures
                details["relationship_class_draws"] = class_draws
                state = state_record(new_notes,notes,index,describe_chord(target,new_notes,vocabulary))
                state["target_relationship"] = details
                states.append(state);current,notes = target,new_notes
            return {"generation_mode":"ambient", "generation_framework":"chord_targeting",
                    "created_at":datetime.now(timezone.utc).isoformat(),"chord":chord,"states":states,
                    "selection_settings":{"harmonic_vocabulary":vocabulary,"generation_framework":"chord_targeting",
                        "tonic_midi":None,"modal_preset":None,"register_low":low,"register_high":high,
                        "voice_count":voice_count,"harmonic_family":"Triadic" if vocabulary=="Basic" else family,
                        "harmonic_relationship":relationship,"chord_quality_balance":balance,
                        "maximum_harmonic_states":state_count,"harmonic_states":state_count,
                        "maximum_voices_moved":maximum_voices_moved,"maximum_voice_movement_semitones":maximum_movement,
                        "hold_bass_note":bool(hold_bass_note),"generator_version":VERSION,"generator_seed":seed},
                    "chord_targeting":{"algorithm":VERSION,"source_sha256":SOURCE_SHA256,"seed":seed,
                        "seed_scope":"chord identities, initial voicing, local contexts and relationship proposal order; realized voice/state counts are inputs",
                        "initial_sampling_probabilities":initial_table,"initial_voicing_probability":1/len(initial.voicings),
                        "quality_category_factors":QUALITY_FACTORS.get(balance,"equal templates within each family/root"),
                        "quality_classification":"major/dominant/major-added templates; minor templates; neutral suspended/quartal templates",
                        "mixed_nominal_probabilities":MIXED_PROBABILITIES,"mixed_feasibility_policy":"try classes without replacement; only classes with no valid target may be skipped",
                        "local_tonal_collection":collection_metadata(context),"initial_attempts":attempt,
                        "failed_initial_attempts":failures,"maximum_initial_attempts":MAX_INITIAL_ATTEMPTS,
                        "cost_policy":list(COST_POLICY),"distinct_pitch_class_sets_required":True}}
        except ValueError as error: failures.append(str(error))
    raise ValueError(f"Chord Targeting found no valid {state_count}-state sequence after {MAX_INITIAL_ATTEMPTS} bounded initial attempts. "
                     f"Relationship: {relationship}; register {low}–{high}; {voice_count} voices; maximum {maximum_voices_moved} moving "
                     f"by {maximum_movement} semitones; Hold Bass Note {'on' if hold_bass_note else 'off'}. "
                     f"Widen the register or relax the movement/bass constraints. Last attempt: {failures[-1]}")
