"""Regression: two-voice generation must render and remain reconstructible."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ambient_app as app
import ambient_library as library
from ambient_saved import reconstruct


class VoiceRenderingTests(unittest.TestCase):
    def test_two_voice_render_save_and_reconstruct(self):
        batch=app.generate_batch(4,None,None,48,72,3,3,2,"Expanded",(2,2),"All",
                                 generation_framework="chromatic",state_weights=(0,0,100))
        for index,timbre in enumerate(("Sine","Strings","Choir")):
            metadata,wav=app.render_stimulus(batch[index],index,10,timbre,False,"Procedural",
                                            None,None,None,"Dry",.3,display=False)
            self.assertTrue(all(len(state["notes_midi"])==2 for state in metadata["states"]))
            library.validate_metadata(metadata)
            with tempfile.TemporaryDirectory() as root,patch.object(library,"LIBRARY_DIR",Path(root)):
                record,_=library.save_stimulus(metadata)
                reopened=library.hydrate(library.read_record(record["saved_id"]))
                self.assertEqual(reconstruct(reopened["metadata"],app.cached_audio),wav)
                self.assertFalse(list(Path(root).glob("*.wav")))
