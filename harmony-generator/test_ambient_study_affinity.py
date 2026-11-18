"""Focused Affinity checks; temporary stores only, no user trials are edited."""
import copy
import itertools
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import numpy as np
import ambient_study_affinity as affinity
import ambient_study_analysis as ordinal
import ambient_study_store as store


def fixture():
    rng=np.random.default_rng(4)
    points=np.concatenate([rng.normal(scale=.25,size=(6,3))+[-1,0,0],rng.normal(scale=.25,size=(6,3))+[1,0,0]])
    ids=list(map(str,range(12)));pairs={}
    lengths=[np.linalg.norm(points[i]-points[j]) for i,j in itertools.combinations(range(12),2) if (i<6)==(j<6)]
    cuts=np.quantile(lengths,[1/3,2/3])
    for i,j in itertools.combinations(range(12),2):
        value=3-int(np.searchsorted(cuts,np.linalg.norm(points[i]-points[j]))) if (i<6)==(j<6) else 0
        counts=[0]*4;counts[value]=1
        pairs[store.pair_key(ids[i],ids[j])]=dict(ids=[ids[i],ids[j]],relatedness=value,valid_count=1,counts=counts)
    return ids,pairs,points


class AffinityChecks(unittest.TestCase):
    def test_gradient_and_one_sided_absence(self):
        ids,pairs,x=fixture();problem=affinity.prepare(ids,pairs,affinity.PARAMETERS)
        x=affinity.normalize(x,problem);value,g,components,d,_=affinity.evaluate(x,problem)
        self.assertLess(affinity.evaluate(x*2,problem)[2]['absence'],1e-12) # no penalty beyond margin
        for i,k in [(0,0),(2,1),(10,2)]:
            plus=x.copy();minus=x.copy();plus[i,k]+=1e-6;minus[i,k]-=1e-6
            numerical=(affinity.evaluate(plus,problem)[0]-affinity.evaluate(minus,problem)[0])/2e-6
            self.assertAlmostEqual(g[i,k],numerical,places=6)
        compact=x*.25
        self.assertGreater(affinity.evaluate(compact,problem)[2]['absence'],0)
        # The fixed scale restores the same configuration after uniform expansion/collapse.
        np.testing.assert_allclose(affinity.normalize(x*.001,problem),x,atol=1e-12)
        np.testing.assert_allclose(affinity.normalize(x*1000,problem),x,atol=1e-12)

    def test_both_dimensions_missing_ties_and_objective(self):
        ids,pairs,_=fixture();settings=dict(seed=1729,starts=4,max_iterations=1000,tolerance=1e-8)
        for n in (2,3):
            result=affinity.fit_affinity(ids,pairs,settings,n_components=n)
            self.assertEqual({len(p) for p in result['coordinates'].values()},{n})
            self.assertLess(result['objective'],.04)
            self.assertGreater(result['positive_diagnostics']['spearman_dissimilarity_distance'],.5)
            self.assertLess(result['absence_diagnostics']['mean_shortfall'],.1)
            self.assertTrue(all(s['maximum_increase']<=1e-10 and s['loss']<=s['initial'] for s in result['start_diagnostics']))
            self.assertEqual(result,affinity.fit_affinity(ids,pairs,settings,n_components=n))
        conflicting=copy.deepcopy(pairs);conflicting['0|1'].update(valid_count=4,relatedness=0,counts=[2,0,0,2])
        self.assertTrue(np.isfinite(affinity.fit_affinity(ids,conflicting,settings)['objective']))
        pairs['0|1']['valid_count']=0
        first=affinity.fit_affinity(ids,pairs,settings)
        pairs['0|1']['relatedness']=0 # no new absence penalty for this missing pair
        self.assertEqual(first,affinity.fit_affinity(ids,pairs,settings))

    def test_cache_parameters_export_and_preservation(self):
        identity=uuid.uuid4().hex
        manifest=dict(session_id=identity,schema_version=store.SCHEMA,settings=copy.deepcopy(store.SETTINGS),
                      inventory=[dict(stimulus_id=str(i)) for i in range(12)])
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'STUDY_DIR',Path(tmp)):
            folder=store.folder(identity);folder.mkdir();(folder/'.lock').touch()
            store.atomic(folder/'manifest.json',manifest);store.atomic(folder/'state.json',{})
            baseline=ordinal.analyze(identity);original=(folder/'analysis.json').read_bytes()
            result=affinity.analyze(identity);self.assertEqual(result,affinity.analyze(identity))
            self.assertEqual((folder/'analysis.json').read_bytes(),original)
            self.assertNotEqual(result['input_hash'],affinity.analyze(identity,parameters={'absence_margin':1.1})['input_hash'])
            # Restore defaults so the default cache reader can reuse it.
            result=affinity.analyze(identity)
            self.assertEqual(result,ordinal.cached_result(identity,2,'Affinity'))
            self.assertEqual(ordinal.cached_result(identity,2,'Ordinal'),baseline)
            exported=store.export_session(identity)
            self.assertFalse(exported['derived_affinity']['2D']['stale'])
            self.assertEqual(exported['manifest'],manifest);self.assertEqual(exported['submitted_trials'],[])
            self.assertEqual(exported['derived_analysis']['input_hash'],baseline['input_hash'])
            self.assertEqual(store.read(folder/'manifest.json'),manifest)
            self.assertNotEqual(result['input_hash'],affinity.fingerprint(identity,manifest['settings']['analysis'],[{'revision':1}],2,affinity.PARAMETERS))
            self.assertNotEqual(result['input_hash'],affinity.fingerprint(identity,manifest['settings']['analysis'],[],3,affinity.PARAMETERS))


if __name__=='__main__':unittest.main()
