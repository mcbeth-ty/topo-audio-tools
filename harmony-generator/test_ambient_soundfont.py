"""Focused real-backend checks. Set AMBIENT_SF2_PATH and run this file directly."""

import io
import os
import unittest
from unittest.mock import patch
import wave

import numpy as np

import ambient_soundfont as sf


STATES = ((48, 52, 55), (48, 53, 55), (48, 53, 57))
DURATION = 10


def samples(data):
    with wave.open(io.BytesIO(data)) as source:
        assert source.getnchannels() == 2
        assert source.getframerate() == sf.SAMPLE_RATE
        return np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").reshape(-1, 2) / 32768


class SoundFontRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("AMBIENT_SF2_PATH")
        if not path:
            raise unittest.SkipTest("Set AMBIENT_SF2_PATH to the existing GeneralUser GS SF2.")
        try:
            sf.fluid_module()
            cls.font = sf.soundfont_identity(path)
        except sf.SoundFontUnavailable as error:
            raise unittest.SkipTest(str(error)) from error

    def test_two_voice_rendering(self):
        states = ((48,55),(48,56),(49,56))
        output = samples(sf.render_soundfont_wav(states,DURATION,self.font,89,"Room",0.6))
        self.assertGreater(np.max(np.abs(output)),0.001)
        self.assertGreater(len(output),DURATION*sf.SAMPLE_RATE)

    def test_generaluser_presets(self):
        presets = {program: name for _, program, name in sf.available_presets(self.font)}
        self.assertEqual(presets[92], "Bowed Glass")
        self.assertEqual(presets[94], "Halo Pad")
        self.assertEqual(len(presets), 7)
        for program in (92, 94):
            output = samples(sf.render_soundfont_wav(STATES, DURATION, self.font, program))
            self.assertGreater(np.max(np.abs(output)), 0.001)

    def test_continuous_engine_release_reverb_and_trimming(self):
        tails = {}
        native_factory = sf.new_synth
        for mode in sf.REVERB_SETTINGS:
            # Three states still allocate only one engine; capture its lifecycle.
            with patch.object(sf, "new_synth", wraps=native_factory) as factory:
                data = sf.render_soundfont_wav(STATES, DURATION, self.font, 48, mode, 0.6)
                self.assertEqual(factory.call_count, 1)
            output = samples(data)
            tail = output[DURATION * sf.SAMPLE_RATE:]
            tails[mode] = tail
            self.assertGreater(np.sqrt(np.mean(tail[:sf.SAMPLE_RATE // 4] ** 2)), 0.0001)
            self.assertLessEqual(np.max(np.abs(output)), 0.801)
            self.assertGreaterEqual(len(tail), round(sf.MIN_RELEASE_SECONDS * sf.SAMPLE_RATE))
            active = np.flatnonzero(np.max(np.abs(tail), axis=1) > sf.TAIL_THRESHOLD)
            self.assertGreater(len(active), 0)
            quiet_end = (len(tail) - active[-1] - 1) / sf.SAMPLE_RATE
            self.assertLessEqual(quiet_end, sf.END_PADDING_SECONDS + 0.02)
            self.assertLessEqual(np.max(np.abs(output[-1])), 1 / 32768)
            # Decay is measurable, rather than simply appended silence.
            early = np.sqrt(np.mean(tail[:sf.SAMPLE_RATE // 4] ** 2))
            late = np.sqrt(np.mean(tail[-sf.SAMPLE_RATE // 4:] ** 2))
            self.assertGreater(early, late * 10)
            self.assertEqual(data, sf.render_soundfont_wav(STATES, DURATION, self.font, 48, mode, 0.6))
        self.assertLess(len(tails["Dry"]), len(tails["Room"]))
        self.assertLess(len(tails["Room"]), len(tails["Ambient"]))
        # Inspect the same post-note-off interval, independently of output length.
        rms = {mode: np.sqrt(np.mean(tail[:sf.SAMPLE_RATE // 2] ** 2))
               for mode, tail in tails.items()}
        self.assertGreater(rms["Room"], rms["Dry"] * 1.5)
        self.assertGreater(rms["Ambient"], rms["Room"] * 1.5)

    def test_effect_level_and_common_tones(self):
        events = sf.note_events(STATES, DURATION)
        common_tone_starts = [event for event in events if event[1] == "noteon" and event[2][1] == 48]
        self.assertEqual(len(common_tone_starts), 1)
        final_offs = [event for event in events if event[1] == "noteoff"]
        self.assertEqual(max(event[0] for event in final_offs), DURATION * sf.SAMPLE_RATE)
        dry = sf.render_soundfont_wav(STATES, DURATION, self.font, 48, "Dry")
        zero = sf.render_soundfont_wav(STATES, DURATION, self.font, 48, "Ambient", 0.0)
        wet = sf.render_soundfont_wav(STATES, DURATION, self.font, 48, "Ambient", 0.6)
        self.assertEqual(dry, zero)
        self.assertNotEqual(zero, wet)


if __name__ == "__main__":
    unittest.main(verbosity=2)
