# Ambient Chord Targeting v1

Only chord/state generation changes. Existing timing, renderers, audio caches,
playback, collection decisions and frozen-study reconstruction use exact stored
MIDI states as before. Defaults for existing frameworks remain unchanged.

## Selection

- Basic uses the existing Chromatic major/minor closed root-position triads.
- Expanded uses `TEMPLATES` and `eligible_voicings` from `ambient_expanded.py`:
  all selected pitch classes, octave doublings, inversions and <=24-semitone span.
  The existing tone-priority truncation applies to undersized voice counts.
  Two voices are explicitly labeled as template subsets, not uniquely identified
  complete chords; omitted tones are recorded for every state.
- Eligible families and roots have equal mass. Within a family/root, Balanced
  gives equal mass to available major, minor and neutral categories. Favor Major
  uses 3:1:1, Favor Minor 1:3:1. Original gives equal template probabilities,
  matching Chromatic's hierarchy. Major includes dominant/major-added structures.
  Neutral suspended/quartal material is retained. Bias does not change identities.

## Relationships

- Diatonic: choose a plausible major or natural-minor collection containing the
  initial full template, then retain it throughout the sequence. All targets'
  full templates must fit. No asserted tonal center or Roman-numeral analysis.
- Chromatic: explicit root/reference shifts of 0, 1, 3, 4, 6, 8, 9 or 11 semitones.
  These admit parallel quality/template changes, semitone shifts, third relations
  and tritone relations. Same-quality third-related triads are described as
  chromatic mediants; quartal relationships are structural reference shifts.
- Common-Tone: at least one shared pitch class with the previous chord.
- Mixed: equal nominal probabilities for the first three modes; try remaining
  modes only if a chosen mode has no legal target. Diatonic transitions in Mixed
  have a local context per transition, not a fabricated global key.
- Unrestricted: any allowed template/root identity, still subject to all hard
  register/movement/bass constraints.

Consecutive states must have different pitch-class sets. Merely revoicing the
same harmony does not count as a new chord target.

## Voice leading and bounds

Select a target identity before optimizing its realization. Consider only legal
voicings with non-crossing distinct pitches, the same voice count, 1 through the
maximum movable voices, and every displacement within the maximum. Locked bass
means the exact initial lowest MIDI note stays fixed. Tie-breaking is deterministic:

1. Minimum total absolute displacement.
2. Most unchanged voice pitches (common-tone audio continuity).
3. Most exact MIDI common tones.
4. Smallest maximum individual leap.
5. Smallest total voicing span.
6. Lexicographically lowest MIDI tuple.

If a target has no legal realization, try another identity without replacement
(at most the finite catalog size). Restart from another initial draw at most eight
times if a sequence fails. No displacements are generated as a fallback. Failure
reports constraints and attempts; it does not claim a proof of global impossibility.
Feasibility-conditioned retries can bias realized frequencies from nominal weights.
Basic + locked bass + Diatonic is generally incompatible because its root-position
bass cannot change roots and a parallel major/minor switch cannot share one such
collection. Other tight combinations may also fail explicitly.

## Reproducibility

Each state stores its own chord template, selected/omitted intervals, root role,
voicing and exact MIDI pitches. Relationship metadata includes local collections,
proposal probabilities, rejected identities, conditional acceptance probability,
Mixed class draws, optimal cost and valid-voicing count. A generator version,
per-stimulus seed, actual voice/state counts and all constraints are retained.
The seed controls chord generation; voice/state-count sampling remains in the
existing batch generator, whose realized inputs and weights are recorded.
No migration or framework-specific audio interpretation is required.
