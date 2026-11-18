"""Focused NumPy-only ordinal MDS checks; no persisted sessions are touched."""
import itertools
import unittest
import numpy as np
import ambient_study_analysis as analysis
import ambient_study_store as store


def pooled_projection(distances, ranks, weights):
    """Independent exhaustive pooling reference (at most 8 partitions)."""
    levels = sorted(set(ranks))
    groups = [np.flatnonzero(ranks == level) for level in levels]
    masses = np.array([weights[g].sum() for g in groups])
    means = np.array([np.average(distances[g], weights=weights[g]) for g in groups])
    best = None
    for cuts in itertools.product((False, True), repeat=len(groups)-1):
        bounds = [0]+[i+1 for i, cut in enumerate(cuts) if cut]+[len(groups)]
        values = np.empty(len(groups))
        for lo, hi in zip(bounds, bounds[1:]):
            values[lo:hi] = np.average(means[lo:hi], weights=masses[lo:hi])
        if np.any(np.diff(values) < -1e-12):
            continue
        loss = float(np.sum(masses*(means-values)**2))
        if best is None or loss < best[0]:
            best = loss, values
    output = np.empty(len(distances))
    for g, value in zip(groups, best[1]):
        output[g] = value
    return output


def fixture(missing=False):
    points = np.random.default_rng(7).normal(size=(12, 2))
    ids = [str(i) for i in range(len(points))]
    edges = list(itertools.combinations(range(len(ids)), 2))
    lengths = np.array([np.linalg.norm(points[i]-points[j]) for i,j in edges])
    cuts = np.quantile(lengths, [.25, .5, .75])
    pairs = {}
    for k, ((i,j), d) in enumerate(zip(edges,lengths)):
        value = 3-int(np.searchsorted(cuts,d))
        count = 0 if missing and k % 5 == 0 else 1+k % 4
        counts = [0]*4; counts[value] = count
        pairs[store.pair_key(ids[i],ids[j])] = dict(ids=[ids[i],ids[j]],valid_count=count,
            relatedness=value if count else None,counts=counts)
    return ids,pairs


class OrdinalMDSChecks(unittest.TestCase):
    def test_weighted_missing_reference_and_stress(self):
        ids,pairs = fixture(missing=True)
        settings = dict(seed=1729, starts=1, max_iterations=60, tolerance=0)
        result = analysis.fit_ordinal(ids,pairs,settings)
        observed = [p for p in pairs.values() if p['valid_count']]
        ix = {identity:i for i,identity in enumerate(ids)}
        a = np.array([ix[p['ids'][0]] for p in observed]); b = np.array([ix[p['ids'][1]] for p in observed])
        weights = np.array([min(p['valid_count'],3) for p in observed],float)
        ranks = np.array([3-p['relatedness'] for p in observed])
        distances = lambda x: np.linalg.norm(x[a]-x[b],axis=1)
        # Independently express unconstrained weighted raw-stress Guttman steps.
        incidence = np.zeros((len(a),len(ids)))
        incidence[np.arange(len(a)),a]=1;incidence[np.arange(len(a)),b]=-1
        laplacian = incidence.T @ (weights[:,None]*incidence)
        x = np.random.default_rng(settings['seed']).normal(size=(len(ids),2))
        x -= x.mean(0); x /= np.sqrt(np.average(distances(x)**2,weights=weights))
        for _ in range(settings['max_iterations']):
            d = distances(x); delta = pooled_projection(d,ranks,weights)
            delta /= np.sqrt(np.average(delta**2,weights=weights))
            forces = (weights*delta/np.maximum(d,1e-10))[:,None]*(incidence@x)
            x = np.linalg.lstsq(laplacian,incidence.T@forces,rcond=None)[0]
        reference = distances(x);reference /= np.sqrt(np.average(reference**2,weights=weights))
        coordinates = np.array([result['coordinates'][i] for i in ids]);actual = distances(coordinates)
        np.testing.assert_allclose(reference,actual,atol=2e-10)
        projection = pooled_projection(actual,ranks,weights)
        expected = np.sqrt(np.average((actual-projection)**2,weights=weights)/np.average(actual**2,weights=weights))
        self.assertAlmostEqual(result['observed_stress1'],expected,12)
        for start in result['start_diagnostics']:
            self.assertLessEqual(start['maximum_objective_increase'],1e-10)
            self.assertLess(start['final_objective'],start['initial_objective'])
        # Missing-pair pseudo-values never enter the objective.
        for p in pairs.values():
            if not p['valid_count']:p['relatedness']=3
        self.assertEqual(result,analysis.fit_ordinal(ids,pairs,settings))

    def test_consistent_ties_order_and_determinism(self):
        ids,pairs = fixture()
        settings = dict(seed=1729,starts=8,max_iterations=800,tolerance=1e-8)
        result = analysis.fit_ordinal(ids,pairs,settings)
        self.assertGreater(result['diagnostics']['spearman_dissimilarity_distance'],.85)
        disparity = list(result['fitted_disparities'].values())
        self.assertTrue(np.all(np.diff(disparity)>=-1e-12))
        self.assertEqual(result,analysis.fit_ordinal(ids,pairs,settings))

    def test_disconnected_and_sparse_gates(self):
        ids,pairs = fixture()
        for p in pairs.values():
            i,j=map(int,p['ids'])
            p['valid_count'] = int((i<6)==(j<6))
        settings = store.SETTINGS['analysis']
        reasons,_ = analysis.sufficiency(ids,pairs,settings)
        self.assertTrue(any('disconnected' in r for r in reasons))
        with self.assertRaisesRegex(ValueError,'Disconnected'):
            analysis.fit_ordinal(ids,pairs,settings)
        for p in pairs.values():
            i,j=map(int,p['ids']);p['valid_count']=int(j==i+1)
        reasons,_=analysis.sufficiency(ids,pairs,settings)
        self.assertTrue(reasons)
        self.assertTrue(analysis.connected(ids,[p['ids'] for p in pairs.values() if p['valid_count']]))

    def test_conflicts_uncertain_and_lower_median(self):
        manifest={'inventory':[{'stimulus_id':i} for i in ['b','a','c','d']]}
        trials=[dict(trial_id=str(n),sequence=n,submitted_at='test',stimulus_ids=['a','b','c','d'],
                     pairs=[dict(ids=['a','b'] if n%2 else ['b','a'],submitted=v)])
                for n,v in enumerate([0,3,3,0,None])]
        summary=store.summarize(manifest,trials)
        pair=summary['pairs']['a|b']
        self.assertEqual(pair['counts'],[2,0,0,2]);self.assertEqual(pair['relatedness'],0)
        self.assertEqual(pair['valid_count'],4);self.assertEqual(pair['uncertain_count'],1)
        self.assertEqual(pair['disagreement'],.5)

    def test_genuine_3d_cube_and_consistent_diagnostics(self):
        points=np.array(list(itertools.product((-1.,1.),repeat=3)))
        ids=[str(i) for i in range(len(points))];pairs={}
        for i,j in itertools.combinations(range(len(ids)),2):
            differing=int(np.count_nonzero(points[i]!=points[j]));value={1:3,2:2,3:0}[differing]
            counts=[0]*4;counts[value]=1
            pairs[store.pair_key(ids[i],ids[j])]=dict(ids=[ids[i],ids[j]],valid_count=1,relatedness=value,counts=counts)
        settings=dict(seed=1729,starts=16,max_iterations=1000,tolerance=1e-8)
        two=analysis.fit_ordinal(ids,pairs,settings,n_components=2)
        three=analysis.fit_ordinal(ids,pairs,settings,n_components=3)
        self.assertEqual({len(p) for p in three['coordinates'].values()},{3})
        self.assertEqual(np.linalg.matrix_rank(np.array(list(three['coordinates'].values()))),3)
        self.assertLess(three['observed_stress1'],.01)
        self.assertLess(three['observed_stress1'],two['observed_stress1'])
        self.assertLess(three['diagnostics']['order_violation_fraction'],two['diagnostics']['order_violation_fraction'])
        self.assertGreater(three['diagnostics']['spearman_dissimilarity_distance'],two['diagnostics']['spearman_dissimilarity_distance'])
        self.assertEqual(three,analysis.fit_ordinal(ids,pairs,settings,n_components=3))
        self.assertTrue(all(start['maximum_objective_increase']<=1e-10 for start in three['start_diagnostics']))

    def test_dimension_cache_and_export(self):
        import tempfile,uuid,copy
        from pathlib import Path
        from unittest.mock import patch
        identity=uuid.uuid4().hex
        ids,pairs=fixture();settings=copy.deepcopy(store.SETTINGS)
        manifest=dict(session_id=identity,schema_version=store.SCHEMA,settings=settings,
                      inventory=[dict(stimulus_id=i) for i in ids])
        # Empty trials exercise independent insufficient-data caches without any rendering.
        with tempfile.TemporaryDirectory() as tmp,patch.object(store,'STUDY_DIR',Path(tmp)):
            folder=store.folder(identity);folder.mkdir();(folder/'.lock').touch()
            store.atomic(folder/'manifest.json',manifest);store.atomic(folder/'state.json',{})
            before=(folder/'manifest.json').read_bytes()
            two=analysis.analyze(identity,2);cache=(folder/'analysis.json').read_bytes()
            three=analysis.analyze(identity,3)
            self.assertNotEqual(two['input_hash'],three['input_hash'])
            self.assertEqual((folder/'analysis.json').read_bytes(),cache)
            with patch.object(analysis,'fit_ordinal',side_effect=AssertionError('Unexpected refit')):
                self.assertEqual(two,analysis.analyze(identity,2));self.assertEqual(three,analysis.analyze(identity,3))
            exported=store.export_session(identity)
            self.assertFalse(exported['derived_analysis']['stale']);self.assertFalse(exported['derived_analysis_3d']['stale'])
            self.assertEqual(exported['derived_analysis_3d']['n_components'],3)
            self.assertEqual(exported['submitted_trials'],[])
            self.assertEqual((folder/'manifest.json').read_bytes(),before)

    def test_uniform_display_geometry(self):
        from ambient_study import plot_positions
        x=np.random.default_rng(10).normal(size=(12,2))*[2,5]
        ids=[str(i) for i in range(12)]
        plotted=plot_positions(dict(zip(ids,x.tolist())))
        y=np.array([[plotted[i]['x']*1000,plotted[i]['y']*600] for i in ids])
        ratios=[np.linalg.norm(y[i]-y[j])/np.linalg.norm(x[i]-x[j]) for i,j in itertools.combinations(range(12),2)]
        self.assertLess(np.ptp(ratios),1e-10)


if __name__=='__main__':unittest.main()
