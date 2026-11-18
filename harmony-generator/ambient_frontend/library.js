// controller() is loaded verbatim from the existing Ambient playback module.
export default function({parentElement,data,setTriggerValue}) {
  const root=parentElement.querySelector('.library-root'),shared=controller();
  shared.context(data.epoch);
  root.classList.toggle('selection-mode',Boolean(data.read_only));
  root.classList.toggle('lock-mode',Boolean(data.can_lock));
  if(!shared.playRequests)shared.playRequests=new Set();
  if(!root.__library){
    const state={rows:new Map(),audio:null,audioId:null,url:null,unregister:null,data};
    root.__library=state;
    state.clearAudio=()=>{
      if(state.unregister)state.unregister();
      state.audio=null;state.audioId=null;state.url=null;state.unregister=null;
    };
    state.paint=()=>{
      for(const [id,row] of state.rows){
        const playing=id===state.audioId&&state.audio&&!state.audio.paused;
        row.node.classList.toggle('playing',Boolean(playing));
        const error=state.data.audio_error?.id===id?state.data.audio_error.message:null;
        const restart=Boolean(state.data.can_lock);
        row.play.textContent=error?'!':playing&&!restart?'Ⅱ':'▶';
        row.play.title=error||(restart?'Play from beginning':playing?'Pause stimulus':'Audition stimulus');
        row.play.setAttribute('aria-label',`${restart?'Restart':playing?'Pause':'Play'} stimulus ${id.slice(0,8)}`);
      }
    };
    state.dispose=()=>{state.clearAudio();if(root.__library===state)delete root.__library;};
  }
  const state=root.__library;state.data=data;
  const emit=(kind,id,value)=>setTriggerValue('event',{kind,id,value,event_id:crypto.randomUUID()});
  const button=(text,label,cls)=>{const e=document.createElement('button');e.type='button';e.textContent=text;e.className=cls;e.title=label;e.setAttribute('aria-label',label);return e;};
  const ids=new Set(data.rows.map(row=>row.id));
  for(const [id,row] of state.rows)if(!ids.has(id)){row.node.remove();state.rows.delete(id);}
  for(const [index,item] of data.rows.entries()){
    let row=state.rows.get(item.id);
    if(!row){
      const node=document.createElement('div');node.className='library-row';node.dataset.id=item.id;
      const lock=button('🔓','Lock stimulus in set','library-lock');
      const play=button('▶','Audition stimulus','library-play'),open=button(item.id.slice(0,8),'Open stimulus details','library-id');
      const summary=document.createElement('span');summary.className='library-summary';
      const studies=document.createElement('span');studies.className='library-studies';
      const favoriteStatus=document.createElement('span');favoriteStatus.className='library-favorite-status';
      const tagDisplay=document.createElement('textarea');tagDisplay.className='library-selection-tag';
      tagDisplay.maxLength=64;tagDisplay.rows=1;tagDisplay.placeholder='Add tag…';tagDisplay.setAttribute('aria-label','Stimulus tag (64 characters maximum)');
      tagDisplay.oninput=()=>{tagDisplay.style.height='auto';tagDisplay.style.height=tagDisplay.scrollHeight+'px';tagDisplay.title=tagDisplay.value;};
      tagDisplay.onchange=()=>{if(state.data.can_edit_tags)setTriggerValue('tag',{id:item.id,value:tagDisplay.value,event_id:crypto.randomUUID()});};
      tagDisplay.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();tagDisplay.blur();}};
      const tag=document.createElement('input');tag.className='library-tag';tag.type='text';tag.maxLength=64;tag.placeholder='Add tag…';tag.setAttribute('aria-label','Stimulus tag (64 characters maximum)');
      tag.oninput=()=>{tag.title=tag.value||'Add tag · 64 characters';};
      tag.onchange=()=>{if(!state.data.read_only)setTriggerValue('tag',{id:item.id,value:tag.value,event_id:crypto.randomUUID()});};
      tag.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();tag.blur();}};
      const actions=document.createElement('div');actions.className='library-actions';
      const save=button('✓','Save',''),bypass=button('⊘','Bypass',''),unsave=button('×','Unsave',''),favorite=button('☆','Mark favorite','favorite');
      save.onclick=()=>emit('status',item.id,'saved');bypass.onclick=()=>emit('status',item.id,'bypassed');unsave.onclick=()=>emit('status',item.id,'unreviewed');
      open.onclick=()=>{if(!state.data.read_only)emit('details',item.id);};
      play.onclick=async()=>{
        if(state.audioId===item.id&&state.audio){
          if(state.data.can_lock)shared.reset(state.audio);
          else if(!state.audio.paused){state.audio.pause();return;}
          shared.activate(state.audio);
          try{await state.audio.play();}catch(_){play.textContent='!';play.title='Playback unavailable; try again.';}
        }else{
          shared.stop();play.textContent='…';emit('play',item.id);
        }
      };
      actions.append(save,bypass,unsave,favorite);node.append(lock,play,open,summary,studies,tag,actions);open.after(favoriteStatus);tag.after(tagDisplay);
      row={node,lock,play,open,summary,studies,tag,save,bypass,unsave,favorite,favoriteStatus,tagDisplay};state.rows.set(item.id,row);
    }
    row.tagDisplay.hidden=!data.can_lock;row.tagDisplay.readOnly=!data.can_edit_tags;
    if(!row.tagDisplay.matches(':focus'))row.tagDisplay.value=item.tag||'';
    row.tagDisplay.title=row.tagDisplay.value||'Add tag · 64 characters';
    row.favoriteStatus.hidden=!data.can_lock;row.favoriteStatus.textContent=item.favorite?'★':'☆';
    row.favoriteStatus.title=item.favorite?'Favorite':'Not a favorite';row.favoriteStatus.setAttribute('aria-label',row.favoriteStatus.title);
    row.lock.hidden=!data.can_lock;row.lock.textContent=item.locked?'🔒':'🔓';
    row.lock.title=item.locked?'Unlock stimulus':'Lock stimulus in set';row.lock.setAttribute('aria-label',row.lock.title);
    row.lock.setAttribute('aria-pressed',String(!!item.locked));row.lock.onclick=()=>emit('lock',item.id,!item.locked);
    row.open.disabled=Boolean(data.read_only);row.tag.readOnly=Boolean(data.read_only);row.open.title=item.id;row.open.setAttribute('aria-label',`Open details for ${item.id.slice(0,8)}`);row.summary.textContent=item.summary;row.summary.title=item.summary;
    row.studies.textContent=`${item.studies} ${item.studies===1?'study':'studies'} · ${item.trials} trials`;row.studies.title=item.study_names;
    if(!row.tag.matches(':focus'))row.tag.value=item.tag;
    row.tag.title=row.tag.value||'Add tag · 64 characters';
    row.save.disabled=item.status==='saved';row.bypass.disabled=item.protected||item.status==='bypassed';row.unsave.disabled=item.protected||item.status==='unreviewed';
    row.bypass.title=item.protected?'Study member: protected':'Bypass';row.unsave.title=item.protected?'Study member: protected':'Unsave';
    row.favorite.textContent=item.favorite?'★':'☆';row.favorite.title=item.favorite?'Remove favorite':'Mark favorite';row.favorite.setAttribute('aria-label',row.favorite.title);
    row.favorite.onclick=()=>emit('favorite',item.id,!item.favorite);
    if(root.children[index]!==row.node)root.insertBefore(row.node,root.children[index]||null);
    if(data.can_lock){row.tagDisplay.style.height='auto';row.tagDisplay.style.height=row.tagDisplay.scrollHeight+'px';}
  }
  if(data.can_preview){
    if(!state.footer){
      const footer=document.createElement('div');footer.className='library-selection-footer';
      const label=document.createElement('label'),toggle=document.createElement('input');toggle.type='checkbox';toggle.setAttribute('role','switch');toggle.setAttribute('aria-label','5-second preview');
      toggle.onchange=()=>{shared.stop();toggle.disabled=true;emit('preview',null,toggle.checked);};
      label.append(toggle,document.createTextNode('5s preview'));footer.append(label);state.footer=footer;state.previewToggle=toggle;
    }
    state.previewToggle.checked=!!data.preview;state.previewToggle.disabled=false;root.append(state.footer);
  }else if(state.footer){state.footer.remove();state.footer=null;}
  const active=data.audio;
  if(!active||!ids.has(active.id))state.clearAudio();
  else{
    if(state.audioId!==active.id||state.url!==active.url){
      state.clearAudio();const audio=document.createElement('audio');audio.preload='none';audio.src=active.url;
      state.audio=audio;state.audioId=active.id;state.url=active.url;state.unregister=shared.register(audio);
      audio.onplay=state.paint;audio.onpause=state.paint;audio.onended=state.paint;
    }
    if(active.request&&!shared.playRequests.has(active.request)){
      shared.playRequests.add(active.request);shared.activate(state.audio);
      state.audio.play().catch(()=>{const row=state.rows.get(active.id);if(row){row.play.title='Click to start playback';state.paint();}});
    }
  }
  state.paint();
  return ()=>state.dispose();
}
