"""Focused template, relationship, constraint and compatibility regression checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ambient_chord_targeting as target


def assert_harmony(test, stimulus):
    selected=stimulus['selection_settings']
    count=selected['voice_count']
    for index,state in enumerate(stimulus['states']):
        chord=state['chord'];notes=state['notes_midi']
        expected={(chord['root_pitch_class']+i)%12 for i in chord['selected_harmonic_intervals']}
        test.assertEqual({n%12 for n in notes},expected)
        test.assertEqual(notes,chord['notes_midi'])
        test.assertEqual(notes,sorted(set(notes)))
        test.assertEqual(len(notes),count)
        test.assertTrue(all(selected['register_low']<=n<=selected['register_high'] for n in notes))
        test.assertEqual(chord['distinct_pitch_class_count'],len(expected))
        test.assertEqual(sum(d['extra_voices'] for d in chord['octave_doublings']),count-len(expected))
        if index:
            previous=stimulus['states'][index-1]['notes_midi']
            delta=[b-a for a,b in zip(previous,notes)]
            test.assertTrue(1<=sum(d!=0 for d in delta)<=min(selected['maximum_voices_moved'],count-int(selected['hold_bass_note'])))
            test.assertTrue(all(abs(d)<=selected['maximum_voice_movement_semitones'] for d in delta))
            test.assertEqual(state['total_voice_leading_distance'],sum(map(abs,delta)))
            test.assertEqual([v['displacement_semitones'] for v in state['voices']],delta)
            if selected['hold_bass_note']:test.assertEqual(notes[0],stimulus['states'][0]['notes_midi'][0])
            relation=state['target_relationship']
            local=relation['local_tonal_collection']
            if local:
                for c in (chord,stimulus['states'][index-1]['chord']):
                    test.assertTrue({(c['root_pitch_class']+i)%12 for i in c['template_intervals_from_root']}<=set(local['pitch_classes']))
            if relation['class']=='Common-Tone Relationships':
                test.assertTrue(expected & {n%12 for n in previous})
            if relation['class']=='Chromatic Relationships':
                test.assertIn(relation['root_or_reference_shift_semitones'],target.CHROMATIC_ROOT_SHIFTS)
    json.dumps(stimulus,allow_nan=False)


class ChordTargetingTests(unittest.TestCase):
    def test_meaningful_sample_and_quality_changes(self):
        transitions=set()
        for seed in range(60):
            s=target.generate_targeted(48,72,'Basic',3,'Triadic',3,3,7,False,'Mixed',seed=seed)
            assert_harmony(self,s)
            transitions.update((a['chord']['intended_quality'],b['chord']['intended_quality']) for a,b in zip(s['states'],s['states'][1:]))
        self.assertTrue({('major triad','major triad'),('major triad','minor triad'),('minor triad','major triad')}<=transitions)

    def test_families_voice_counts_and_relationships(self):
        for count in (2,3,4,5):
            for family in target.FAMILIES[1:]:
                for relationship in target.RELATIONSHIPS:
                    with self.subTest(count=count,family=family,relationship=relationship):
                        s=target.generate_targeted(48,72,'Expanded',count,family,3,count,7,False,relationship,seed=26)
                        assert_harmony(self,s)
                        self.assertTrue(all(state['chord']['harmonic_family']==family for state in s['states']))
                        if relationship=='Diatonic Relationships':
                            contexts=[state['target_relationship']['local_tonal_collection'] for state in s['states'][1:]]
                            self.assertEqual(contexts[0],contexts[1])

    def test_one_two_three_states_seed_and_held_bass(self):
        for state_count in (1,2,3):
            for voices in (2,3,4,5):
                s=target.generate_targeted(48,72,'Expanded',voices,'All',state_count,3,2,True,'Common-Tone Relationships',seed=8)
                assert_harmony(self,s)
                again=target.generate_targeted(48,72,'Expanded',voices,'All',state_count,3,2,True,'Common-Tone Relationships',seed=8)
                self.assertEqual(s['states'],again['states'])
                self.assertEqual(s['chord_targeting'],again['chord_targeting'])
                self.assertEqual(len(s['states']),state_count)

    def test_quality_weights_and_neutral_family(self):
        pool=target.catalog('Expanded',4,'Seventh',48,72)
        sums={}
        for balance in target.QUALITY_BALANCES:
            weights=target.sampling_weights(pool,balance)
            self.assertAlmostEqual(sum(weights),1)
            sums[balance]={category:sum(w for t,w in zip(pool,weights) if t.quality==category) for category in ('major','minor')}
        self.assertAlmostEqual(sums['Balanced']['major'],sums['Balanced']['minor'])
        self.assertAlmostEqual(sums['Favor Major']['major']/sums['Favor Major']['minor'],3)
        self.assertAlmostEqual(sums['Favor Minor']['minor']/sums['Favor Minor']['major'],3)
        self.assertAlmostEqual(sums['Original Vocabulary Weights']['major']/sums['Original Vocabulary Weights']['minor'],2)
        neutral=target.catalog('Expanded',4,'Quartal/Interval-based',48,72)
        self.assertEqual(target.sampling_weights(neutral,'Balanced'),target.sampling_weights(neutral,'Favor Major'))

    def test_voicing_optimum_and_specific_relationships(self):
        pool=target.catalog('Basic',3,'Triadic',48,72)
        def find(root,name):return next(t for t in pool if t.root==root and t.name==name)
        previous=find(0,'major triad')
        for root,name in [(5,'major triad'),(9,'minor triad'),(4,'major triad')]:
            dest=find(root,name);result=target.optimize_voicing((60,64,67),dest,3,7)
            self.assertIsNotNone(result)
            candidates=[n for n in dest.voicings if n!=(60,64,67) and all(abs(a-b)<=7 for a,b in zip(n,(60,64,67)))]
            self.assertEqual(result[1][0],min(sum(abs(a-b) for a,b in zip(n,(60,64,67))) for n in candidates))
        self.assertTrue(target.related(previous,find(5,'major triad'),'Diatonic Relationships'))
        self.assertTrue(target.related(previous,find(4,'major triad'),'Chromatic Relationships'))
        self.assertTrue(target.related(previous,find(9,'minor triad'),'Common-Tone Relationships'))
        self.assertIsNotNone(target.optimize_voicing((60,63,67),find(4,'major triad'),3,7))
        # Basic's locked root-position bass cannot change quality within a single
        # major/natural-minor collection. Failure is finite and explicit.
        with self.assertRaisesRegex(ValueError,'8 bounded initial attempts'):
            target.generate_targeted(48,72,'Basic',3,'Triadic',3,3,7,True,'Diatonic Relationships',seed=4)
        self.assertIsNone(target.optimize_voicing((60,64,67),find(5,'major triad'),1,1,True))

    def test_render_library_and_frozen_study_round_trip(self):
        import ambient_app as app
        import ambient_library as library
        import ambient_study_store as study
        from ambient_saved import reconstruct
        stimulus=app.generate_batch(4,None,None,48,72,3,3,7,'Expanded',(3,4),'All',generation_framework='chord_targeting')[0]
        metadata,wav=app.render_stimulus(stimulus,0,10,'Sine',False,'Procedural',None,None,None,'Dry',.3,display=False)
        with tempfile.TemporaryDirectory() as tmp,patch.object(library,'LIBRARY_DIR',Path(tmp)/'library'),patch.object(study,'STUDY_DIR',Path(tmp)/'studies'):
            records=[]
            for i in range(12):
                value=copy.deepcopy(metadata);value['stimulus_id']=f'{i:032x}'
                record,_=library.save_stimulus(value);records.append(record)
            record=records[0]
            library.set_favorite(record['saved_id'],True)
            library.set_status(records[1]['saved_id'],'bypassed',dict(incoherent_or_multi_emotional=True,overly_unpleasant=False))
            self.assertEqual(reconstruct(library.read_record(record['saved_id'])['metadata'],app.cached_audio),wav)
            exported=library.export_collection()
            self.assertTrue(exported['stimuli'])
            identity=study.create_session('Targeted',records,'Exploratory')
            manifest,_=study.load_session(identity)
            frozen=manifest['inventory'][0]['metadata']
            library.set_tag(record['saved_id'],'library tag')
            self.assertEqual(study.load_session(identity)[0]['inventory'][0]['metadata'],frozen)
            self.assertEqual(reconstruct(frozen,app.cached_audio),wav)
            self.assertEqual(frozen['generation_framework'],'chord_targeting')
            self.assertFalse(list(Path(tmp).rglob('*.wav')))
            json.dumps(study.export_session(identity),allow_nan=False)


if __name__=='__main__':unittest.main()
