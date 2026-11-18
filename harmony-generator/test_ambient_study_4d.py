"""4D model shape, full-distance diagnostics and isolated derived-cache checks."""
import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import numpy as np
import ambient_study_analysis as ordinal
import ambient_study_affinity as affinity
import ambient_study_neighborhood as neighborhood
import ambient_study_store as store


def fixture():
    ids=[f'{i:032x}' for i in range(12)]
    points=np.random.default_rng(11).normal(size=(12,4))
    edges=list(itertools.combinations(range(12),2))
    distances=np.array([np.linalg.norm(points[a]-points[b]) for a,b in edges])
    cuts=np.quantile(distances,[.25,.5,.75]);pairs={}
    for (a,b),d in zip(edges,distances):
        value=3-int(np.searchsorted(cuts,d));counts=[0]*4;counts[value]=1
        pairs[store.pair_key(ids[a],ids[b])]=dict(ids=[ids[a],ids[b]],valid_count=1,relatedness=value,counts=counts,uncertain_count=0,disagreement=0.)
    return ids,pairs


class FourDimensionTests(unittest.TestCase):
    def test_models_fit_four_coordinates_and_are_deterministic(self):
        ids,pairs=fixture();settings=dict(seed=1729,starts=3,max_iterations=100,tolerance=1e-8)
        for fit in (ordinal.fit_ordinal,affinity.fit_affinity):
            result=fit(ids,pairs,settings,n_components=4)
            points=np.array([result['coordinates'][i] for i in ids])
            self.assertEqual(points.shape,(12,4));self.assertTrue(np.isfinite(points).all())
            self.assertGreater(np.ptp(points[:,3]),.01)
            again=fit(ids,pairs,settings,n_components=4)
            np.testing.assert_array_equal(points,np.array([again['coordinates'][i] for i in ids]))
            self.assertEqual(neighborhood.evaluate(ids,pairs,result['coordinates'])['n_components'],4)

    def test_neighborhood_distances_include_fourth_coordinate(self):
        ids,pairs=fixture()
        coords={i:[0.,0.,0.,float(n)] for n,i in enumerate(ids)}
        evaluated=neighborhood.evaluate(ids,pairs,coords)
        near=evaluated['per_stimulus'][ids[0]]['nearest_5'][0]
        self.assertIn(ids[1],near['ids'])
        self.assertAlmostEqual(near['distance'],1.)

    def test_4d_cache_and_export_do_not_touch_other_dimensions_or_trials(self):
        ids,pairs=fixture();identity=uuid4().hex
        completed=[]
        for n,pair in enumerate(pairs.values()):
            group=pair['ids']+[i for i in ids if i not in pair['ids']][:2]
            completed.append(dict(trial_id=uuid4().hex,session_id=identity,sequence=n,submitted_at='test',stimulus_ids=group,
                                  pairs=[dict(ids=sorted((a,b)),submitted=pairs[store.pair_key(a,b)]['relatedness']) for a,b in itertools.combinations(group,2)]))
        manifest=dict(session_id=identity,schema_version=store.SCHEMA,inventory=[{'stimulus_id':i} for i in ids],
                      settings=copy.deepcopy(store.SETTINGS),feedback_policy='Exploratory')
        summary=store.summarize(manifest,completed)
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'STUDY_DIR',Path(tmp)), \
             patch.object(store,'load_session',return_value=(manifest,{'revealed_at':None})):
            root=store.folder(identity);root.mkdir()
            sentinels={'analysis.json':json.dumps({'model_version':ordinal.MODEL,'input_hash':'old-2d'}).encode(),
                       'analysis_3d.json':json.dumps({'model_version':ordinal.MODEL,'input_hash':'old-3d'}).encode(),
                       'pending.json':b'{}'}
            for trial in completed:
                sentinels[f"trials/{trial['trial_id']}.json"]=json.dumps(trial).encode()
            for name,content in sentinels.items():
                path=root/name;path.parent.mkdir(exist_ok=True);path.write_bytes(content)
            settings=dict(seed=1729,starts=2,max_iterations=80,tolerance=1e-8,minimum_degree=3,minimum_pair_coverage=.35)
            with patch.object(ordinal,'effective_settings',return_value=settings):
                for model in ('Ordinal','Affinity'):
                    fit=ordinal.analyze(identity,4,model)
                    self.assertEqual(fit['n_components'],4)
                    self.assertEqual(len(fit['embedding']['coordinates'][ids[0]]),4)
                    path=root/('analysis_4d.json' if model=='Ordinal' else 'analysis_affinity_4d.json')
                    before=path.read_bytes()
                    self.assertEqual(ordinal.analyze(identity,4,model)['input_hash'],fit['input_hash'])
                    self.assertEqual(path.read_bytes(),before)
                exported=store.export_session(identity)
                self.assertEqual(exported['derived_analysis_4d']['n_components'],4)
                self.assertEqual(exported['derived_affinity']['4D']['n_components'],4)
                self.assertFalse(exported['derived_analysis_4d']['stale'])
                self.assertFalse(exported['derived_affinity']['4D']['stale'])
            for name,content in sentinels.items():self.assertEqual((root/name).read_bytes(),content)
            self.assertEqual(len(summary['pairs']),66)
