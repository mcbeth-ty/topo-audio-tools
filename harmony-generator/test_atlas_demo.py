"""Focused public-demo isolation and enforced rendering constraints."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import atlas_demo as demo


class AtlasDemoTests(unittest.TestCase):
    def test_public_snapshot_projection_is_read_only_and_minimal(self):
        model={'manifest':{'inventory':[{'stimulus_id':'private-id','metadata':{'private_recipe':True}}]},
               'fits':{'Ordinal:3D+color':{'embedding':{'coordinates':{'private-id':[1,2,3,4]}}}},
               'summary':{'pairs':{}},'tags':{'private-id':'Hopeful'}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.json';path.write_text(json.dumps(model));before=path.read_bytes()
            public,recipes=demo._read_model(str(path),path.stat().st_size,path.stat().st_mtime_ns)
            self.assertEqual(public['world_positions'],{'n1':[1,2,3,4]})
            self.assertEqual(public['tags'],{'n1':'Hopeful'})
            self.assertEqual(set(public),{'ids','world_positions','tags','pairs'})
            self.assertNotIn('private-id',json.dumps(public));self.assertEqual(recipes['n1'],{'private_recipe':True})
            self.assertEqual(path.read_bytes(),before)

    def test_generator_enforces_four_warm_pad_fifteen_second_samples(self):
        import ambient_app
        stimulus={'states':[{'notes_midi':[48,55,60]}]};batch=[copy.deepcopy(stimulus) for _ in range(4)]
        with patch.object(ambient_app,'generate_batch',return_value=batch) as generate, \
             patch.object(demo,'demo_soundfont',return_value=('asset.sf2','hash')), \
             patch.object(demo,'warm_audio',return_value=b'wav') as render:
            for framework in ('chromatic','chord_targeting'):
                out=demo.generate_demo({'framework':framework,'backend':'Procedural','duration':5,'batch_size':99,'timbre':'Sine','weights':[100,0,0],'low':45,'high':75})
                self.assertEqual(len(out),4);self.assertEqual(generate.call_args.args[0],4)
                self.assertEqual(generate.call_args.kwargs['generation_framework'],framework)
                self.assertEqual(generate.call_args.kwargs['state_weights'],(25,100,100))
                self.assertEqual(generate.call_args.args[8],'Expanded')
                self.assertEqual(generate.call_args.args[3:5],(45,75))
                self.assertEqual(render.call_args.args,(((48,55,60),),('asset.sf2','hash')))
            with self.assertRaises(ValueError):demo.generate_demo({'framework':'diatonic'})
        with patch.object(demo,'render_soundfont_wav',return_value=b'pcm') as synth:
            demo.warm_audio.clear();demo.warm_audio(((48,55,60),),('asset.sf2','hash'))
            self.assertEqual(synth.call_args.args,(((48,55,60),),15,('asset.sf2','hash'),89,'Room',.6))

    def test_saved_audio_uses_fifteen_seconds_without_mutating_recipe(self):
        metadata={'rendering':{'backend':'Procedural'}};before=copy.deepcopy(metadata)
        with patch.object(demo,'preview_audio',return_value=b'wav') as render:
            self.assertEqual(demo.recipe_audio(metadata),b'wav');render.assert_called_once_with(metadata,15)
        self.assertEqual(metadata,before)
