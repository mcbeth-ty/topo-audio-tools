"""Focused random candidate selection and expanded study-size checks."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ambient_study as ui
import ambient_study_store as store


class StudySelectionTests(unittest.TestCase):
    def test_sampling_is_unique_filtered_and_seeded(self):
        records=[{'saved_id':f'{i:032x}'} for i in range(70)]
        usage={r['saved_id']:{'studies':[{'id':'existing'}]} for r in records[:5]}
        before=copy.deepcopy(records)
        for count in (10,24,40):
            chosen,pool=ui.sample_study_candidates(records,usage,count,True,42)
            self.assertEqual((len(chosen),len(set(chosen)),pool),(count,count,65))
            self.assertFalse(set(chosen)&set(usage))
            self.assertEqual(chosen,ui.sample_study_candidates(records,usage,count,True,42)[0])
        self.assertEqual(ui.sample_study_candidates(records,usage,40,False,42)[1],70)
        self.assertEqual(len(ui.sample_study_candidates(records[:4],{},24,True,42)[0]),4)
        self.assertEqual(records,before)
        for count in (9,41):
            with self.assertRaises(ValueError):ui.sample_study_candidates(records,{},count,True,42)

    def test_candidate_set_survives_reruns_and_audition_state(self):
        records=[{'saved_id':f'{i:032x}'} for i in range(70)]
        with patch.object(ui.st,'session_state',{}),patch.object(ui.random,'SystemRandom') as random_source:
            random_source.return_value.getrandbits.side_effect=range(11,20)
            first=copy.deepcopy(ui.study_candidate_set(records,{},24,True))
            ui.st.session_state['ambient_study_candidate_rows_audio']=('test',b'wav')
            self.assertEqual(ui.study_candidate_set(records,{},24,True),first)
            newer=ui.study_candidate_set(records,{},24,True,force=True)
            self.assertNotEqual(newer['ids'],first['ids'])
            smaller=ui.study_candidate_set(records,{},10,True)
            self.assertEqual(len(smaller['ids']),10)
            used=smaller['ids'][0]
            refreshed=ui.study_candidate_set(records,{used:{'studies':[{}]}},10,True)
            self.assertNotIn(used,refreshed['ids'])

    def test_favorites_fill_and_locked_randomization(self):
        records=[{'saved_id':f'{i:032x}','favorite':i<8} for i in range(60)]
        favorites={r['saved_id'] for r in records[:8]}
        ids,pool=ui.sample_study_candidates(records,{},24,True,42,favorites=True)
        self.assertEqual(len(ids),24);self.assertTrue(favorites<=set(ids))
        many=[{**r,'favorite':True} for r in records]
        a=ui.sample_study_candidates(many,{},24,True,42,favorites=True)[0]
        b=ui.sample_study_candidates(many,{},24,True,43,favorites=True)[0]
        self.assertEqual(len(set(a)),24);self.assertNotEqual(a,b)
        locks=ids[:3]
        for seed in range(5):
            selected,_=ui.sample_study_candidates(records,{},24,True,seed,locks)
            self.assertEqual(len(set(selected)),24);self.assertTrue(set(locks)<=set(selected))
        excluded=records[0]['saved_id']
        selected,_=ui.sample_study_candidates(records,{excluded:{'studies':[{}]}},24,True,42,locks,True)
        self.assertNotIn(excluded,selected)
        with patch.object(ui.st,'session_state',{}):
            initial=ui.study_candidate_set(records,{},24,True)
            initial['locked_ids']=initial['ids'][:3]
            next_set=ui.study_candidate_set(records,{},24,True,force=True)
            self.assertEqual(next_set['locked_ids'],initial['locked_ids'])
            self.assertTrue(set(initial['locked_ids'])<=set(next_set['ids']))
            favorite_set=ui.study_candidate_set(records,{},24,True,favorites=True)
            self.assertTrue(favorites<=set(favorite_set['ids']))
            self.assertEqual(favorite_set['method'],'favorites_then_random')

    def test_initial_tags_inherit_prior_studies_without_overriding_library(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'STUDY_DIR',Path(tmp)):
            for name,date,tags in [('older','2026-01-01',{'a':'Earlier tag','b':'Other tag'}),
                                    ('newer','2026-02-01',{'a':'Recent tag','c':'Inherited tag'})]:
                folder=Path(tmp)/name;folder.mkdir()
                store.atomic(folder/'manifest.json',{'created_at':date})
                store.atomic(folder/'state.json',{'stimulus_tags':tags})
            before={p:p.read_bytes() for p in Path(tmp).rglob('*.json')}
            records=[{'saved_id':'a'},{'saved_id':'b','tag':'Library tag'},
                     {'saved_id':'c','tag':''},{'saved_id':'d'}]
            self.assertEqual(store.initial_stimulus_tags(records),{'a':'Recent tag','b':'Library tag','c':'Inherited tag'})
            self.assertTrue(all(p.read_bytes()==content for p,content in before.items()))

    def test_ten_and_forty_stimulus_frozen_sessions(self):
        import ambient_app as app
        stimulus=app.generate_batch(4,60,'major',48,72,1,3,2)[0]
        metadata,_=app.render_stimulus(stimulus,0,10,'Sine',False,'Procedural',None,None,None,'Dry',.3,display=False)
        records=[{'saved_id':f'{i:032x}','metadata':copy.deepcopy(metadata),'tag':f'Personal tag {i}'} for i in range(40)]
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'STUDY_DIR',Path(tmp)):
            for count in (10,40):
                provenance={'method':'random_saved_stimuli','requested_size':count,'selected_saved_ids':[r['saved_id'] for r in records[:count]]}
                identity=store.create_session(f'Set {count}',records[:count],'Exploratory',provenance)
                manifest,state=store.load_session(identity)
                self.assertEqual(state['stimulus_tags'],{r['saved_id']:r['tag'] for r in records[:count]})
                self.assertEqual(len(manifest['inventory']),count)
                self.assertEqual(manifest['inventory_selection'],provenance)
                self.assertEqual(len(store.ensure_pending(identity)['stimulus_ids']),4)
                self.assertEqual(store.export_session(identity)['manifest']['inventory_selection'],provenance)
            for count in (9,41):
                with self.assertRaises(ValueError):store.create_session('Invalid',(records*2)[:count],'Exploratory')
