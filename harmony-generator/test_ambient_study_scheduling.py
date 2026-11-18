"""Focused coverage scheduling checks; all mutations use temporary sessions."""
import copy
import itertools
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import ambient_study_store as store


def manifest(n=8):
    return dict(session_id=uuid4().hex,schema_version=store.SCHEMA,created_at='test',feedback_policy='Exploratory',
                inventory=[dict(stimulus_id=str(i)) for i in range(n)],settings=copy.deepcopy(store.SETTINGS))


def trial(ids,sequence,unknown=()):
    return dict(trial_id=uuid4().hex,sequence=sequence,stimulus_ids=list(ids),submitted_at='test',
                pairs=[dict(ids=sorted((a,b)),submitted=None if store.pair_key(a,b) in unknown else 2)
                       for a,b in itertools.combinations(ids,2)])


def comparable(p):
    return {k:p[k] for k in ('stimulus_ids','presentation_order','initial_positions','sequence')}


class SchedulingChecks(unittest.TestCase):
    def test_exhaustive_maximum_and_reproducibility(self):
        m=manifest();ids=[p['stimulus_id'] for p in m['inventory']];rng=random.Random(10)
        for count in (0,2,5,10,30):
            completed=[trial(rng.sample(ids,4),i) for i in range(count)]
            summary=store.summarize(m,completed)
            state=dict(scheduler_seed=1729,scheduling_mode='Coverage First')
            result=store.schedule(m,state,completed)
            maximum=max(store.new_pair_count(group,summary) for group in itertools.combinations(ids,4))
            self.assertEqual(store.new_pair_count(result['stimulus_ids'],summary),maximum)
            self.assertEqual(comparable(result),comparable(store.schedule(m,state,completed)))
            self.assertEqual(result['scheduler']['candidate_count'],70)
            self.assertEqual(len(set(result['stimulus_ids'])),4)

    def test_secondary_criteria_cannot_sacrifice_only_new_pair(self):
        m=manifest(6);ids=[p['stimulus_id'] for p in m['inventory']]
        unknown={'0|1'}
        completed=[trial(group,i,unknown) for i,group in enumerate(itertools.combinations(ids,4))]
        completed.extend(trial(['0','1','2','3'],100+i,unknown) for i in range(1000))
        result=store.schedule(m,dict(scheduler_seed=1,scheduling_mode='Coverage First'),completed)
        self.assertTrue({'0','1'}<=set(result['stimulus_ids']))
        self.assertEqual(result['scheduler']['new_pair_count'],1)

    def test_full_coverage_falls_back_to_identical_adaptive_choice(self):
        m=manifest(6);completed=[trial(group,i) for i,group in enumerate(itertools.combinations([str(i) for i in range(6)],4))]
        state=dict(scheduler_seed=5,scheduling_mode='Coverage First')
        result=store.schedule(m,state,completed);reference=store._schedule_adaptive(m,state,completed)
        self.assertEqual(comparable(result),comparable(reference))
        self.assertEqual(result['scheduler']['seed'],reference['scheduler']['seed'])
        self.assertEqual(result['scheduler']['effective_mode'],'Adaptive')
        self.assertTrue(result['scheduler']['first_pass_complete'])
        self.assertEqual(state['scheduling_mode'],'Coverage First')
        self.assertEqual(result['scheduler']['new_pair_count'],0)
        adaptive=store.schedule(m,{**state,'scheduling_mode':'Adaptive'},completed)
        self.assertEqual(comparable(adaptive),comparable(reference))

    def test_legacy_pending_persistence_submission_and_export(self):
        m=manifest(12);identity=m['session_id']
        state=dict(name='Legacy',view='Arrange',scheduler_seed=13,revealed_at=None,collection_closed=False,exposures=[],view_token=uuid4().hex)
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'STUDY_DIR',Path(tmp)):
            folder=store.folder(identity);folder.mkdir();(folder/'.lock').touch()
            store.atomic(folder/'manifest.json',m);store.atomic(folder/'state.json',state)
            old=store._schedule_adaptive(m,state,[]);store.atomic(folder/'pending.json',old)
            original=(folder/'pending.json').read_bytes();frozen=(folder/'manifest.json').read_bytes()
            self.assertEqual(store.load_session(identity)[1]['scheduling_mode'],'Coverage First')
            self.assertEqual(store.ensure_pending(identity),old)
            self.assertEqual(store.summarize(m,store.trials(identity)[0])['observed_pairs'],0)
            store.update_state(identity,scheduling_mode='Adaptive')
            self.assertEqual(store.load_session(identity)[1]['scheduling_mode'],'Adaptive')
            subprocess.run([sys.executable,'-c',
                            "import sys,pathlib;sys.path.insert(0,sys.argv[1]);import ambient_study_store as s;s.STUDY_DIR=pathlib.Path(sys.argv[2]);assert s.load_session(sys.argv[3])[1]['scheduling_mode']=='Adaptive'",
                            str(Path(store.__file__).parent),tmp,identity],check=True)

            self.assertEqual(store.ensure_pending(identity),old)
            self.assertEqual((folder/'pending.json').read_bytes(),original)
            exported=store.export_session(identity)
            self.assertEqual(exported['operational_state']['scheduling_mode'],'Adaptive')
            self.assertEqual(exported['pending_trial'],old)
            store.update_state(identity,scheduling_mode='Coverage First')
            payload={k:copy.deepcopy(old[k]) for k in ('trial_id','positions','overrides','interactions')}
            payload.update(revision=1,confirmed=True)
            store.submit(identity,payload)
            summary=store.summarize(m,store.trials(identity)[0])
            self.assertEqual(summary['observed_pairs'],6)
            store.submit(identity,payload) # duplicate submission doesn't add coverage
            self.assertEqual(store.summarize(m,store.trials(identity)[0])['observed_pairs'],6)
            new=store.ensure_pending(identity)
            self.assertNotEqual(new['trial_id'],old['trial_id'])
            self.assertEqual(new['scheduler']['effective_mode'],'Coverage First')
            self.assertEqual((folder/'manifest.json').read_bytes(),frozen)
            with self.assertRaises(ValueError):store.update_state(identity,scheduling_mode='invalid')


if __name__=='__main__':unittest.main()
