"""Focused immutable model persistence and study-independent playback checks."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import ambient_models as models
import ambient_study as ui
import ambient_study_store as store
from test_ambient_study_4d import fixture


class SavedModelTests(unittest.TestCase):
    def setUp(self):
        ids,pairs=fixture();self.ids=ids
        self.session=uuid4().hex
        metadata={'chord':{'display_label':'Test'},'states':[{'notes_names':['C3','E3','G3'],'notes_midi':[48,52,55]}]}
        self.manifest={'session_id':self.session,'inventory':[{'stimulus_id':i,'metadata':copy.deepcopy(metadata)} for i in ids],
                       'settings':copy.deepcopy(store.SETTINGS),'feedback_policy':'Exploratory'}
        self.state={'name':'Test source','stimulus_tags':{ids[0]:'Tag snapshot'},'revealed_at':None}
        self.summary={'pairs':pairs,'coverage':1,'observed_pairs':66,'possible_pairs':66}
        self.trials=[{'trial_id':'one','value':1}]

    def fit(self,identity,dimension,model):
        return {'summary':copy.deepcopy(self.summary),'input_hash':f'{model}-{dimension}',
                'n_components':dimension,'settings':{'seed':1,'starts':1,'max_iterations':10,'tolerance':1e-6},'model_version':model,'embedding':{'status':'Provisional',
                'fitted_disparities':{str(i):1. for i in range(4)},
                'positive_disparity_by_relatedness':{str(i):.5 for i in range(1,4)},
                'parameters':{'absence_margin':1.,'lambda_absence':2.},
                'coordinates':{i:[float(n+axis) for axis in range(dimension)] for n,i in enumerate(self.ids)}}}

    def test_save_six_variants_is_json_only_and_independent_of_source(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(models,'MODEL_DIR',Path(tmp)), \
             patch.object(store,'load_session',return_value=(self.manifest,self.state)), \
             patch.object(store,'trials',return_value=(self.trials,[])), \
             patch.object(store,'summarize',return_value=self.summary), \
             patch.object(models.analysis,'analyze',side_effect=self.fit) as analyze:
            record=models.save_model(self.session,'My frozen model')
            self.assertEqual(analyze.call_count,6)
            self.assertEqual(set(record['fits']),{f'{name}:{n}' for name in ('Ordinal','Affinity') for n in (2,3,4,'3D+color')})
            path=models.model_path(record['model_id']);saved=path.read_bytes()
            self.assertEqual([p.suffix for p in Path(tmp).iterdir()],['.json'])
            self.manifest['inventory'].clear();self.state['stimulus_tags'].clear()
            with patch.object(store,'load_session',side_effect=AssertionError('Source not needed')), \
                 patch.object(models.analysis,'analyze',side_effect=AssertionError('Must not refit')):
                loaded=models.load_model(record['model_id'])
                self.assertEqual(len(loaded['manifest']['inventory']),12)
                self.assertEqual(loaded['tags'][self.ids[0]],'Tag snapshot')
                self.assertEqual(models.list_models()[0][0]['name'],'My frozen model')
            self.assertEqual(path.read_bytes(),saved)
            (Path(tmp)/'broken.json').write_text('{}')
            self.assertEqual(len(models.list_models()[0]),1);self.assertEqual(len(models.list_models()[1]),1)

    def test_changed_observations_abort_without_saving(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(models,'MODEL_DIR',Path(tmp)), \
             patch.object(store,'load_session',return_value=(self.manifest,self.state)), \
             patch.object(store,'trials',side_effect=[(self.trials,[]),([{'changed':True}],[])]), \
             patch.object(store,'summarize',return_value=self.summary),patch.object(models.analysis,'analyze',side_effect=self.fit):
            with self.assertRaisesRegex(ValueError,'observations changed'):models.save_model(self.session,'Frozen')
            self.assertFalse(list(Path(tmp).iterdir()))

    def test_frozen_canvas_uses_snapshot_tags_and_never_reads_or_writes_study(self):
        frozen={'model_id':uuid4().hex,'tags':{self.ids[0]:'Frozen tag'}};state={};mounted={}
        data={'kind':'explore','context':'frozen:test','ids':self.ids,'n_components':4,'audio_seconds':15}
        with patch.object(ui.st,'session_state',state),patch.object(ui,'_canvas_component',return_value=lambda **kw:mounted.update(kw)), \
             patch.object(store,'load_session',side_effect=AssertionError('Live source not needed')), \
             patch.object(store,'exposure',side_effect=AssertionError('No study writes')), \
             patch.object(ui,'preview_audio',return_value=b'audio') as render,patch.object(ui,'audio_url',return_value='audio-url'):
            ui.mount_canvas(frozen['model_id'],self.manifest,data,None,frozen=frozen)
            self.assertEqual(mounted['data']['tags'],frozen['tags'])
            render.assert_not_called();mounted['on_exposure_change']()
            state['ambient_study_canvas']={'event':{'kind':'play','context':'frozen:test','id':self.ids[0]}}
            mounted['on_event_change']()
            render.assert_called_once_with(self.manifest['inventory'][0]['metadata'],15)
            state['ambient_study_canvas']={'event':{'kind':'exposure'}};mounted['on_event_change']()

    def test_policy_and_name_validation(self):
        with self.assertRaises(ValueError):models.save_model(self.session,' ')
        self.manifest['feedback_policy']='Feedback Hidden'
        with patch.object(store,'load_session',return_value=(self.manifest,self.state)):
            with self.assertRaisesRegex(ValueError,'Reveal'):models.save_model(self.session,'Hidden')
