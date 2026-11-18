"""Small known-distance checks for read-only neighborhood diagnostics."""
import copy
from itertools import combinations
import math
import unittest
import ambient_study_neighborhood as local
from ambient_study_store import pair_key


def pairs_for(ids,judgments):
    pairs={}
    for a,b in combinations(ids,2):
        value=judgments.get(pair_key(a,b))
        counts=[0]*4
        if value is not None:counts[value]=1
        pairs[pair_key(a,b)]=dict(ids=[a,b],valid_count=int(value is not None),relatedness=value,counts=counts,uncertain_count=0)
    return pairs


class NeighborhoodChecks(unittest.TestCase):
    def test_unique_pairs_denominators_and_unknowns(self):
        ids=list('abcd');x=dict(zip(ids,[[0,0],[1,0],[3,0],[10,0]]))
        pairs=pairs_for(ids,{'a|b':3,'b|c':0});pairs['a|b'].update(valid_count=2,counts=[0,0,0,2])
        before=copy.deepcopy((pairs,x));result=local.evaluate(ids,pairs,x,(1,3,5));m=result['metrics']['1']
        self.assertEqual(m['neighbor_pair_count'],3) # AB counted once despite mutual selection
        self.assertEqual(m['observed_denominator'],2)
        self.assertEqual(m['positive_precision'],.5);self.assertEqual(m['false_neighbor_rate'],.5)
        self.assertEqual(m['unknown_neighbor_rate'],1/3)
        self.assertEqual(m['strong_recall'],1);self.assertEqual(m['strong_mutual_recall'],1)
        self.assertEqual(m['single_observation_pairs'],1);self.assertEqual(m['repeated_observation_pairs'],1)
        self.assertEqual(result['metrics']['3']['unknown_neighbor_rate'],4/6)
        self.assertEqual(result['metrics']['5']['effective_k'],3)
        self.assertAlmostEqual(result['observed_distance_rms'],math.sqrt(2))
        self.assertEqual((pairs,x),before)

    def test_one_endpoint_and_mutual_recall(self):
        ids=list('abcde');x={i:[v,0] for i,v in zip(ids,[0,1,2,3,10])}
        pairs=pairs_for(ids,{'d|e':3})
        result=local.evaluate(ids,pairs,x)
        self.assertEqual(result['metrics']['3']['strong_recall'],1)
        self.assertEqual(result['metrics']['3']['strong_mutual_recall'],0)
        self.assertEqual(result['metrics']['5']['strong_mutual_recall'],1)

    def test_depth_and_stable_distance_ties(self):
        ids=list('abcd');pairs=pairs_for(ids,{'a|b':3})
        flat={'a':[0,0],'b':[.1,0],'c':[1,0],'d':[-1,0]}
        depth={i:point+[10 if i=='b' else 0] for i,point in flat.items()}
        two=local.evaluate(ids,pairs,flat,(1,));three=local.evaluate(ids,pairs,depth,(1,))
        self.assertEqual(two['neighbors']['1']['a'],['b']);self.assertEqual(three['neighbors']['1']['a'],['c'])
        self.assertAlmostEqual(three['per_stimulus']['a']['strongest_partners'][0]['distance'],math.sqrt(100.01))
        reverse=list(reversed(ids))
        self.assertEqual(three['neighbors'],local.evaluate(reverse,pairs,depth,(1,))['neighbors'])

    def test_conflicting_repeats_uncertain_and_disconnected(self):
        ids=list('abcd');x={i:[k,0] for k,i in enumerate(ids)}
        pairs=pairs_for(ids,{'a|b':0,'c|d':2})
        pairs['a|b'].update(valid_count=2,counts=[1,0,0,1]) # existing lower median remains zero
        pairs['b|c']['uncertain_count']=1
        result=local.evaluate(ids,pairs,x)
        m=result['metrics']['3'];self.assertEqual(m['conflicting_repeated_pairs'],1)
        self.assertEqual(m['unknown_count'],4);self.assertEqual(m['unrelated_count'],1)
        self.assertIsNone(m['strong_recall'])
        self.assertEqual(result['problems']['close_unrelated'][0]['evidence'],'Conflicting repeated judgments')
        self.assertTrue(any(p['status']=='Unable-to-judge only' for p in result['problems']['close_unknown']))
        # Empty/disconnected observations don't invent evidence or refit coordinates.
        empty=local.evaluate(ids,pairs_for(ids,{}),x)
        self.assertIsNone(empty['metrics']['3']['positive_precision'])
        self.assertEqual(empty['metrics']['3']['unknown_neighbor_rate'],1)
        self.assertIsNone(empty['observed_distance_rms'])

    def test_ordered_positive_distances_and_tied_categories(self):
        ids=list('abcd');x={'a':[0,0],'b':[1,0],'c':[3,0],'d':[7,0]}
        pairs=pairs_for(ids,{'a|b':3,'b|c':2,'c|d':1,'a|c':2})
        result=local.evaluate(ids,pairs,x)
        self.assertGreater(result['positive_diagnostics']['spearman_dissimilarity_distance'],.9)
        medians=[result['positive_level_distances'][str(k)]['normalized_median'] for k in [3,2,1]]
        self.assertTrue(medians[0]<medians[1]<medians[2])
        malformed=copy.deepcopy(pairs);malformed['b|a']=malformed.pop('a|b')
        with self.assertRaisesRegex(ValueError,'Noncanonical'):local.evaluate(ids,malformed,x)


if __name__=='__main__':unittest.main()
