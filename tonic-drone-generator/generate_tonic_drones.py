import numpy as np
import soundfile as sf
from pathlib import Path

# ----------------------------
# SETTINGS
# ----------------------------

OUTPUT_DIR = Path("tonic_drones")
OUTPUT_DIR.mkdir(exist_ok=True)

SAMPLE_RATE = 44100
DURATION = 15.0
AMPLITUDE = 0.25

START_MIDI = 24   # C1
END_MIDI = 84     # C6

NOTE_NAMES = ["C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B"]


# ----------------------------
# FUNCTIONS
# ----------------------------

def midi_to_note_name(midi_note):
    octave = (midi_note // 12) - 1
    note = NOTE_NAMES[midi_note % 12]
    return f"{note}{octave}"


def midi_to_freq(midi_note):
    return 440.0 * (2 ** ((midi_note - 69) / 12))


def make_sine(freq, duration, sample_rate):
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    wave = np.sin(2 * np.pi * freq * t)

    # Small fade in/out to avoid clicks
    fade_len = int(sample_rate * 0.05)

    wave[:fade_len] *= np.linspace(0, 1, fade_len)
    wave[-fade_len:] *= np.linspace(1, 0, fade_len)

    return wave * AMPLITUDE


# ----------------------------
# EXPORT FILES
# ----------------------------

for midi_note in range(START_MIDI, END_MIDI + 1):
    note_name = midi_to_note_name(midi_note)
    freq = midi_to_freq(midi_note)

    audio = make_sine(freq, DURATION, SAMPLE_RATE)

    filename = f"tonic-drone-{note_name}.wav"
    filepath = OUTPUT_DIR / filename

    sf.write(filepath, audio, SAMPLE_RATE, subtype="PCM_24")

    print(f"Created: {filepath}")

print("Done.")