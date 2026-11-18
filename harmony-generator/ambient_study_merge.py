"""Explicit data-only study union, preserving submitted evidence and provenance."""
import copy
import hashlib
import random
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import ambient_study_store as store


def merge_sessions(name,source_ids):
    name=name.strip()
    if not name:raise ValueError('A merged study needs a name.')
    source_ids=list(dict.fromkeys(source_ids))
    if len(source_ids)<2:raise ValueError('Select at least two source studies.')
    sessions,errors=store.list_sessions()
    if errors:raise ValueError('Repair unreadable studies before merging.')
    if any(s['name'].casefold()==name.casefold() for s in sessions):raise ValueError('A study with this name already exists; nothing was overwritten.')
    identity=uuid4().hex;inventory={};tags={};tag_sources={};completed=[];sources=[];seen={};settings=None
    checks={}
    for source_id in source_ids:
        with store.locked(source_id):
            manifest,state=store.load_session(source_id)
            rows,errors=store.trials(source_id)
            if errors:raise ValueError(f'Unreadable trials in {state["name"]}.')
            if manifest['feedback_policy']!='Exploratory' and not state.get('revealed_at'):
                raise ValueError('Reveal hidden study feedback before merging its evidence.')
            if settings is None:settings=copy.deepcopy(manifest['settings'])
            elif settings!=manifest['settings']:raise ValueError('Source studies have incompatible judgment/analysis settings.')
            files=[store.folder(source_id)/'manifest.json']+[store.folder(source_id)/'trials'/f'{r["trial_id"]}.json' for r in rows]
            for path in files:checks[path]=hashlib.sha256(path.read_bytes()).hexdigest()
            for item in manifest['inventory']:
                stimulus=item['stimulus_id']
                if stimulus in inventory and inventory[stimulus]['metadata']!=item['metadata']:
                    raise ValueError('Shared stimulus IDs have different frozen recipes; cannot merge safely.')
                inventory.setdefault(stimulus,copy.deepcopy(item))
            for stimulus,text in state.get('stimulus_tags',{}).items():
                tag_sources.setdefault(stimulus,[]).append({'session_id':source_id,'session_name':state['name'],'tag':text})
                tags[stimulus]=text
            for row in rows:
                original=copy.deepcopy(row)
                origin=row.get('imported_from',{})
                source_trial=origin.get('trial_id',row['trial_id']);source_study=origin.get('session_id',source_id)
                key=(source_study,source_trial)
                if key in seen:
                    if seen[key]!=row['pairs']:raise ValueError('Conflicting copies of an imported source trial.')
                    continue
                seen[key]=copy.deepcopy(row['pairs'])
                original.update(session_id=identity,trial_id=uuid4().hex,sequence=len(completed)+1)
                original['imported_from']={'session_id':source_study,'trial_id':source_trial,
                    'sequence':origin.get('sequence',row['sequence']),'copied_from_session_id':source_id,
                    'source_file_sha256':hashlib.sha256((store.folder(source_id)/'trials'/f'{row["trial_id"]}.json').read_bytes()).hexdigest()}
                completed.append(original)
            sources.append({'session_id':source_id,'name':state['name'],'stimulus_count':len(manifest['inventory']),
                            'submitted_trials':len(rows),'created_at':manifest['created_at']})
    manifest={'schema_version':store.SCHEMA,'session_id':identity,'created_at':store.now(),'initial_name':name,
              'build':store.build_info(),'settings':settings,'feedback_policy':'Exploratory','inventory':list(inventory.values()),
              'inventory_selection':{'method':'merged_study_union','sources':sources,'selected_saved_ids':list(inventory),
                                     'imported_trial_count':len(completed),'size_limit_exception':'Explicitly requested merged inventory; ordinary setup limits unchanged.'}}
    state={'name':name,'updated_at':store.now(),'view':'Arrange','scheduler_seed':random.SystemRandom().getrandbits(64),
           'scheduling_mode':'Coverage First','revealed_at':None,'collection_closed':False,'exposures':[],
           'view_token':uuid4().hex,'stimulus_tags':tags,'imported_tag_sources':tag_sources}
    summary=store.summarize(manifest,completed)
    pending=store.schedule(manifest,state,completed)
    store.STUDY_DIR.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.merging-',dir=store.STUDY_DIR))
    try:
        store.atomic(temporary/'manifest.json',manifest);store.atomic(temporary/'state.json',state)
        for trial in completed:store.atomic(temporary/'trials'/f'{trial["trial_id"]}.json',trial)
        store.atomic(temporary/'pending.json',pending)
        for path,digest in checks.items():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Source study data changed during merging. Try again.')
        temporary.rename(store.folder(identity))
    finally:
        if temporary.exists():shutil.rmtree(temporary)
    return identity,summary,pending
