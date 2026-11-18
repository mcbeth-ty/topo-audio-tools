"""Optional offline FluidSynth backend. No audio device, MIDI files, or SF2 assets."""

from functools import lru_cache
import hashlib
import importlib
import io
from pathlib import Path
import wave

import numpy as np

from ambient_audio import SAMPLE_RATE, TRANSITION_SECONDS

RENDERER_VERSION = "ambient_soundfont_v3_polyphony"
# General MIDI programs are zero-based in FluidSynth; verify against the loaded bank.
PRESETS = {"Sampled Strings": 48, "Choir Aahs": 52, "Voice Oohs": 53,
           "Warm Pad": 89, "Choir Pad": 91, "Halo Pad": 94, "Bowed Glass": 92}
# Room size controls the native reverb's decay, separately from instrument release.
REVERB_SETTINGS = {"Dry": None, "Room": (0.65, 0.45, 70.0),
                   "Ambient": (0.92, 0.25, 100.0)}
TAIL_THRESHOLD_DBFS = -84.0
TAIL_THRESHOLD = 10 ** (TAIL_THRESHOLD_DBFS / 20)
MIN_RELEASE_SECONDS = 0.75
MAX_TAIL_SECONDS = 30.0
QUIET_HOLD_SECONDS = 0.5
END_PADDING_SECONDS = 0.12
END_FADE_SECONDS = 0.08
SETUP = ("Optional SoundFont setup (use the Python environment running Streamlit):\n"
         "brew install fluid-synth\npython -m pip install pyFluidSynth\n"
         "Download GeneralUser-GS.sf2 from https://github.com/mrbumpy409/GeneralUser-GS "
         "and set AMBIENT_SF2_PATH or enter its local path below. "
         "Procedural Sine, Strings and Choir remain available.")


class SoundFontUnavailable(RuntimeError):
    pass


def fluid_module():
    try:
        module = importlib.import_module("fluidsynth")
        if not hasattr(module, "Synth"):
            raise ImportError("Install pyFluidSynth, not the unrelated fluidsynth package.")
        return module
    except (ImportError, OSError) as error:
        raise SoundFontUnavailable(f"FluidSynth unavailable: {error}\n\n{SETUP}") from error


@lru_cache(maxsize=4)
def _file_digest(path, size, modified_ns, inode):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def soundfont_identity(path):
    try:
        source = Path(path).expanduser().resolve()
        if source.suffix.lower() != ".sf2" or not source.is_file():
            raise ValueError("Select a local .sf2 file.")
        stat = source.stat()
        return (str(source), _file_digest(str(source), stat.st_size, stat.st_mtime_ns, stat.st_ino))
    except (OSError, ValueError) as error:
        raise SoundFontUnavailable(f"SoundFont unavailable: {error}\n\n{SETUP}") from error


def new_synth(reverb_mode="Dry", effect_level=0.3):
    # One offline engine and one native effect state for the complete stimulus.
    settings = REVERB_SETTINGS[reverb_mode]
    synth = fluid_module().Synth(gain=0.12, samplerate=SAMPLE_RATE, channels=16,
                                **{"synth.reverb.active": int(settings is not None and effect_level > 0),
                                   "synth.chorus.active": 0, "synth.cpu-cores": 1,
                                   "synth.threadsafe-api": 0})
    if settings is not None:
        roomsize, damping, width = settings
        result = synth.set_reverb(roomsize=roomsize, damping=damping,
                                  width=width, level=effect_level)
        if result not in (None, 0):
            synth.delete()
            raise SoundFontUnavailable("FluidSynth could not configure native reverb.")
    return synth


def load_font(synth, identity):
    if soundfont_identity(identity[0]) != identity:
        raise SoundFontUnavailable("SoundFont changed on disk. Rerun to refresh its identity.")
    sfid = synth.sfload(identity[0])
    if sfid < 0:
        raise SoundFontUnavailable("FluidSynth could not load this SF2 file.")
    return sfid


@lru_cache(maxsize=4)
def available_presets(identity):
    synth = new_synth()
    try:
        sfid = load_font(synth, identity)
        return tuple((label, program, synth.sfpreset_name(sfid, 0, program))
                     for label, program in PRESETS.items()
                     if synth.program_select(0, sfid, 0, program) == 0)
    finally:
        synth.delete()


def note_events(states, duration):
    """Merge unchanged voices and schedule short expression-controlled overlaps."""
    events = []
    def add(seconds, action, *args):
        events.append((round(seconds * SAMPLE_RATE), action, args))
    # Merge by pitch, including a common tone transferred to another voice ID.
    # Allocate up to ten channels per overlapping run (two five-voice states).
    # Remap around MIDI channel 10, reserved for percussion.
    runs = []
    for pitch in sorted({pitch for state in states for pitch in state}):
        first = 0
        while first < len(states):
            if pitch not in states[first]:
                first += 1
                continue
            last = first + 1
            while last < len(states) and pitch in states[last]:
                last += 1
            on = duration * first / len(states) - (TRANSITION_SECONDS / 2 if first else 0)
            off = duration * last / len(states) + (TRANSITION_SECONDS / 2 if last < len(states) else 0)
            runs.append((on, off, pitch, first, last))
            first = last
    channels = [channel for channel in range(16) if channel != 9][:2 * len(states[0])]
    channel_until = [-1.0] * len(channels)
    for on, off, pitch, first, last in sorted(runs):
        slot = next(index for index, until in enumerate(channel_until) if until <= on)
        channel_until[slot] = off
        channel = channels[slot]
        add(on, "all_sounds_off", channel)
        add(on, "cc", channel, 11, 0 if first else 127)
        add(on, "noteon", channel, pitch, 80)
        # Raised-cosine ramps at 100 Hz, with stable common-tone channels.
        for step in range(31):
            fraction = step / 30
            level = round(127 * np.sin(np.pi * fraction / 2) ** 2)
            if first:
                add(on + TRANSITION_SECONDS * fraction, "cc", channel, 11, level)
            if last < len(states):
                add(off - TRANSITION_SECONDS + TRANSITION_SECONDS * fraction,
                    "cc", channel, 11, 127 - level)
        add(off, "noteoff", channel, pitch)
    # Stable sort preserves initialization order at the same sample frame.
    return sorted(events, key=lambda event: event[0])


def trim_tail(audio, musical_frames):
    """Keep quiet stereo ambience, never shorten the requested musical event."""
    # Examine both channels together. The threshold is below quiet ambience but
    # above FluidSynth's 16-bit dither floor, which otherwise prevents termination.
    active = np.flatnonzero(np.max(np.abs(audio[musical_frames:]), axis=1) > TAIL_THRESHOLD)
    last = musical_frames + int(active[-1]) + 1 if len(active) else musical_frames
    keep = max(musical_frames + round(MIN_RELEASE_SECONDS * SAMPLE_RATE),
               last + round(END_PADDING_SECONDS * SAMPLE_RATE))
    result = audio[:min(keep, len(audio))].copy()
    fade = min(round(END_FADE_SECONDS * SAMPLE_RATE), len(result) - musical_frames)
    if fade:
        result[-fade:] *= (np.cos(np.linspace(0, np.pi / 2, fade)) ** 2)[:, None]
    return result


def render_soundfont_wav(states, duration, identity, program, reverb_mode="Dry", effect_level=0.3):
    if (not 1 <= len(states) <= 3 or not 2 <= len(states[0]) <= 5
            or any(len(state) != len(states[0]) for state in states)
            or any(not all(0 <= pitch <= 127 for pitch in state)
                   or not all(a < b for a, b in zip(state, state[1:])) for state in states)
            or not 5 <= duration <= 90 or program not in PRESETS.values()
            or reverb_mode not in REVERB_SETTINGS or not 0 <= effect_level <= 1):
        raise ValueError("Invalid SoundFont rendering settings.")
    musical_frames = round(duration * SAMPLE_RATE)
    maximum_frames = musical_frames + round(MAX_TAIL_SECONDS * SAMPLE_RATE)
    synth = new_synth(reverb_mode, effect_level)
    chunks = []
    cursor = 0
    try:
        sfid = load_font(synth, identity)
        for channel in [channel for channel in range(16) if channel != 9][:2 * len(states[0])]:
            if synth.program_select(channel, sfid, 0, program) != 0:
                raise SoundFontUnavailable("This preset is not available in the selected SF2.")
            # Explicit send amount: effect level is controlled by the native unit.
            synth.cc(channel, 91, 100)
        def read_block(size):
            nonlocal cursor
            block = synth.get_samples(size).reshape(-1, 2)
            if np.max(np.abs(block.astype(np.int32))) >= 32767:
                raise SoundFontUnavailable("SoundFont output clipped; select a quieter preset.")
            block = block.astype(np.float32) / 32768
            chunks.append(block)
            cursor += size
            return block
        for frame, action, args in note_events(states, duration):
            while cursor < frame:
                read_block(min(4096, frame - cursor))
            getattr(synth, action)(*args)
        # Final note-offs occur at musical_frames. Do not reset, mute, or delete
        # the synth until its instrument envelopes AND native reverb have decayed.
        quiet_frames = 0
        while cursor < maximum_frames:
            block = read_block(min(1024, maximum_frames - cursor))
            quiet_frames = quiet_frames + len(block) if np.max(np.abs(block)) <= TAIL_THRESHOLD else 0
            if (cursor >= musical_frames + round(MIN_RELEASE_SECONDS * SAMPLE_RATE)
                    and quiet_frames >= round(QUIET_HOLD_SECONDS * SAMPLE_RATE)):
                break
    finally:
        synth.delete()
    audio = np.concatenate(chunks)
    del chunks
    audio = trim_tail(audio, musical_frames)
    # Smooth the initial attack without changing final note-off timing.
    attack = round(1.5 * SAMPLE_RATE)
    audio[:attack] *= (np.sin(np.linspace(0, np.pi / 2, attack)) ** 2)[:, None]
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-7:
        raise SoundFontUnavailable("SoundFont produced silent output; select another preset.")
    audio *= min(1.0, 0.8 / peak)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(np.rint(audio * 32767).astype("<i2").tobytes())
    return buffer.getvalue()
