"""Explicitly publish only the three curated demo snapshots, without raw trials."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from atlas_demo import MODEL_NAMES,_read_model
from atlas_assets import SOUNDFONT_SHA256
from ambient_library import validate_metadata
from ambient_harmony import time_states


def export_public_models(source,destination):
    records={}
    for path in source.glob('*.json'):
        record=json.loads(path.read_text());name=record.get('name','').lower().strip()
        if name in MODEL_NAMES:
            if name in records:raise ValueError(f'More than one snapshot is named {name}. Select the intended source explicitly.')
            records[name]=path
    if set(records)!=set(MODEL_NAMES):raise ValueError('Missing a requested public model.')
    destination.mkdir(parents=True,exist_ok=True)
    for name in MODEL_NAMES:
        path=records[name];stat=path.stat();public,recipes=_read_model(str(path),stat.st_size,stat.st_mtime_ns)
        inventory=[]
        for identity,metadata in recipes.items():
            audio=metadata['rendering']
            # Explicit allowlist, never participant/source identifiers or local paths.
            recipe={'chord':{'notes_midi':metadata['states'][0]['notes_midi']},'selection_settings':{},
                    'states':[{key:copy.deepcopy(state[key]) for key in ('notes_midi','notes_names','voices','start_seconds','end_seconds')} for state in metadata['states']],
                    'transitions':copy.deepcopy(metadata['transitions']),
                    'rendering':{key:copy.deepcopy(audio[key]) for key in ('duration_seconds','backend','timbre','reverb','effect_level','sample_rate','renderer_version','transition_overlap_seconds') if key in audio}}
            if audio['backend']=='SoundFont':
                if audio['soundfont']['sha256']!=SOUNDFONT_SHA256:raise ValueError('A public recipe uses a different SoundFont.')
                recipe['rendering']['soundfont']={**{key:audio['soundfont'][key] for key in ('sha256','bank','program')},'path':'GeneralUser-GS.sf2'}
                recipe['rendering']['native_reverb_settings']=copy.deepcopy(audio.get('native_reverb_settings'))
            recipe['rendering']['duration_seconds']=15
            recipe['transitions']=time_states(recipe['states'],15)
            validate_metadata(recipe)
            inventory.append({'stimulus_id':identity,'metadata':recipe})
        record={'schema_version':'affective-atlas-public-v1','name':name,
                'manifest':{'inventory':inventory},'fits':{'Ordinal:3D+color':{'embedding':{'coordinates':public['world_positions']}}},
                'summary':{'pairs':public['pairs']},'tags':public['tags']}
        text=json.dumps(record,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n'
        if '/Users/' in text or 'source_session_id' in text or 'submitted_at' in text:raise ValueError('Private provenance found in a public asset.')
        target=destination/(name.replace(' ','_')+'.json');target.write_text(text)
        print(f'{target.name}: {len(inventory)} stimuli, {len(text.encode())} bytes')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'data'/'ambient_models')
    parser.add_argument('--destination',type=Path,default=ROOT/'public_data'/'models')
    args=parser.parse_args();export_public_models(args.source,args.destination)
