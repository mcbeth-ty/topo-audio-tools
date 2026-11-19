export default function({parentElement,data,setTriggerValue}){
  const shell=parentElement.querySelector('.atlas-demo-root'),shared=controller();shared.context(data.epoch);
  const emit=event=>setTriggerValue('event',{...event,event_id:crypto.randomUUID()});
  let state=shell.__demo;
  if(!state){
    state={data,urls:new Map(),index:0,step:'intro',done:false,tags:[true,false,true],manual:[false,false,false],popup:null,viewed:false,disposed:false};shell.__demo=state;
    state.cleanup=[];shell.classList.add(`atlas-section-${data.section}`);
    state.popup=atlasPopup(shell);
    const error=document.createElement('div');error.className='atlas-error';error.setAttribute('role','status');shell.append(error);state.error=error;
    const common=()=>({public_demo:true,playback_context:state.data.epoch,audio_seconds:15,category_descriptions:{},thresholds:[.10,.23,.40],show_reference_cube:false});
    const items=ids=>ids.map((id,i)=>({id,number:i+1,label:'',notes:'',url:state.urls.get(`${state.data.section==='atlas'?state.index:0}:${id}`)||null}));
    const request=()=>{const r=state.data.response;return r&&r.key===`${state.data.section==='atlas'?state.index:0}:${r.id}`?{id:r.id,token:r.request}:null;};
    const demoEvent=(type,event)=>{
      if(type!=='event')return;
      if(event.kind==='play'){emit({kind:'play',id:event.id,model:state.index});return;}
      if(state.data.section==='atlas'&&event.kind==='explore_settings'&&typeof event.show_tags==='boolean'){
        state.tags[state.index]=event.show_tags;state.manual[state.index]=true;return;
      }
      if(state.data.section==='arrange'&&event.kind==='submit'){
        shared.stop();state.popup.show('Thank you','Your example arrangement is complete. No judgments were recorded.',[['Try another',()=>{state.popup.hide();emit({kind:'next'});}]],()=>{});
      }
    };
    state.showStep=()=>{
      const stop=()=>{clearTimeout(state.tagPause);state.done=true;state.step='done';state.popup.hide();shell.classList.remove('atlas-path-highlight');for(let i=0;i<3;i++)if(!state.manual[i])state.tags[i]=true;};
      state.complete=()=>{stop();state.render();};
      if(state.done)return;
      if(state.step==='intro')state.popup.show('',ATLAS_TEXT.intro,[],()=>{stop();state.render();});
      if(state.step==='tags')state.popup.show('Understanding tags',ATLAS_TEXT.tags,[['Reveal Tags',()=>{
        state.tags[1]=true;state.step='tagsPause';state.popup.hide();state.render();
        clearTimeout(state.tagPause);
        state.tagPause=setTimeout(()=>{
          if(state.disposed||state.done||state.index!==1||state.step!=='tagsPause')return;
          state.step='path';state.showStep();
        },3000);
      }],['Continue',()=>{state.step='path';state.showStep();}]],()=>{stop();state.render();});
      if(state.step==='path'){state.seedPath();shell.classList.remove('atlas-path-highlight');state.popup.show('Finding paths between sounds',ATLAS_TEXT.path,[],()=>{stop();state.render();});}
      if(state.step==='usePath'){shell.classList.remove('atlas-path-highlight');state.popup.show('Create a path',ATLAS_TEXT.usePath,[],()=>{stop();state.render();});}
    };
    if(data.section==='atlas'){
      state.cleanup.push(atlasHostedFrame());
      state.cleanup.push(atlasSectionNav());
      const previous=document.createElement('button'),next=document.createElement('button');previous.className='atlas-model-previous';next.className='atlas-model-next';previous.textContent='‹';next.innerHTML='<span>Next model / pathfinding</span><span aria-hidden="true">›</span>';previous.setAttribute('aria-label','Previous model');next.setAttribute('aria-label','Next model / pathfinding');previous.title='Previous model';next.title='Next model / pathfinding';shell.append(previous,next);
      const move=direction=>{const to=Math.max(0,Math.min(2,state.index+direction));if(to===state.index)return;shared.stop();state.index=to;if(!state.done&&to===1&&state.step==='intro'){state.step='tags';}else if(!state.done&&to!==1&&state.step!=='intro'){state.complete();}state.render();if(!state.done)state.showStep();};
      previous.onclick=()=>move(-1);next.onclick=()=>{clearTimeout(state.nextModelCue);next.classList.remove('atlas-next-cue');move(1);};
      state.nextModelCue=setTimeout(()=>{if(!state.disposed&&state.index===0)next.classList.add('atlas-next-cue');},20000);
      state.cleanup.push(()=>clearTimeout(state.nextModelCue));
      state.previous=previous;state.next=next;
      state.seedPath=()=>{
        if(state.pathSeeded)return;
        const root=shell.querySelector('.study-root'),viewer=root?.__study;
        const tags=state.data.models[state.index].tags;
        const find=label=>Object.keys(tags).find(id=>tags[id].trim().toLowerCase()===label);
        const start=find('anxiety'),end=find('airy and beautiful');
        if(!viewer?.pathfinder||!start||!end)return;
        state.seedingPath=true;
        try{
          const launcher=root.querySelector('.study-pathfinder-launch');
          if(launcher.getAttribute('aria-expanded')!=='true')launcher.click();
          root.querySelector('[aria-label="Choose start node"]').click();viewer.pathfinder.pick(start);
          root.querySelector('[aria-label="Choose destination node"]').click();viewer.pathfinder.pick(end);
          root.querySelector('.study-pathfinder-calculate').click();
          state.pathSeeded=viewer.pathfinder.routes.length>0;
        }finally{state.seedingPath=false;}
      };
      const click=event=>{
        if(state.done||state.seedingPath)return;
        if(event.target.closest('.study-pathfinder-picks button')&&state.step==='path'){
          state.step='usePath';state.showStep();
        }else if(event.target.closest('.study-pathfinder-calculate')&&state.step==='usePath'&&shell.querySelector('.study-root').__study?.pathfinder.routes.length){state.complete();}
      };shell.addEventListener('click',click);state.cleanup.push(()=>shell.removeEventListener('click',click));
      state.render=()=>{
        const model=state.data.models[state.index];
        const payload={...common(),...model,kind:'explore',context:`atlas-public-model-${state.index}`,n_components:4,model:'Ordinal',
          positions:Object.fromEntries(model.ids.map(id=>[id,{x:.5,y:.5}])),show_tags:state.tags[state.index],connection_level:'All',
          items:items(model.ids),play_request:request()};
        shell.querySelectorAll('.atlas-floating-scale').forEach(el=>el.remove());
        renderAtlasStudy({parentElement:shell,data:payload,setTriggerValue:demoEvent});
        const root=shell.querySelector('.study-root'),svg=root.querySelector('svg');
        const scale=root.querySelector('.study-fourth-scale');if(scale){scale.classList.add('atlas-floating-scale');for(const label of scale.querySelectorAll('span:not(.study-fourth-gradient)'))label.hidden=true;root.append(scale);}
        state.previous.disabled=state.index===0;
        const nextLabel=state.index===0?'Next model / pathfinding':'Next model';
        state.next.querySelector('span').textContent=nextLabel;
        state.next.setAttribute('aria-label',nextLabel);state.next.title=nextLabel;
        state.next.hidden=state.index===2;state.next.disabled=state.index===2;
        const position=()=>{
          const box=svg.getBoundingClientRect(),parent=shell.getBoundingClientRect();
          state.popup.element.style.top=`${box.top-parent.top+40}px`;state.previous.style.top=state.next.style.top=`${box.top-parent.top+box.height/2}px`;
          const arrow=shell.querySelector('.atlas-section-arrow');
          if(arrow)arrow.style.top=`${box.bottom-parent.top-22}px`;
        };position();
        if(state.viewport!==svg){state.viewportObserver?.disconnect();state.viewport=svg;state.viewportObserver=new ResizeObserver(position);state.viewportObserver.observe(svg);}
        if(!state.viewed){state.viewed=true;requestAnimationFrame(()=>state.showStep());}
      };
    }else if(data.section==='arrange'){
      state.render=()=>{
        const ids=state.data.ids,corners=[{x:.12,y:.12},{x:.88,y:.12},{x:.12,y:.88},{x:.88,y:.88}];
        const positions=Object.fromEntries(ids.map((id,i)=>[id,corners[i]]));
        renderAtlasStudy({parentElement:shell,data:{...common(),kind:'trial',context:`atlas-public-arrange-${state.data.round}`,ids,
          positions,pending:{trial_id:state.data.round,sequence:1,revision:0,interactions:Object.fromEntries(ids.map(id=>[id,{moved:false,auditioned:false,considered:false}]))},feedback:true,
          items:items(ids),play_request:request()},setTriggerValue:demoEvent});
        if(!state.observing){state.observing=true;state.cleanup.push(atlasOnceVisible(shell.querySelector('svg'),()=>state.popup.show('Understanding musical relationships',ATLAS_TEXT.arrange,[['Start Exploring',()=>state.popup.hide()]])));}
      };
    }else{
      const root=shell.querySelector('.study-root');root.remove();
      const layout=document.createElement('div');layout.className='atlas-generator-layout';const form=document.createElement('form'),gallery=document.createElement('div');form.className='atlas-generator-controls';gallery.className='atlas-gallery';layout.append(form,gallery);shell.prepend(layout);
      const fields={};
      const select=(key,label,options,value)=>{const wrap=document.createElement('label');wrap.textContent=label;const el=document.createElement('select');for(const [v,text] of options.map(o=>Array.isArray(o)?o:[o,o])){const opt=document.createElement('option');opt.value=v;opt.textContent=text;el.append(opt);}el.value=value;fields[key]=el;wrap.append(el);form.append(wrap);return wrap;};
      select('framework','Harmonic targeting',[['chromatic','Chromatic'],['chord_targeting','Chord targeting']],'chromatic');
      const register=document.createElement('label');register.className='atlas-register';
      const readout=document.createElement('output'),track=document.createElement('div');track.className='atlas-register-range';register.append(readout,track);form.append(register);
      for(const [key,value,label] of [['low',48,'Lowest MIDI note'],['high',72,'Highest MIDI note']]){
        const input=document.createElement('input');input.type='range';input.min=24;input.max=96;input.step=1;input.value=value;input.setAttribute('aria-label',label);fields[key]=input;track.append(input);
        input.oninput=()=>{if(Number(fields.low.value)>Number(fields.high.value))input.value=key==='low'?fields.high.value:fields.low.value;updateRegister();};
      }
      function updateRegister(){readout.textContent=`Register · ${fields.low.value} – ${fields.high.value}`;track.classList.toggle('equal-values',fields.low.value===fields.high.value);}
      updateRegister();
      const vocabulary=document.createElement('small');vocabulary.className='atlas-vocabulary';vocabulary.textContent='Expanded harmonic vocabulary';form.prepend(vocabulary);
      const range=document.createElement('div');range.className='atlas-voice-range';form.append(range);
      for(const [key,label,value] of [['minimum','Min voices',3],['maximum','Max voices',4]]){const wrap=select(key,label,[2,3,4,5],value);range.append(wrap);}
      select('family','Harmonic family',data.families,'All');
      const relationship=select('relationship','Relationship',data.relationships,'Mixed'),quality=select('quality','Quality balance',data.qualities,'Balanced');
      const updateMode=()=>{relationship.hidden=quality.hidden=fields.framework.value!=='chord_targeting';};fields.framework.onchange=updateMode;updateMode();
      select('voices','Maximum voices moved',[1,2,3,4,5],3);select('movement','Maximum movement (semitones)',Array.from({length:16},(_,i)=>i+1),7);
      const holdLabel=document.createElement('label'),hold=document.createElement('input');hold.type='checkbox';holdLabel.className='atlas-hold';holdLabel.append(hold,document.createTextNode('Hold bass note'));form.append(holdLabel);
      const generate=document.createElement('button');generate.type='submit';generate.textContent='Generate four sounds';form.append(generate);
      const run=()=>{
        if(Number(fields.minimum.value)>Number(fields.maximum.value)){fields.maximum.value=fields.minimum.value;}
        shared.stop();generate.disabled=true;generate.textContent='Generating…';
        emit({kind:'generate',settings:{...Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value])),hold:hold.checked}});
      };
      form.onsubmit=event=>{event.preventDefault();state.popup.hide();run();};
      state.render=()=>{
        generate.disabled=false;generate.textContent='Generate four sounds';
        const cards=state.data.cards;for(const dispose of state.playerCleanups||[])dispose?.();state.playerCleanups=[];gallery.replaceChildren();
        for(let i=0;i<4;i++){
          const card=document.createElement('div');card.className='atlas-audio-card';const label=document.createElement('div');label.textContent=`Sound ${i+1}`;card.append(label);
          if(cards[i]){const host=document.createElement('div');host.innerHTML='<div class="ambient-root"></div>';card.append(host);state.playerCleanups.push(renderAtlasPlayer({parentElement:host,data:{kind:'player',id:cards[i].id,url:cards[i].url,epoch:state.data.epoch,compact:false},setTriggerValue:()=>{}}));}
          else{const empty=document.createElement('div');empty.className='atlas-card-placeholder';empty.textContent='Generate a group to listen';card.append(empty);}
          if(cards[i]?.metadata){
            const m=cards[i].metadata,meta=document.createElement('div');meta.className='atlas-card-meta';
            const summary=document.createElement('div');summary.textContent=[`${m.duration||15}s`,m.timbre||'Warm Pad',Number.isFinite(m.voices)?`${m.voices} voices`:null,Number.isFinite(m.states)?`${m.states} ${m.states===1?'state':'states'}`:null].filter(Boolean).join(' · ');
            const harmony=document.createElement('div');harmony.textContent=[m.harmony,m.notes].filter(Boolean).join(' · ');meta.append(summary,harmony);card.append(meta);
          }
          gallery.append(card);
        }
        if(!state.observing){state.observing=true;state.cleanup.push(atlasOnceVisible(layout,()=>state.popup.show('Generating new harmonic experiences',ATLAS_TEXT.generator,[['Start Generating',()=>{state.popup.hide();if(!state.data.cards.length)run();}]])));}
      };
    }
    if(data.section!=='generator'){
      const destination=data.section==='atlas'?'Arrange':'Ambient Generator';
      const arrow=document.createElement('button');arrow.className='atlas-section-arrow';arrow.innerHTML=`<span>${destination}</span><span aria-hidden="true">↓</span>`;
      arrow.setAttribute('aria-label',`Scroll to ${destination}`);
      arrow.onclick=()=>{
        const heading=[...document.querySelectorAll('h2')].find(e=>e.textContent.trim()===destination);
        heading?.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});
      };shell.append(arrow);
    }
    state.dispose=()=>{if(state.disposed)return;state.disposed=true;clearTimeout(state.tagPause);state.popup.dispose();state.viewportObserver?.disconnect();for(const f of state.cleanup)f();for(const f of state.playerCleanups||[])f?.();shell.querySelector('.study-root')?.__study?.dispose();delete shell.__demo;};
  }
  state.data=data;
  if(data.audio_urls)state.urls=new Map(Object.entries(data.audio_urls));
  if(data.response)state.urls.set(data.response.key,data.response.url);
  state.error.textContent=data.error||'';state.render();
  // Retain state across data updates; dispose only after actual DOM removal.
  return ()=>{queueMicrotask(()=>{if(!shell.isConnected)state.dispose();});};
}
