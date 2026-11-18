"""Read-only public Affective Atlas: snapshots in, session-local demos out."""
import base64
import copy
import json
import os
import random
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import streamlit as st
from streamlit.components.v2 import component
from ambient_study_color import extend_color
from ambient_preview import preview_audio
from ambient_soundfont import soundfont_identity,render_soundfont_wav
from atlas_assets import demo_soundfont

ROOT=Path(__file__).parent
MODEL_NAMES=('model 1','model 4','model 2')
PUBLIC_EPOCH='affective-atlas-public-15s'


@st.cache_data(max_entries=6,show_spinner=False)
def _read_model(path,size,modified):
    record=json.loads(Path(path).read_text())
    fit=record['fits'].get('Ordinal:3D+color')
    if fit is None:fit=extend_color({**record['fits']['Ordinal:3'],'summary':record['summary']},'Ordinal')
    if 'coordinates' not in fit['embedding']:raise ValueError('A public model needs its frozen 3D coordinates.')
    ids=[item['stimulus_id'] for item in record['manifest']['inventory']]
    alias={identity:f'n{i+1}' for i,identity in enumerate(ids)}
    recipes={alias[item['stimulus_id']]:item['metadata'] for item in record['manifest']['inventory']}
    pairs={}
    for pair in record['summary']['pairs'].values():
        a,b=[alias[i] for i in pair['ids']]
        pairs['|'.join(sorted((a,b))) ]={**{k:pair[k] for k in ('valid_count','relatedness','counts','uncertain_count','disagreement')},'ids':[a,b]}
    public={'ids':list(alias.values()),'world_positions':{alias[i]:fit['embedding']['coordinates'][i] for i in ids},
            'tags':{alias[i]:text for i,text in record.get('tags',{}).items() if i in alias},'pairs':pairs}
    return public,recipes


def load_demo_models():
    directory=Path(os.getenv('AFFECTIVE_ATLAS_MODELS_DIR',str(ROOT/'public_data'/'models'))).expanduser()
    found={}
    for path in directory.glob('*.json'):
        record=json.loads(path.read_text());name=record.get('name','').strip().lower()
        if name in MODEL_NAMES:found[name]=path
    if set(found)!=set(MODEL_NAMES):raise ValueError('The demo requires saved JSON models named model 1, model 4, and model 2.')
    loaded=[]
    for name in MODEL_NAMES:
        path=found[name];stat=path.stat();loaded.append(_read_model(str(path),stat.st_size,stat.st_mtime_ns))
    return loaded


@st.cache_data(max_entries=8,show_spinner=False)
def _inline_audio(wav):
    # Cloud wraps the app under /~/+/. Raw media-manager URLs bypass its
    # routing and can return HTML instead of WAVs. Keep on-demand audio in
    # memory and independent of proxy paths, including cross-origin embeds.
    return 'data:audio/wav;base64,'+base64.b64encode(wav).decode('ascii')


def audio_url(wav, identity):
    return _inline_audio(wav)


def recipe_audio(metadata):
    recipe=copy.deepcopy(metadata)
    if recipe['rendering']['backend']=='SoundFont':
        identity=demo_soundfont()
        if identity[1]!=recipe['rendering']['soundfont']['sha256']:raise ValueError('The configured SoundFont does not match the sample library.')
        recipe['rendering']['soundfont']['path']=identity[0]
    return preview_audio(recipe,15)


@st.cache_data(max_entries=8,show_spinner=False)
def warm_audio(states,font):
    return render_soundfont_wav(states,15,font,89,'Room',.60)


def generate_demo(settings):
    from ambient_app import generate_batch
    from ambient_expanded import FAMILIES
    from ambient_chord_targeting import RELATIONSHIPS,QUALITY_BALANCES
    if not isinstance(settings,dict):raise ValueError('Invalid generator controls.')
    framework=settings.get('framework','chromatic')
    if framework not in ('chromatic','chord_targeting'):raise ValueError('Invalid framework.')
    minimum,maximum=int(settings.get('minimum',3)),int(settings.get('maximum',4))
    movement=int(settings.get('movement',7));voices=int(settings.get('voices',3))
    if not 2<=minimum<=maximum<=5 or not 1<=movement<=16 or not 1<=voices<=5:raise ValueError('Check the voice controls.')
    family=settings.get('family','All');relationship=settings.get('relationship','Mixed');quality=settings.get('quality','Balanced')
    if family not in FAMILIES or relationship not in RELATIONSHIPS or quality not in QUALITY_BALANCES:raise ValueError('Invalid harmonic controls.')
    low,high=int(settings.get('low',48)),int(settings.get('high',72))
    if not 24<=low<=high<=96:raise ValueError('Invalid register.')
    weights=(25,100,100)
    font=demo_soundfont()
    batch=generate_batch(4,None,None,low,high,3,voices,movement,'Expanded',(minimum,maximum),family,
        hold_bass_note=bool(settings.get('hold',False)),generation_framework=framework,state_weights=weights,
        harmonic_relationship=relationship,chord_quality_balance=quality)
    return [(item,warm_audio(tuple(tuple(s['notes_midi']) for s in item['states']),font)) for item in batch]


@lru_cache(maxsize=8)
def _component(js,css):
    import hashlib
    return component('affective_atlas_public_'+hashlib.sha256((js+css).encode()).hexdigest()[:16],
        html='<div class="atlas-demo-root"><div class="study-root"></div></div>',js=js,css=css)


def demo_component():
    assets=ROOT/'ambient_frontend';demo=ROOT/'atlas_demo_frontend'
    controller=(assets/'audition.js').read_text().split('export default function',1)[0]
    study=(assets/'study.js').read_text().replace('export default function','function renderAtlasStudy',1)
    player=(assets/'audition.js').read_text().split('export default function',1)[1]
    js=controller+(assets/'study_pathfinder.js').read_text()+study+'\nfunction renderAtlasPlayer'+player+(demo/'popup.js').read_text()+(demo/'demo.js').read_text()
    return _component(js,(assets/'study.css').read_text()+(assets/'audition.css').read_text()+(demo/'demo.css').read_text())


def _audio_response(section,key,identity,metadata):
    cache=st.session_state.setdefault('atlas_demo_audio',{})
    if key not in cache:cache[key]=recipe_audio(metadata)
    while len(cache)>8:cache.pop(next(iter(cache)))
    return {'key':key,'url':audio_url(cache[key],f'atlas-demo-{key}'),'request':uuid4().hex,'id':identity,'section':section}




@st.fragment
def atlas_section(loaded):
    def event():
        message=st.session_state.get('atlas_demo_atlas',{}).get('event',{})
        if message.get('kind')!='play':return
        try:
            model=message['model'];identity=message['id']
            if type(model) is not int or not 0<=model<3 or identity not in loaded[model][1]:raise ValueError('Invalid sound.')
            st.session_state['atlas_demo_atlas_response']=_audio_response('atlas',f'{model}:{identity}',identity,loaded[model][1][identity])
        except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError):st.session_state['atlas_demo_atlas_error']='This sound is temporarily unavailable.'
    demo_component()(key='atlas_demo_atlas',data={'section':'atlas','models':[item[0] for item in loaded],
        'response':st.session_state.get('atlas_demo_atlas_response'),'error':st.session_state.pop('atlas_demo_atlas_error',None),
        'epoch':PUBLIC_EPOCH},height='content',on_event_change=event)


@st.fragment
def arrange_section(model):
    if 'atlas_demo_arrange_group' not in st.session_state:
        st.session_state['atlas_demo_arrange_group']=random.sample(model[0]['ids'],4)
        st.session_state['atlas_demo_arrange_round']=uuid4().hex
    group=st.session_state['atlas_demo_arrange_group']
    def event():
        message=st.session_state.get('atlas_demo_arrange',{}).get('event',{})
        if message.get('kind')=='next':
            st.session_state['atlas_demo_arrange_group']=random.sample(model[0]['ids'],4)
            st.session_state['atlas_demo_arrange_round']=uuid4().hex
            st.session_state.pop('atlas_demo_arrange_response',None)
        elif message.get('kind')=='play':
            try:
                identity=message['id']
                if identity not in group:raise ValueError('Invalid sample.')
                st.session_state['atlas_demo_arrange_response']=_audio_response('arrange',f'0:{identity}',identity,model[1][identity])
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError):st.session_state['atlas_demo_arrange_error']='This sound is temporarily unavailable.'
    demo_component()(key='atlas_demo_arrange',data={'section':'arrange','ids':group,'round':st.session_state['atlas_demo_arrange_round'],
        'response':st.session_state.get('atlas_demo_arrange_response'),'error':st.session_state.pop('atlas_demo_arrange_error',None),
        'epoch':PUBLIC_EPOCH},height='content',on_event_change=event)


@st.fragment
def generator_section():
    from ambient_expanded import FAMILIES
    from ambient_chord_targeting import RELATIONSHIPS,QUALITY_BALANCES
    def event():
        message=st.session_state.get('atlas_demo_generator',{}).get('event',{})
        if message.get('kind')!='generate':return
        try:
            batch=generate_demo(message.get('settings',{}))
            st.session_state['atlas_demo_generated']=[{'id':item['stimulus_id'],'wav':wav,'metadata':{'harmony':item['chord']['display_label'],
                'notes':', '.join(item['states'][0]['notes_names']),'voices':len(item['states'][0]['notes_midi']),
                'states':len(item['states']),'duration':15,'timbre':'Warm Pad'}} for item,wav in batch]
            st.session_state.pop('atlas_demo_generator_error',None)
        except (OSError,ValueError,KeyError,TypeError,RuntimeError,ImportError):
            st.session_state['atlas_demo_generator_error']='Generation is unavailable. Check the local SoundFont setup, then try again.'
    demo_component()(key='atlas_demo_generator',data={'section':'generator','cards':[{'id':card['id'],'url':audio_url(card['wav'],f"atlas-demo-generated-{card['id']}"),'metadata':card.get('metadata',{})} for card in st.session_state.get('atlas_demo_generated',[])],
        'families':list(FAMILIES),'relationships':list(RELATIONSHIPS),'qualities':list(QUALITY_BALANCES),
        'error':st.session_state.get('atlas_demo_generator_error'),'epoch':PUBLIC_EPOCH},height='content',on_event_change=event)


def main():
    st.set_page_config(page_title='Affective Atlas',layout='wide',initial_sidebar_state='collapsed')
    st.markdown('''<style>
    [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],header[data-testid="stHeader"],#MainMenu,footer {display:none!important}
    .stApp {background:#0a0a0a;color:#ddd} .block-container {max-width:1500px!important;padding:clamp(16px,3vw,48px)!important}
    [data-testid="stMainBlockContainer"] {padding-top:28px!important}
    html,body,.stApp,h1,h2,p {font-family:Arial,Helvetica,sans-serif} h1 {font-size:clamp(28px,4vw,44px)!important} h2 {margin-top:12px!important}
    .st-key-atlas_demo_intro {max-width:700px} .st-key-atlas_demo_intro p {font-size:12px;line-height:1.45;margin-bottom:6px}
    .st-key-atlas_demo_intro [data-testid="stVerticalBlock"] {gap:6px}
    </style>''',unsafe_allow_html=True)
    st.title('Affective Atlas')
    with st.container(key='atlas_demo_intro'):
        st.write('Affective Atlas is an experimental environment for exploring the relationships between sounds and the emotions they evoke.')
        st.write('By translating listening judgments into interactive spatial models, it allows us to navigate musical experiences through their perceived relationships rather than conventional musical categories.')
        st.write('Explore the resulting sound landscapes, discover gradual transitions between different experiences, and investigate how musical relationships might be understood, organized, and eventually generated.')
    try:loaded=load_demo_models()
    except (OSError,ValueError,KeyError,TypeError) as error:
        st.error(str(error));st.stop()
    atlas_section(loaded)
    st.header('Arrange')
    arrange_section(loaded[0])
    st.header('Ambient Generator')
    generator_section()
