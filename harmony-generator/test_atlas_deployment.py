"""Portable asset verification and public dataset privacy regression checks."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import atlas_assets as assets
import atlas_demo as demo


class DeploymentTests(unittest.TestCase):
    def test_packaged_models_have_no_private_provenance_or_paths(self):
        loaded=demo.load_demo_models()
        self.assertEqual([len(item[0]['ids']) for item in loaded],[24,49,24])
        for path in (demo.ROOT/'public_data'/'models').glob('*.json'):
            record=json.loads(path.read_text());text=path.read_text()
            for forbidden in ('/Users/','source_session_id','submitted_at','source_saved_at','trial_id','created_at'):
                self.assertNotIn(forbidden,text)
            self.assertEqual(set(record['fits']),{'Ordinal:3D+color'})
            self.assertTrue(all(item['stimulus_id'].startswith('n') for item in record['manifest']['inventory']))

    def test_download_is_verified_atomic_and_reused(self):
        content=b'verified-test-font';digest=hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'AFFECTIVE_ATLAS_ASSET_CACHE':directory},clear=True), \
             patch.object(assets,'SOUNDFONT_BYTES',len(content)),patch.object(assets,'SOUNDFONT_SHA256',digest), \
             patch.object(assets.urllib.request,'urlopen',return_value=io.BytesIO(content)) as download, \
             patch.object(assets,'soundfont_identity',side_effect=lambda p:(str(p),hashlib.sha256(Path(p).read_bytes()).hexdigest())):
            one=assets.demo_soundfont();two=assets.demo_soundfont()
            self.assertEqual(one,two);download.assert_called_once()
            self.assertEqual(Path(one[0]).read_bytes(),content)
            self.assertFalse(list(Path(directory).glob('.soundfont-*')))

    def test_bad_download_never_becomes_a_soundfont(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'AFFECTIVE_ATLAS_ASSET_CACHE':directory},clear=True), \
             patch.object(assets.urllib.request,'urlopen',return_value=io.BytesIO(b'bad')):
            with self.assertRaises(assets.SoundFontUnavailable):assets.demo_soundfont()
            self.assertFalse((Path(directory)/'GeneralUser-GS.sf2').exists())
            self.assertFalse(list(Path(directory).glob('.soundfont-*')))
