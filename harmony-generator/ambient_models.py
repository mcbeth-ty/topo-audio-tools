"""Named, immutable JSON snapshots of Ambient study fits; no audio persistence."""
import copy
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import streamlit as st
import ambient_study_store as store
import ambient_study_analysis as analysis

MODEL_DIR=Path(__file__).parent/'data'/'ambient_models'
SCHEMA='hsg-ambient-model-v1'


def model_path(identity):
    return MODEL_DIR/f'{UUID(identity).hex}.json'


def load_model(identity):
    record=store.read(model_path(identity))
    if record.get('schema_version')!=SCHEMA or record.get('model_id')!=UUID(identity).hex:
        raise ValueError('Unsupported saved model.')
    if not record.get('manifest',{}).get('inventory') or not isinstance(record.get('fits'),dict):
        raise ValueError('Incomplete saved model.')
    return record


def list_models():
    records,errors=[],[]
    if MODEL_DIR.exists():
        for path in MODEL_DIR.glob('*.json'):
            try:
                record=load_model(path.stem)
                records.append({key:record[key] for key in ('model_id','name','saved_at')})
            except (OSError,ValueError,KeyError,TypeError) as error:errors.append(f'{path.name}: {error}')
    return sorted(records,key=lambda r:(r['saved_at'],r['model_id']),reverse=True),errors


def save_model(session_id,name):
    name=name.strip()
    if not name or len(name)>100:raise ValueError('Enter a model name (up to 100 characters).')
    manifest,state=store.load_session(session_id)
    if manifest['feedback_policy']!='Exploratory' and not state.get('revealed_at'):
        raise ValueError('Reveal study feedback before saving a model.')
    trials,errors=store.trials(session_id)
    if errors:raise ValueError('Repair unreadable trial files before saving a model.')
    summary=store.summarize(manifest,trials)
    ids=[item['stimulus_id'] for item in manifest['inventory']]
    reasons,_=analysis.sufficiency(ids,summary['pairs'],analysis.effective_settings(manifest['settings']['analysis']),3)
    if reasons:raise ValueError('Not enough evidence for a 3D model: '+'; '.join(reasons))
    fingerprint=lambda rows:hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
    digest=fingerprint(trials)
    fits={}
    for model in ('Ordinal','Affinity'):
        for dimension in (2,3,4):
            result=analysis.analyze(session_id,dimension,model)
            if result['summary']['pairs']!=summary['pairs']:
                raise ValueError('Study observations changed while saving. Please save again.')
            fits[f'{model}:{dimension}']={key:copy.deepcopy(value) for key,value in result.items() if key!='summary'}
    from ambient_study_color import extend_color
    for model in ('Ordinal','Affinity'):
        conditional=extend_color({**fits[f'{model}:3'],'summary':summary},model)
        fits[f'{model}:3D+color']={key:value for key,value in conditional.items() if key!='summary'}
    if not any('coordinates' in fits[f'{model}:3']['embedding'] for model in ('Ordinal','Affinity')):
        raise ValueError('A usable 3D fit could not be produced.')
    latest,errors=store.trials(session_id)
    if errors or fingerprint(latest)!=digest:raise ValueError('Study observations changed while saving. Please save again.')
    _,latest_state=store.load_session(session_id)
    identity=uuid4().hex
    record={'schema_version':SCHEMA,'model_id':identity,'name':name,'saved_at':store.now(),
            'source_session_id':session_id,'source_session_name':state['name'],'observations_sha256':digest,
            'manifest':copy.deepcopy(manifest),'tags':copy.deepcopy(latest_state.get('stimulus_tags',{})),
            'summary':summary,'fits':fits}
    store.atomic(model_path(identity),record)
    return record


def render_models(cached_audio):
    from ambient_study import explore
    st.subheader('Models')
    records,errors=list_models()
    for error in errors:st.warning(f'Unreadable model: {error}')
    if not records:
        st.info('Save a named model from Relational Study → Explore once a 3D fit is available.')
        return
    ids=[r['model_id'] for r in records];labels={r['model_id']:r['name'] for r in records}
    key='ambient_models_selected'
    if st.session_state.get(key) not in ids:st.session_state[key]=ids[0]
    def step(direction):
        st.session_state[key]=ids[(ids.index(st.session_state[key])+direction)%len(ids)]
    with st.sidebar:
        st.subheader('SAVED MODEL')
        identity=st.selectbox('Model',ids,format_func=labels.get,key=key)
        left,right=st.columns(2)
        with left:st.button('← Previous',key='ambient_models_previous',on_click=step,args=(-1,),disabled=len(ids)<2)
        with right:st.button('Next →',key='ambient_models_next',on_click=step,args=(1,),disabled=len(ids)<2)
    try:
        frozen=load_model(identity)
        st.markdown(f"**{frozen['name']}**")
        st.caption(f"Frozen {frozen['saved_at'][:19].replace('T',' ')} UTC · {frozen['source_session_name']} · data only; no live refitting")
        explore(identity,frozen['manifest'],{'name':frozen['name']},cached_audio,frozen=frozen)
    except (OSError,ValueError,KeyError,TypeError) as error:st.error(f'Saved model: {error}')
