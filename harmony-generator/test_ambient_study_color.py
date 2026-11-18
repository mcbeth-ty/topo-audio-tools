"""Fixed geometry, deterministic residual color, and snapshot compatibility."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import ambient_study_analysis as ordinal
import ambient_study_affinity as affinity
import ambient_study_color as color
from test_ambient_study_4d import fixture


class ConditionalColorTests(unittest.TestCase):
    def test_fixed_xyz_determinism_and_nonincreasing_conditional_loss(self):
        ids,pairs=fixture();settings={'seed':1729,'starts':3,'max_iterations':100,'tolerance':1e-8}
        for name,fit in [('Ordinal',ordinal.fit_ordinal),('Affinity',affinity.fit_affinity)]:
            embedding=fit(ids,pairs,settings,n_components=3)
            base={'input_hash':name,'settings':settings,'summary':{'pairs':pairs},'embedding':embedding}
            before=copy.deepcopy(base)
            result=color.fit_color(base,name);again=color.fit_color(base,name)
            self.assertEqual(result,again);self.assertEqual(base,before)
            for identity in ids:
                self.assertEqual(result['embedding']['coordinates'][identity][:3],embedding['coordinates'][identity])
            w=np.array([result['embedding']['coordinates'][i][3] for i in ids])
            self.assertTrue(np.isfinite(w).all());self.assertAlmostEqual(w.mean(),0.,places=10)
            self.assertLessEqual(result['embedding']['objective'],result['embedding']['baseline_objective'])
            self.assertEqual(result['settings']['n_components'],4)
            self.assertNotEqual(result['input_hash'],base['input_hash'])
            # Old frozen snapshots need only their stored 3D fit and pair summary.
            with patch.object(ordinal,'analyze',side_effect=AssertionError('Never refit snapshot XYZ')):
                self.assertEqual(color.extend_color(base,name),result)

    def test_unavailable_base_does_not_invent_coordinates(self):
        base={'input_hash':'none','settings':{},'embedding':{'status':'Insufficient data','reasons':['More observations needed']}}
        result=color.fit_color(base,'Ordinal')
        self.assertNotIn('coordinates',result['embedding'])
        self.assertEqual(result['embedding']['reasons'],base['embedding']['reasons'])
