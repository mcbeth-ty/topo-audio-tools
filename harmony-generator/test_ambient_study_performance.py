"""UI caches reuse unchanged inputs and invalidate when observations change."""
import unittest
from unittest.mock import patch
import ambient_study as ui


class ExploreCacheTests(unittest.TestCase):
    def test_neighborhood_cache_invalidates_on_new_evidence(self):
        ui._cached_neighborhood.clear()
        pairs={'a|b':{'valid_count':1}}
        with patch.object(ui.neighborhood,'evaluate',return_value={'metric':1}) as evaluate:
            first=ui._cached_neighborhood(['a','b'],pairs,{'a':[0,0,0],'b':[1,0,0]})
            first['metric']=99
            self.assertEqual(ui._cached_neighborhood(['a','b'],pairs,{'a':[0,0,0],'b':[1,0,0]})['metric'],1)
            self.assertEqual(evaluate.call_count,1)
            pairs['a|b']['valid_count']=2
            ui._cached_neighborhood(['a','b'],pairs,{'a':[0,0,0],'b':[1,0,0]})
            self.assertEqual(evaluate.call_count,2)

    def test_save_eligibility_cache_invalidates_on_new_evidence(self):
        ui._save_model_reasons.clear();pairs={'a|b':{'valid_count':1}}
        with patch.object(ui.analysis,'sufficiency',return_value=([],{})) as check:
            for _ in range(2):self.assertEqual(ui._save_model_reasons(['a','b'],pairs,{}),[])
            self.assertEqual(check.call_count,1)
            pairs['a|b']['valid_count']=2
            ui._save_model_reasons(['a','b'],pairs,{})
            self.assertEqual(check.call_count,2)
