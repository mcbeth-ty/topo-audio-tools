"""Deterministic, dependency-free (apart from NumPy) Ambient WAV synthesis."""

import io
import wave

import numpy as np

TRANSITION_SECONDS = 0.3


RENDERER_VERSION = "ambient_states_v3_polyphony"
SAMPLE_RATE = 22050
TIMBRES = ("Sine", "Strings", "Choir")


def synthesize_note(pitch, t, timbre):
    frequency = 440.0 * 2 ** ((pitch - 69) / 12)
    voice = np.zeros(len(t), dtype=np.float32)
    if timbre == "Sine":
        voice = np.sin(2 * np.pi * frequency * t)
    else:
        # Fixed detuning and slow modulation: identical design for every note.
        partials = []
        for harmonic in range(1, 13):
            hz = frequency * harmonic
            if hz * 1.002 >= SAMPLE_RATE / 2:
                continue
            if timbre == "Strings":
                weight = harmonic ** -1.35
            else:
                # Broad fixed vowel formants shape the harmonic spectrum.
                formants = sum(
                    gain * np.exp(-0.5 * ((hz - center) / width) ** 2)
                    for center, width, gain in (
                        (700, 180, 1.0), (1200, 250, 0.7), (2600, 400, 0.35)
                    )
                )
                weight = (0.18 + formants) / harmonic
            partials.append((harmonic, weight))
        total_weight = sum(weight for _, weight in partials)
        vibrato = 0.025 * np.sin(2 * np.pi * 0.23 * t)
        for harmonic, weight in partials:
            phase = 2 * np.pi * frequency * harmonic * t
            voice += (weight / total_weight) * (
                0.6 * np.sin(phase + vibrato)
                + 0.2 * np.sin(phase * 1.0015 + 0.4)
                + 0.2 * np.sin(phase * 0.9985 - 0.4)
            )
        voice *= 0.97 + 0.03 * np.sin(2 * np.pi * 0.17 * t)
    return voice


def render_ambient_wav(pitches, duration, timbre="Strings", reverb=False):
    """Compatibility wrapper for a single sustained state."""
    return render_states_wav((tuple(pitches),), duration, timbre, reverb)


def render_states_wav(states, duration, timbre="Strings", reverb=False):
    """Render fixed voices with continuous common tones and smooth note overlaps."""
    states = tuple(tuple(state) for state in states)
    if (not 1 <= len(states) <= 3 or not 2 <= len(states[0]) <= 5
            or any(len(state) != len(states[0]) for state in states)
            or any(not all(0 <= pitch <= 127 for pitch in state)
                   or not all(a < b for a, b in zip(state, state[1:])) for state in states)):
        raise ValueError("Provide one to three ordered, distinct states with two to five consistent voices.")
    if not 5 <= duration <= 90 or timbre not in TIMBRES:
        raise ValueError("Invalid duration or timbre.")
    count = round(duration * SAMPLE_RATE)
    audio = np.zeros(count, dtype=np.float32)
    # Merge each unchanged voice across boundaries, preserving oscillator phase.
    for voice_index in range(len(states[0])):
        first = 0
        while first < len(states):
            last = first + 1
            pitch = states[first][voice_index]
            while last < len(states) and states[last][voice_index] == pitch:
                last += 1
            start_time = duration * first / len(states)
            end_time = duration * last / len(states)
            start = max(0, round((start_time - TRANSITION_SECONDS / 2) * SAMPLE_RATE)) if first else 0
            end = min(count, round((end_time + TRANSITION_SECONDS / 2) * SAMPLE_RATE)) if last < len(states) else count
            t = np.arange(start, end, dtype=np.float64) / SAMPLE_RATE
            voice = synthesize_note(pitch, t, timbre)
            envelope = np.ones(end - start, dtype=np.float32)
            overlap = round(TRANSITION_SECONDS * SAMPLE_RATE)
            fade = np.sin(np.linspace(0, np.pi / 2, overlap)) ** 2
            if first:
                envelope[:overlap] *= fade
            if last < len(states):
                envelope[-overlap:] *= fade[::-1]
            audio[start:end] += voice * envelope / len(states[0])
            first = last

    attack = min(round(1.5 * SAMPLE_RATE), count // 4)
    release = min(round(3.0 * SAMPLE_RATE), count // 3)
    audio[:attack] *= np.sin(np.linspace(0, np.pi / 2, attack)) ** 2
    audio[-release:] *= np.sin(np.linspace(np.pi / 2, 0, release)) ** 2
    if reverb:
        # Dense decaying tapped reflections, bounded and deterministic.
        dry = audio
        audio = np.pad(dry, (0, round(1.5 * SAMPLE_RATE)))
        for index in range(1, 25):
            delay_seconds = 0.037 * index + 0.0007 * index ** 2
            delay = round(delay_seconds * SAMPLE_RATE)
            gain = 0.055 * np.exp(-3.5 * delay_seconds)
            audio[delay:delay + count] += gain * dry

    # Consistent RMS target with a peak ceiling; avoid clipping quiet textures.
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(audio)))
    audio *= min(0.12 / max(rms, 1e-12), 0.8 / max(peak, 1e-12))
    pcm = (audio * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm.tobytes())
    return buffer.getvalue()
