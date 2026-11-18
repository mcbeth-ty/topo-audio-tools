"""Focused preview timing, settings, caching and non-mutation checks."""
import copy
import io
import unittest
from unittest.mock import patch
import wave

import ambient_app as app
import ambient_preview as preview
import ambient_saved as saved
from ambient_audio import RENDERER_VERSION, SAMPLE_RATE
from ambient_soundfont import RENDERER_VERSION as SF_VERSION


class PreviewTests(unittest.TestCase):
    def setUp(self):
        stimulus=app.generate_batch(4,None,None,48,72,3,3,2,'Expanded',(2,2),'All',
                                    generation_framework='chord_targeting',state_weights=(0,0,100))[0]
        self.metadata,_=app.render_stimulus(stimulus,0,15,'Sine',False,'Procedural',None,None,None,'Dry',.3,display=False)
        preview.cached_preview_audio.clear()

    def test_five_second_procedural_cache_and_original_preservation(self):
        before=copy.deepcopy(self.metadata)
        native=preview.render_states_wav
        with patch.object(preview,'render_states_wav',wraps=native) as renderer:
            first=preview.preview_audio(self.metadata)
            second=preview.preview_audio(self.metadata)
            self.assertEqual(first,second)
            self.assertEqual(renderer.call_count,1)
            states,duration,timbre,reverb=renderer.call_args.args
            self.assertEqual(states,tuple(tuple(s['notes_midi']) for s in self.metadata['states']))
            self.assertEqual((duration,timbre,reverb),(5,'Sine',False))
        with wave.open(io.BytesIO(first)) as wav:
            self.assertEqual(wav.getnframes(),5*SAMPLE_RATE)
        self.assertEqual(self.metadata,before)
        self.assertEqual([s['start_seconds'] for s in self.metadata['states']],[0,5,10])
        self.assertEqual(saved.reconstruct(self.metadata,app.cached_audio),app.cached_audio(states,15,'Sine',False,RENDERER_VERSION))

    def test_extended_playback_preserves_recipe_and_separates_duration_cache(self):
        before=copy.deepcopy(self.metadata)
        native=preview.render_states_wav
        with patch.object(preview,'render_states_wav',wraps=native) as renderer:
            short=preview.preview_audio(self.metadata,5)
            extended=preview.preview_audio(self.metadata,30)
            self.assertEqual(preview.preview_audio(self.metadata,30),extended)
            self.assertEqual(renderer.call_count,2)
            self.assertEqual(renderer.call_args.args[1],30)
            self.assertEqual(renderer.call_args.args[0],tuple(tuple(s['notes_midi']) for s in self.metadata['states']))
        for wav,seconds in [(short,5),(extended,30)]:
            with wave.open(io.BytesIO(wav)) as audio:self.assertEqual(audio.getnframes(),seconds*SAMPLE_RATE)
        self.assertEqual(self.metadata,before)

    def test_soundfont_settings_identity_and_cache_keys(self):
        metadata=copy.deepcopy(self.metadata);audio=metadata['rendering']
        audio.update(backend='SoundFont',renderer_version=SF_VERSION,timbre='Warm Pad',reverb='Room',
                     effect_level=.6,soundfont={'path':'/test.sf2','sha256':'test-hash','bank':0,'program':89})
        with patch.object(saved,'soundfont_identity',return_value=('/test.sf2','test-hash')), \
             patch.object(preview,'render_soundfont_wav',return_value=b'preview') as renderer:
            self.assertEqual(preview.preview_audio(metadata),b'preview')
            self.assertEqual(preview.preview_audio(metadata),b'preview')
            self.assertEqual(renderer.call_count,1)
            self.assertEqual(renderer.call_args.args[1:],(5,('/test.sf2','test-hash'),89,'Room',.6))
            metadata['rendering']['effect_level']=.7
            preview.preview_audio(metadata);self.assertEqual(renderer.call_count,2)
        with patch.object(saved,'soundfont_identity',return_value=('/test.sf2','different-hash')):
            with self.assertRaisesRegex(ValueError,'SoundFont identity'):preview.preview_audio(metadata)
