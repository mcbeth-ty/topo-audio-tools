// The shared controller() prefix is loaded verbatim from audition.js by Python.
export default function ({parentElement,data,setTriggerValue}) {
  const shared=controller(); shared.context(data.playback_context||data.context);
  const root=parentElement.querySelector('.study-root');
  if(root.__study && root.__study.context!==data.context) root.__study.dispose();
  if(!root.__study) {
    root.replaceChildren();
    const cameras=window.__hsgAmbientStudyCameras||(window.__hsgAmbientStudyCameras=new Map());
    let fittedPan={panX:0,panY:0};
    const defaultCamera=()=>({projection:'perspective-v3',yaw:0,pitch:0,zoom:1,...fittedPan});
    const is3D=data.kind==='explore'&&data.n_components>=3;
    const is4D=is3D&&data.n_components===4;
    const state={camera:structuredClone(cameras.get(data.context)?.projection==='perspective-v3'?cameras.get(data.context):defaultCamera()),cameraSuppressUntil:0,context:data.context,data,revision:data.pending?.revision||0,positions:structuredClone(data.positions),
      overrides:structuredClone(data.pending?.overrides||{}),interactions:structuredClone(data.pending?.interactions||{}),
      confirmed:data.pending?.confirmed||false,audios:new Map(),unregister:[],nodes:new Map(),selected:null,pair:null,drag:null,timer:null,autoPlayed:new Set()};
    root.__study=state;
    let pathfinder=null;
    const svgNS='http://www.w3.org/2000/svg';
    const html=(tag,cls,text)=>{let e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e;};
    const svgEl=(tag,attrs={})=>{let e=document.createElementNS(svgNS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e;};
    const legend=html('div','study-legend');root.append(legend);
    const svg=svgEl('svg',{viewBox:'0 0 1000 600',preserveAspectRatio:'xMidYMid meet',role:'group','aria-label':data.kind==='trial'?'Four-item relational arrangement':'Provisional global relational map'});svg.classList.add('study-svg');
    const edgeGradients=is4D?svgEl('defs'):null,edgeGradientPrefix=is4D?`study-edge-${crypto.randomUUID()}`:null;
    if(edgeGradients)svg.append(edgeGradients);
    const wExtent=is4D?Math.max(0,...Object.values(data.world_positions).map(p=>Math.abs(p[3]))):0;
    const fourthColor=value=>{
      const t=wExtent?Math.max(-1,Math.min(1,value/wExtent)):0;
      const stops=[[205,65,255],[40,65,255],[30,165,255],[45,245,255],[205,215,220],[255,235,65]];
      const position=(t+1)*.5*(stops.length-1),i=Math.min(stops.length-2,Math.floor(position)),blend=position-i;
      return stops[i].map((v,channel)=>Math.round(v+(stops[i+1][channel]-v)*blend));
    };
    const edges=svgEl('g'),tagLeaders=svgEl('g',{'class':'study-tag-leaders','pointer-events':'none'}),nodes=svgEl('g'),scene=is3D?svgEl('g',{'class':'study-scene-3d'}):null;
    if(is3D)svg.append(scene);else svg.append(edges,tagLeaders,nodes);root.append(svg);
    if(data.kind==='trial'&&!data.public_demo){
      const preferenceKey=`hsg-study-tags:${data.context.split(':trial:')[0]}`;
      try{state.showTrialTags=localStorage.getItem(preferenceKey)==='true';}catch(_){state.showTrialTags=false;}
      const bar=html('div','study-tag-toggle-bar'),label=html('label','study-tag-toggle');
      const toggle=html('input');toggle.type='checkbox';toggle.checked=state.showTrialTags;
      toggle.setAttribute('role','switch');toggle.setAttribute('aria-label','Display tags in Arrange');
      toggle.onchange=()=>{state.showTrialTags=toggle.checked;try{localStorage.setItem(preferenceKey,String(toggle.checked));}catch(_){}renderNodes();};
      label.append(toggle,html('span',null,'Tags'));bar.append(label);
      const previewLabel=html('label','study-tag-toggle'),preview=html('input');
      preview.type='checkbox';preview.checked=!!data.fast_preview;
      preview.setAttribute('role','switch');preview.setAttribute('aria-label','5-second preview');
      previewLabel.title='Play the same material in 5 seconds; release/reverb tails may extend playback.';
      preview.onchange=()=>{shared.stop();preview.disabled=true;emit('preview',{enabled:preview.checked,context:state.context});};
      previewLabel.append(preview,html('span',null,'5s preview'));bar.append(previewLabel);root.append(bar);
      state.previewToggle=preview;
    }
    if(is3D){
      const bar=html('div','study-tag-toggle-bar'),tagLabel=html('label','study-tag-toggle'),tags=html('input');
      tags.type='checkbox';tags.checked=!!data.show_tags;
      tags.setAttribute('role','switch');tags.setAttribute('aria-label','Display tags in Explore');
      tags.onchange=()=>{state.data.show_tags=tags.checked;renderNodes();emit('explore_settings',{show_tags:tags.checked,context:state.context});};
      tagLabel.append(tags,html('span',null,'Tags'));bar.append(tagLabel);
      if(!data.public_demo){
      const duration=html('div','study-duration-options');duration.setAttribute('role','group');duration.setAttribute('aria-label','Playback duration');
      state.durationButtons=new Map();
      for(const seconds of [5,15,30]){
        const button=html('button',null,`${seconds}s`);button.type='button';
        button.title=seconds===5?'5-second preview':seconds===15?'Default 15-second playback':'Extended 30-second playback';
        button.setAttribute('aria-pressed',String((data.audio_seconds??15)===seconds));
        button.onclick=()=>{
          if((state.data.audio_seconds??15)===seconds)return;
          shared.stop();for(const b of state.durationButtons.values())b.disabled=true;
          emit('explore_settings',{audio_seconds:seconds,context:state.context});
        };
        state.durationButtons.set(seconds,button);duration.append(button);
      }
        bar.append(duration);
      }
      root.append(bar);state.exploreTagsToggle=tags;
    }
    const info=html('div','study-info',data.kind==='explore'?(is3D?'Click a node to listen; drag to orbit. Select a relationship line to inspect its evidence.':'Click a node to listen and reveal its recorded connections.'):'Click a node to listen. Drag to arrange; select a pair below for an optional judgment.');root.append(info);
    const controls=html('div','study-controls');root.append(controls);
    const save=html('div','study-save');root.append(save);
    const menu=html('div','study-tag-menu');menu.hidden=true;root.append(menu);
    const closeMenu=event=>{if(!menu.contains(event.target))menu.hidden=true;};
    root.addEventListener('pointerdown',closeMenu);
    const tagMenu=(event,id)=>{
      event.preventDefault();event.stopPropagation();menu.replaceChildren();menu.classList.remove('editing');menu.hidden=false;
      const positionMenu=()=>{
        const rect=root.getBoundingClientRect();
        const anchor=state.nodes.get(id).querySelector('.body').getBoundingClientRect();
        const width=menu.offsetWidth,height=menu.offsetHeight;
        const right=anchor.right-rect.left+8;
        const left=right+width<=rect.width?right:anchor.left-rect.left-width-8;
        menu.style.left=`${Math.max(0,Math.min(left,rect.width-width))}px`;
        menu.style.top=`${Math.max(0,Math.min(anchor.top-rect.top+(anchor.height-height)/2,rect.height-height))}px`;
      };
      const current=state.data.tags?.[id]||'';
      const send=text=>{emit('tag',{id,text,context:state.context});menu.hidden=true;};
      const edit=()=>{
        menu.replaceChildren();menu.classList.add('editing');const input=html('input');input.type='text';input.maxLength=64;
        input.value=current;input.placeholder='Short phrase';input.setAttribute('aria-label','Stimulus tag (64 characters maximum)');
        const count=html('small',null,`${Array.from(input.value).length} / 64`);
        input.oninput=()=>{count.textContent=`${Array.from(input.value).length} / 64`;};
        const accept=html('button',null,'Save tag');accept.onclick=()=>send(input.value);
        const cancel=html('button',null,'Cancel');cancel.onclick=()=>{menu.hidden=true;};
        input.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'){e.preventDefault();send(input.value);}if(e.key==='Escape')menu.hidden=true;};
        menu.append(input,count,accept,cancel);positionMenu();input.focus();
      };
      if(current)menu.append(html('div','study-tag-value',current));
      const add=html('button',current?'study-tag-icon':'study-tag-add',current?'✎':'Add tag');add.title=current?'Edit tag':'Add tag';add.setAttribute('aria-label',add.title);add.onclick=edit;menu.append(add);
      if(current){const remove=html('button','study-tag-icon','×');remove.title='Remove tag';remove.setAttribute('aria-label','Remove tag');remove.onclick=()=>send('');menu.append(remove);}
      positionMenu();
    };
    const key=(a,b)=>[a,b].sort().join('|');
    const pairs=[];for(let i=0;i<data.items.length;i++)for(let j=i+1;j<data.items.length;j++)pairs.push([data.items[i].id,data.items[j].id]);
    const index=new Map(data.items.map((item,i)=>[item.id,i+1]));
    let worldCenter=[0,0,0],worldRadius=1,cubeHalf=1;
    if(is3D){
      const values=Object.values(data.world_positions).map(p=>p.slice(0,3));
      worldCenter=[0,1,2].map(axis=>values.reduce((sum,p)=>sum+p[axis],0)/values.length);
      worldRadius=Math.max(1e-9,...values.map(p=>Math.hypot(...p.map((v,k)=>v-worldCenter[k]))));
      cubeHalf=Math.max(...values.flatMap(p=>p.map((v,k)=>Math.abs(v-worldCenter[k])/worldRadius)))+.10;
      svg.classList.add('study-svg-3d');if(is4D)svg.classList.add('study-svg-4d');svg.setAttribute('aria-label',is4D?'Provisional 4D MDS: XYZ spatial position, fourth coordinate shown by node color':'Provisional 3D global relational map');
    }
    // PerspectiveCamera equivalent: vertical FOV 42°, near .05, far 40.
    // Display-only uniform normalization leaves the fitted coordinates untouched.
    const cameraSpec={fov:42,near:.05,far:40,distance:3.7};
    const focal=300/Math.tan(cameraSpec.fov*Math.PI/360);
    const cameraWorld=world=>{
      const c=state.camera;
      const [x,y,z]=world.slice(0,3).map((v,k)=>(v-worldCenter[k])/worldRadius);
      const rx=Math.cos(c.yaw)*x+Math.sin(c.yaw)*z,rz=-Math.sin(c.yaw)*x+Math.cos(c.yaw)*z;
      const ry=Math.cos(c.pitch)*y-Math.sin(c.pitch)*rz,depth=Math.sin(c.pitch)*y+Math.cos(c.pitch)*rz;
      return {x:rx,y:ry,z:cameraSpec.distance/c.zoom-depth};
    };
    if(is3D){
      // Fit the actual point cloud, not the larger reference cube's bounding sphere.
      const remembered=state.camera;state.camera=defaultCamera();
      cameraSpec.distance=0;
      const rotated=Object.values(data.world_positions).map(world=>cameraWorld(world));
      const bounds=distance=>{
        const projected=rotated.map(p=>({x:focal*p.x/(distance+p.z),y:focal*p.y/(distance+p.z)}));
        const xs=projected.map(p=>p.x),ys=projected.map(p=>p.y);
        return {left:Math.min(...xs),right:Math.max(...xs),top:Math.min(...ys),bottom:Math.max(...ys)};
      };
      let low=Math.max(...rotated.map(p=>-p.z))+cameraSpec.near+.02,high=Math.max(4,low+1);
      const fits=b=>b.right-b.left<=900&&b.bottom-b.top<=500;
      while(!fits(bounds(high)))high*=2;
      for(let i=0;i<50;i++){const mid=(low+high)/2;if(fits(bounds(mid)))high=mid;else low=mid;}
      cameraSpec.distance=high;
      const b=bounds(high);fittedPan={panX:-(b.left+b.right)/2,panY:-(b.top+b.bottom)/2};
      state.camera=cameras.get(data.context)?.projection==='perspective-v3'?remembered:defaultCamera();
    }
    const cameraPoint=id=>cameraWorld(state.data.world_positions[id]);
    const project=p=>({x:500+focal*p.x/p.z+state.camera.panX,y:300+focal*p.y/p.z+state.camera.panY,
                       z:p.z,visible:p.z>=cameraSpec.near&&p.z<=cameraSpec.far});
    const point=id=>{
      if(is3D)return project(cameraPoint(id));
      const x=state.positions[id].x*1000,y=state.positions[id].y*600,c=state.camera;
      return data.kind==='explore'?{x:500+(x-500)*c.zoom+c.panX,y:300+(y-300)*c.zoom+c.panY,z:0}:{x,y,z:0};
    };
    const inferred=(a,b)=>{const p=point(a),q=point(b),d=Math.hypot(p.x-q.x,p.y-q.y)/1000,t=state.data.thresholds;return d<=t[0]?3:d<=t[1]?2:d<=t[2]?1:0;};
    const snapshot=()=>({trial_id:state.data.pending?.trial_id,revision:++state.revision,positions:structuredClone(state.positions),overrides:structuredClone(state.overrides),interactions:structuredClone(state.interactions),confirmed:state.confirmed});
    const emit=(kind,extra={})=>{
      clearTimeout(state.timer);state.timer=null;if(state.data.kind==='trial')save.textContent='Saving…';
      setTriggerValue('event',{kind,event_id:crypto.randomUUID(),snapshot:state.data.kind==='trial'?snapshot():null,...extra});
    };
    const ready=()=>state.confirmed||Object.values(state.interactions).length===4&&Object.values(state.interactions).every(flags=>Object.values(flags).some(Boolean));
    let pairSelect=null,overrideSelect=null,confirm=null,submit=null;
    const pairInfo=()=>{
      if(!state.pair)return;
      const [a,b]=state.pair;const k=key(a,b);
      if(state.data.kind==='trial') {
        const override=state.overrides[k];
        info.textContent=`Pair ${index.get(a)}–${index.get(b)}: `+(override==='uncertain'?'Unable to judge (missing evidence)':override!=null?`Manual category ${override} *`:state.data.feedback?`Distance-derived category ${inferred(a,b)}`:'Automatic geometry-based response; hidden feedback');
        if(overrideSelect)overrideSelect.value=override==null?'auto':String(override);
      } else {
        const p=state.data.pairs[k];
        info.textContent=`Pair ${index.get(a)}–${index.get(b)} · ${p.valid_count} valid measurements · distribution [0,1,2,3]: ${p.counts.join(', ')} · ${p.uncertain_count} unable-to-judge · ${p.valid_count?`lower median ${p.relatedness}; disagreement ${p.disagreement.toFixed(2)}`:'Unobserved; no estimated relationship'}`;
      }
    };
    const choosePair=(a,b)=>{state.pair=[a,b];if(pairSelect)pairSelect.value=key(a,b);pairInfo();};
    const lineStyle=category=>category===3?{width:2.4,opacity:.85,dash:''}:category===2?{width:1.2,opacity:.6,dash:''}:category===1?{width:.8,opacity:.4,dash:'4 5'}:{width:.6,opacity:.16,dash:'1 8'};
    const drawEdges=()=>{
      edges.replaceChildren();
      edgeGradients?.replaceChildren();
      if(state.data.kind==='trial'&&!state.data.feedback)return;
      for(const [a,b] of pairs){
        if(state.data.kind==='explore'&&state.selected!==a&&state.selected!==b){
          const pair=state.data.pairs[key(a,b)];
          const threshold=state.data.public_demo&&state.data.connection_level==='All'?0:{Strong:3,Moderate:2,Weak:1}[state.data.connection_level];
          const showConnection=is3D&&threshold!==undefined&&pair?.valid_count>0&&pair.relatedness>=threshold;
          if(!showConnection)continue;
        }
        const k=key(a,b),p=point(a),q=point(b);let style,description,marker='';
        if(state.data.kind==='trial'){
          const override=state.overrides[k];const category=override==null?inferred(a,b):override;
          style=category==='uncertain'?{width:.7,opacity:.25,dash:'2 9'}:lineStyle(category);
          description=category==='uncertain'?'Unable to judge':`Current assigned category ${category}`;
          marker=override==='uncertain'?'?':override!=null?'*':'';
        }else{
          const pair=state.data.pairs[k];const count=pair.valid_count;
          if(state.data.evidence)style=count===0?{width:.5,opacity:.18,dash:'1 9'}:count===1?{width:.8,opacity:.45,dash:'4 5'}:count===2?{width:1.5,opacity:.65,dash:''}:{width:2.8,opacity:.85,dash:''};
          else style=count?lineStyle(pair.relatedness):{width:.5,opacity:.18,dash:'1 9'};
          description=`${count} valid measurements; distribution ${pair.counts.join(', ')}; ${pair.uncertain_count} unable-to-judge; ${count?'median '+pair.relatedness+'; disagreement '+pair.disagreement.toFixed(2):'Unobserved'}`;
        }
        if(is3D){
          if(!p.visible||!q.visible)continue;
          // One screen-space SVG stroke per connection, with no segmented geometry.
          const depth=(p.z+q.z)/2;
          const attrs={x1:p.x,y1:p.y,x2:q.x,y2:q.y,'data-depth':depth};
          const strong=state.data.pairs[k]?.valid_count>0&&state.data.pairs[k].relatedness===3;
          const moderate=state.data.pairs[k]?.valid_count>0&&state.data.pairs[k].relatedness===2;
          const attenuation=Math.max(.28,Math.min(1,3.2/depth));
          const opacity=strong?Math.max(.65,attenuation):moderate?.55*Math.max(.5,attenuation):style.opacity*attenuation*.35;
          const line=svgEl('line',{...attrs,'stroke-width':strong?.6:moderate?.35:.2,
              'stroke-opacity':opacity});
          line.classList.add('study-edge');line.style.stroke='#fff';
          if(is4D){
            const gradientId=`${edgeGradientPrefix}-${edgeGradients.childElementCount}`;
            const gradient=svgEl('linearGradient',{id:gradientId,gradientUnits:'userSpaceOnUse',x1:p.x,y1:p.y,x2:q.x,y2:q.y});
            for(const [offset,id] of [[0,a],[1,b]]){
              const color=state.nodes.get(id).querySelector('.body').style.fill;
              gradient.append(svgEl('stop',{offset,'stop-color':color}));
            }
            edgeGradients.append(gradient);line.style.stroke=`url(#${gradientId})`;
          }
          if(strong)line.style.filter='drop-shadow(0 0 1.5px rgba(255,255,255,.65))';
          const title=svgEl('title');title.textContent=description;line.append(title);
          const hit=svgEl('line',attrs);hit.classList.add('study-edge-hit');
          hit.addEventListener('study-pair-select',()=>choosePair(a,b));
          hit.onclick=()=>{if(Date.now()>=state.cameraSuppressUntil)choosePair(a,b);};
          edges.append(line,hit);
          continue;
        }
        const attrs={x1:p.x,y1:p.y,x2:q.x,y2:q.y};
        const line=svgEl('line',{...attrs,'stroke-width':style.width,'stroke-opacity':style.opacity,'stroke-dasharray':style.dash});line.classList.add('study-edge');
        const title=svgEl('title');title.textContent=description;line.append(title);
        const hit=svgEl('line',attrs);hit.classList.add('study-edge-hit');hit.addEventListener('study-pair-select',()=>choosePair(a,b));hit.onclick=()=>{if(Date.now()>=state.cameraSuppressUntil)choosePair(a,b);};edges.append(line,hit);
        if(state.data.kind==='trial'){
          const category=state.overrides[k]??inferred(a,b);
          const text=svgEl('text',{x:(p.x+q.x)/2,y:(p.y+q.y)/2,'class':'study-relationship-label'});
          text.textContent=(category==='uncertain'?'Unable to judge':['Unrelated','Weak','Moderate','Strong'][category])+(marker?` ${marker}`:'');
          text.style.fontSize=`${9/(svg.getScreenCTM()?.a||1)}px`;
          text.style.fill=category==='uncertain'?'#484848':['#343434','#444444','#505050','#606060'][category];
          edges.append(text);
        }else if(marker){const text=svgEl('text',{x:(p.x+q.x)/2,y:(p.y+q.y)/2-6});text.classList.add('study-marker');text.textContent=marker;edges.append(text);}
      }
    };
    const tagLayout=new Map();let tagFrame=null,tagFrameTime=null;
    const drawTagLayout=(animate=false)=>{
      const now=performance.now(),dt=Math.min(50,now-(tagFrameTime??now-16));tagFrameTime=now;
      const alpha=animate?1-Math.exp(-dt/65):0;
      const scale=svg.getScreenCTM()?.a||1,pad=6/scale,gap=4/scale;
      const clamp=(v,lo,hi)=>Math.max(lo,Math.min(v,hi));
      let moving=false;
      for(const [id,l] of tagLayout){
        if(l.tag.style.display==='none')continue;
        if(animate){l.x+=(l.tx-l.x)*alpha;l.y+=(l.ty-l.y)*alpha;}
        const p=point(id),r=Number(l.node.querySelector('.body').getAttribute('r'));
        l.x=clamp(l.x,pad-p.x,1000-pad-p.x-l.w);
        l.y=clamp(l.y,pad-p.y-l.baseline,600-pad-p.y-l.baseline-l.h);
        l.tag.setAttribute('x',l.x);l.tag.setAttribute('y',l.y);
        const left=p.x+l.x,top=p.y+l.y+l.baseline;
        const end={x:clamp(p.x,left,left+l.w),y:clamp(p.y,top,top+l.h)};
        const distance=Math.hypot(end.x-p.x,end.y-p.y);
        l.line.style.display=distance>r+gap*2?'':'none';
        if(distance>0){
          l.line.setAttribute('x1',p.x+(end.x-p.x)*r/distance);l.line.setAttribute('y1',p.y+(end.y-p.y)*r/distance);
          l.line.setAttribute('x2',end.x);l.line.setAttribute('y2',end.y);
        }
        if(Math.abs(l.tx-l.x)+Math.abs(l.ty-l.y)>.1)moving=true;
      }
      if(moving&&tagFrame===null)tagFrame=requestAnimationFrame(()=>{tagFrame=null;drawTagLayout(true);});
    };
    const space2DTags=()=>{
      tagLeaders.replaceChildren();
      const scale=svg.getScreenCTM()?.a||1,pad=6/scale,gap=4/scale;
      const obstacles=[...state.nodes].map(([id,node])=>{
        const p=point(id),r=Number(node.querySelector('.body').getAttribute('r'))+gap;
        return {x:p.x-r,y:p.y-r,w:2*r,h:2*r};
      });
      const overlaps=(a,b)=>a.x<b.x+b.w+gap&&a.x+a.w+gap>b.x&&a.y<b.y+b.h+gap&&a.y+a.h+gap>b.y;
      const labels=[...state.nodes].map(([id,node])=>({id,node,tag:node.querySelector('.study-node-tag')}))
        .filter(item=>item.tag.style.display!=='none').map(item=>({...item,box:item.tag.getBBox()}))
        .sort((a,b)=>b.box.width-a.box.width||a.id.localeCompare(b.id));
      for(const {id,node,tag,box} of labels){
        const p=point(id),r=Number(node.querySelector('.body').getAttribute('r'));
        const w=box.width,h=box.height,baseline=box.y-Number(tag.getAttribute('y'));
        const clamp=(v,lo,hi)=>Math.max(lo,Math.min(v,hi));
        const previous=tagLayout.get(id);
        // Off-screen points must not leave orphan labels pinned to the viewport.
        if(p.x<0||p.x>1000||p.y<0||p.y>600){tag.style.display='none';continue;}
        const preferred={x:p.x+r+gap,y:p.y-h/2};
        const old=previous?{x:p.x+previous.tx,y:p.y+previous.ty+baseline}:preferred;
        const candidates=[];
        const candidate=(x,y)=>({x:clamp(x,pad,1000-pad-w),y:clamp(y,pad,600-pad-h),w,h});
        const add=(x,y)=>candidates.push(candidate(x,y));
        // Proximity to the node is primary; a small movement penalty prevents jitter.
        // Reconsider old placements so labels return when nearby space opens up.
        add(old.x,old.y);
        const reach=120/scale;
        for(let row=0;row<=Math.ceil(reach/(h+gap));row++)for(const sign of row?[1,-1]:[1]){
          const y=p.y-h/2+sign*row*(h+gap);
          add(p.x+r+gap,y);add(p.x-r-gap-w,y);add(p.x-w/2,y);
          for(let dx=-reach;dx<=reach;dx+=24/scale)add(p.x-w/2+dx,y);
        }
        const distance=c=>Math.hypot(p.x-clamp(p.x,c.x,c.x+c.w),p.y-clamp(p.y,c.y,c.y+c.h));
        const score=c=>distance(c)+.12*Math.hypot(c.x-old.x,c.y-old.y);
        candidates.sort((a,b)=>score(a)-score(b));
        const valid=c=>distance(c)<=r+reach&&!obstacles.some(o=>overlaps(c,o));
        let chosen=candidates.find(valid);
        const prior=candidate(old.x,old.y);
        if(chosen&&previous&&valid(prior)&&score(prior)<=score(chosen)+6/scale)chosen=prior;
        if(!chosen){tag.style.display='none';continue;}
        obstacles.push(chosen);
        const tx=chosen.x-p.x,ty=chosen.y-p.y-baseline;
        const line=svgEl('line',{stroke:'#555','stroke-width':.6,'stroke-opacity':.65,'vector-effect':'non-scaling-stroke'});
        tagLeaders.append(line);
        tagLayout.set(id,{node,tag,line,w,h,baseline,tx,ty,x:previous?.x??tx,y:previous?.y??ty});
      }
      drawTagLayout();
    };
    const renderNodes=()=>{
      const screenScale=svg.getScreenCTM()?.a||1;
      for(const [id,node] of state.nodes){
        const p=point(id);node.setAttribute('transform',`translate(${p.x} ${p.y})`);node.classList.toggle('selected',state.selected===id);
        const tag=node.querySelector('.study-node-tag');
        tag.textContent=state.data.tags?.[id]||'';
        tag.style.display=(state.data.kind==='explore'?state.data.show_tags:state.showTrialTags)&&tag.textContent?'':'none';
        const radius2D=Number(node.querySelector('.body').getAttribute('r'))||8;
        tag.setAttribute('x',radius2D+5/screenScale);tag.setAttribute('y',0);
        tag.style.fontSize=`${9/screenScale}px`;
        tag.style.fill=is3D?'#aaa':'#777';
        if(is3D){
          node.setAttribute('data-depth',p.z);node.style.display=p.visible?'':'none';
          const radius=.7*.75*.5*Math.max(7/screenScale,Math.min(36/screenScale,.065*focal/p.z));
          node.querySelector('.body').setAttribute('r',radius);
          // Flat fills: distance darkens nodes without sphere shading.
          const distance=cameraSpec.distance/state.camera.zoom;
          const depthFraction=Math.max(0,Math.min(1,(p.z-(distance-1))/2));
          const brightness=(1-depthFraction)**2.2;
          const shade=is4D?Math.round(3+177*brightness)+(state.selected===id?20:0):Math.round(64+191*Math.sqrt(brightness));
          node.querySelector('.body').style.stroke='none';
          node.querySelector('.body').style.fill=`rgb(${shade},${shade},${shade})`;
          if(!is4D)node.querySelector('.body').style.filter=`drop-shadow(0 0 2.5px rgba(255,255,255,${(.25+.45*brightness).toFixed(3)}))`;
          let fillLuminance=shade,tagColor=null;
          if(is4D){
            const rgb=fourthColor(state.data.world_positions[id][3]);
            const attenuation=state.selected===id?1:.22+.78*Math.sqrt(brightness);
            const highlight=.18*brightness;
            const channels=rgb.map(v=>Math.round(v*attenuation+(255-v*attenuation)*highlight));
            const color=`rgb(${channels.join(',')})`;
            node.querySelector('.body').style.fill=color;
            node.querySelector('.body').style.filter=`drop-shadow(0 0 2.5px rgba(${channels.join(',')},${(.25+.45*brightness).toFixed(3)}))`;
            fillLuminance=.2126*channels[0]+.7152*channels[1]+.0722*channels[2];
            tagColor=`rgb(${channels.map(v=>Math.round(v*.5)).join(',')})`;
          }
          const label=state.selected===id?238:Math.round(30+208*(1-depthFraction)**1.5);
          node.querySelector('text').style.fill=!is4D?'#080808':fillLuminance>=118?'#101010':`rgb(${label},${label},${label})`;
          node.querySelector('.hit').setAttribute('r',Math.max(radius,22/screenScale));
          node.querySelector('text').style.fontSize=`${.75*Math.max(11,10/screenScale)}px`;
          tag.setAttribute('x',radius+5/screenScale);
          tag.style.fontSize=`${Math.max(4,Math.min(11,9*distance/p.z))/screenScale}px`;
          const tagShade=Math.round(18+202*(1-depthFraction)**2.2);
          tag.style.fill=tagColor||`rgb(${tagShade},${tagShade},${tagShade})`;
        }
        node.querySelector('.study-playing-ring').setAttribute('r',Number(node.querySelector('.body').getAttribute('r'))+5/screenScale);
        if(tag.style.display!=='none'&&node.style.display!=='none'){
          // Measure final font sizing, then keep the entire label inside the viewBox.
          const padding=6/screenScale,gap=5/screenScale;
          const radius=Number(node.querySelector('.body').getAttribute('r'));
          tag.removeAttribute('textLength');tag.removeAttribute('lengthAdjust');
          let bounds=tag.getBBox();
          if(bounds.width>1000-2*padding){
            tag.setAttribute('textLength',Math.max(1,1000-2*padding));
            tag.setAttribute('lengthAdjust','spacingAndGlyphs');bounds=tag.getBBox();
          }
          let x=radius+gap;
          if(p.x+x+bounds.width>1000-padding)x=-radius-gap-bounds.width;
          x=Math.max(padding-p.x,Math.min(x,1000-padding-p.x-bounds.width));
          const y=Math.max(padding-p.y-bounds.y,Math.min(0,600-padding-p.y-bounds.y-bounds.height));
          tag.setAttribute('x',x);tag.setAttribute('y',y);
        }
      }
      if(!is3D)space2DTags();
    };
    const reflection=is3D?svgEl('g',{'class':'study-floor-reflection','pointer-events':'none','aria-hidden':'true'}):null;
    const reflectionId=is3D?`study-floor-${crypto.randomUUID()}`:null;
    if(reflection)svg.insertBefore(reflection,scene);
    const drawReflection=()=>{
      if(!reflection)return;
      reflection.replaceChildren();
      if(!state.data.show_reference_cube)return;
      // Screen Y increases downwards, so +Y is the cube's fixed bottom face.
      const floorY=worldCenter[1]+cubeHalf*worldRadius;
      const corners=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([x,z])=>project(cameraWorld([
        worldCenter[0]+x*cubeHalf*worldRadius,floorY,worldCenter[2]+z*cubeHalf*worldRadius])));
      if(corners.some(p=>!p.visible))return;
      const polygon=corners.map(p=>`${p.x},${p.y}`).join(' ');
      const defs=svgEl('defs'),clip=svgEl('clipPath',{id:reflectionId,clipPathUnits:'userSpaceOnUse'});
      clip.append(svgEl('polygon',{points:polygon}));defs.append(clip);reflection.append(defs);
      const ghosts=svgEl('g',{'clip-path':`url(#${reflectionId})`});
      for(const [id,node] of state.nodes){
        const world=state.data.world_positions[id],mirrored=[world[0],2*floorY-world[1],world[2]];
        const p=project(cameraWorld(mirrored));if(!p.visible)continue;
        const height=Math.max(0,(floorY-world[1])/(2*cubeHalf*worldRadius));
        const body=node.querySelector('.body');
        const radius=(Number(body.getAttribute('r'))||4)*cameraPoint(id).z/p.z;
        ghosts.append(svgEl('circle',{cx:p.x,cy:p.y,r:radius,fill:body.style.fill,
          'fill-opacity':.1*Math.exp(-2*height)}));
      }
      reflection.append(ghosts);
    };
    const reference=svgEl('g');
    const drawReference=()=>{
      reference.replaceChildren();if(!is3D||!state.data.show_reference_cube)return;
      const corners=Array.from({length:8},(_,i)=>cameraWorld(worldCenter.map((center,axis)=>center+((i>>axis)&1?1:-1)*cubeHalf*worldRadius)));
      for(let i=0;i<8;i++)for(let axis=0;axis<3;axis++){
        const j=i^(1<<axis);if(j<i)continue;
        const a=corners[i],b=corners[j];
        for(let step=0;step<8;step++){
          const at=t=>project({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,z:a.z+(b.z-a.z)*t});
          const u=at(step/8),v=at((step+1)/8),depth=(u.z+v.z)/2;
          if(!u.visible||!v.visible)continue;
          const centerDistance=cameraSpec.distance/state.camera.zoom;
          const depthRange=Math.sqrt(3)*cubeHalf;
          const nearness=Math.max(0,Math.min(1,(centerDistance+depthRange-depth)/(2*depthRange)));
          const line=svgEl('line',{x1:u.x,y1:u.y,x2:v.x,y2:v.y,'data-depth':depth,
              stroke:'#999','stroke-width':.8,'stroke-opacity':.035+.445*nearness**2,
              'vector-effect':'non-scaling-stroke','pointer-events':'none','class':'study-reference-edge'});
          reference.append(line);
        }
      }
    };
    const update=()=>{
      renderNodes();drawEdges();drawReference();drawReflection();
      if(is3D)scene.replaceChildren(...[...reference.children,...edges.children,...state.nodes.values()].sort((a,b)=>Number(b.getAttribute('data-depth'))-Number(a.getAttribute('data-depth'))));
      pathfinder?.update();
      if(submit)submit.disabled=state.data.public_demo?false:!ready();if(confirm)confirm.checked=state.confirmed;pairInfo();
    };
    let idleFrame=null,idleStopped=false,idleTime=null,idleDrawTime=0;
    const stopIdle=()=>{
      idleStopped=true;cancelAnimationFrame(idleFrame);
      if(is3D)cameras.set(state.context,structuredClone(state.camera));
    };
    const idleRotate=time=>{
      if(idleStopped)return;
      if(idleTime!==null&&!document.hidden){
        state.camera.yaw+=Math.min((time-idleTime)/1000,.1)*.03;
        if(time-idleDrawTime>=1000/24){update();idleDrawTime=time;}
      }
      idleTime=time;idleFrame=requestAnimationFrame(idleRotate);
    };
    if(is3D){
      root.addEventListener('pointerdown',stopIdle,true);
      root.addEventListener('wheel',stopIdle,{capture:true,passive:true});
      root.addEventListener('keydown',stopIdle,true);
      state.startIdle=()=>{idleFrame=requestAnimationFrame(idleRotate);};
    }
    const play=async id=>{
      if(pathfinder?.pick(id))return;
      if(state.data.kind==='explore'&&state.selected===id){
        const audio=state.audios.get(id);if(audio)shared.reset(audio);
        state.selected=null;state.pair=null;update();
        emit('select',{id:null,context:state.context});
        info.textContent='Click a node to listen and reveal its connections.';
        return;
      }
      state.selected=id;update();
      const item=state.data.items.find(item=>item.id===id);
      info.textContent=state.data.kind==='trial'?`Stimulus ${index.get(id)}`:`Stimulus ${index.get(id)} · ${item.label} · ${item.notes}`;
      if(state.data.kind==='trial')state.interactions[id].considered=true;
      const audio=state.audios.get(id);
      if(audio){
        if(state.data.kind==='trial')shared.reset(audio);
        else if(!audio.paused){audio.pause();emit('select',{id,context:state.context});return;}
        shared.activate(audio);try{await audio.play();}catch(_){info.textContent='Playback unavailable; use the node again after checking resources.';}
        if(state.data.kind==='trial')emit('draft');else emit('select',{id,context:state.context});
      }else emit('play',{id,context:state.context});
    };
    for(const item of data.items){
      const node=svgEl('g',{tabindex:0,role:'button','aria-label':`Stimulus ${index.get(item.id)}: click to play, drag to ${is3D?'orbit':'position'}`});node.classList.add('study-node');node.dataset.id=item.id;
      const hit=svgEl('circle',{r:30});hit.classList.add('hit');const body=svgEl('circle',{r:16});body.classList.add('body');const text=svgEl('text');text.textContent=index.get(item.id);
      const playingRing=svgEl('circle',{'class':'study-playing-ring','aria-hidden':'true','pointer-events':'none'});
      node.append(hit,body,playingRing,text);
      const tag=svgEl('text',{'class':'study-node-tag'});node.append(tag);
      if(data.kind==='trial'&&!data.public_demo)node.oncontextmenu=event=>tagMenu(event,item.id);
      if(data.kind==='explore'&&!data.public_demo){const title=svgEl('title');title.textContent=`${item.label}\n${item.notes}`+(is4D?`\nFourth MDS coordinate: ${data.world_positions[item.id][3].toFixed(4)}`:'');node.append(title);}
      nodes.append(node);state.nodes.set(item.id,node);
      let suppress=0;
      node.onpointerdown=event=>{
        if(state.data.kind!=='trial'||event.button!==0)return;
        const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());
        state.drag={id:item.id,pointer:event.pointerId,start:p,original:point(item.id),moved:false};node.setPointerCapture(event.pointerId);
      };
      node.onpointermove=event=>{
        const drag=state.drag;if(!drag||drag.pointer!==event.pointerId)return;
        const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());
        const scale=svg.getScreenCTM().a;
        if(!drag.moved&&Math.hypot(p.x-drag.start.x,p.y-drag.start.y)*scale<5)return;
        drag.moved=true;
        const x=Math.max(50,Math.min(950,drag.original.x+p.x-drag.start.x));const y=Math.max(50,Math.min(550,drag.original.y+p.y-drag.start.y));
        state.positions[item.id]={x:x/1000,y:y/600};state.interactions[item.id].moved=true;update();
        if(!state.timer)state.timer=setTimeout(()=>{state.timer=null;emit('draft');},350);
        event.preventDefault();
      };
      const end=event=>{
        if(!state.drag||state.drag.pointer!==event.pointerId)return;
        if(state.drag.moved){suppress=Date.now()+350;emit('draft');}
        state.drag=null;if(node.hasPointerCapture(event.pointerId))node.releasePointerCapture(event.pointerId);
      };
      node.onpointerup=end;node.onpointercancel=end;
      node.onclick=()=>{if(Date.now()>=Math.max(suppress,state.cameraSuppressUntil))play(item.id);};
      node.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();play(item.id);}};
    }
    if(is3D){
      pathfinder=createStudyPathfinder({root,svg,state,index,point,worldCenter,getCamera:()=>state.camera,
        setCamera:camera=>{state.camera=camera;cameras.set(state.context,structuredClone(camera));},update,stopIdle});
      state.pathfinder=pathfinder;
    }
    if(data.kind==='explore'){
      if(!is3D)svg.classList.add('study-svg-2d');
      const reset=html('button','study-reset-view','Reset View');
      const remember=()=>{cameras.set(state.context,structuredClone(state.camera));update();};
      reset.onclick=()=>{state.camera=defaultCamera();remember();};controls.append(reset);
      svg.ondblclick=event=>{event.preventDefault();state.camera=defaultCamera();remember();};
      controls.append(html('span','study-camera-help',is3D?'Perspective · drag: orbit · wheel/pinch: zoom · Shift-drag: pan':'Drag: pan · wheel/pinch: zoom'));
      const zoomAt=(zoom,from,to=from)=>{
        const c=state.camera,ratio=zoom/c.zoom;
        c.panX=to.x-500-ratio*(from.x-500-c.panX);
        c.panY=to.y-300-ratio*(from.y-300-c.panY);c.zoom=zoom;
      };
      const pointers=new Map();
      const location=event=>new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());
      svg.oncontextmenu=event=>event.preventDefault();
      // Wide invisible connection targets must never steal a visible node click.
      const nodeAt=p=>{
        const ordered=is3D?[...scene.children].reverse():[...state.nodes.values()].reverse();
        for(const node of ordered){
          if(!node.classList.contains('study-node')||node.style.display==='none')continue;
          const center=point(node.dataset.id),radius=Number(node.querySelector('.body').getAttribute('r'));
          if(Math.hypot(p.x-center.x,p.y-center.y)<=radius)return node;
        }
        return null;
      };
      svg.onpointerdown=event=>{
        if(event.button!==0&&event.button!==2)return;
        const p=location(event),node=nodeAt(p)||event.target.closest('.study-node'),edge=node?null:event.target.closest('.study-edge-hit');
        pointers.set(event.pointerId,{x:p.x,y:p.y,startX:event.clientX,startY:event.clientY,moved:false,
                                   node:node?.dataset.id,edge,pan:event.shiftKey||event.button===2,multi:pointers.size>0});
        if(pointers.size>1)for(const pointer of pointers.values())pointer.multi=true;
        svg.setPointerCapture(event.pointerId);event.preventDefault();
      };
      svg.onpointerleave=()=>pathfinder?.hover(null);
      svg.onpointermove=event=>{
        const pointer=pointers.get(event.pointerId),p=location(event);
        const hovered=pointer?null:nodeAt(p)||event.target.closest('.study-node');
        pathfinder?.hover(hovered?.dataset.id||null);
        if(!pointer)return;
        if(!pointer.moved&&!pointer.multi&&Math.hypot(event.clientX-pointer.startX,event.clientY-pointer.startY)<5)return;
        pointer.moved=true;
        const previous=[...pointers.values()].map(v=>({x:v.x,y:v.y}));
        const dx=p.x-pointer.x,dy=p.y-pointer.y;pointer.x=p.x;pointer.y=p.y;
        if(pointers.size>=2){
          const current=[...pointers.values()],oldLength=Math.hypot(previous[0].x-previous[1].x,previous[0].y-previous[1].y);
          const length=Math.hypot(current[0].x-current[1].x,current[0].y-current[1].y);
          if(!is3D){
            const oldCenter={x:(previous[0].x+previous[1].x)/2,y:(previous[0].y+previous[1].y)/2};
            const center={x:(current[0].x+current[1].x)/2,y:(current[0].y+current[1].y)/2};
            zoomAt(Math.max(.25,Math.min(8,state.camera.zoom*(oldLength>1?length/oldLength:1))),oldCenter,center);
          }else{
            if(oldLength>1)state.camera.zoom=Math.max(.35,Math.min(2.2,state.camera.zoom*length/oldLength));
            state.camera.panX+=dx/2;state.camera.panY+=dy/2;
          }
        }else if(pointer.pan||!is3D){state.camera.panX+=dx;state.camera.panY+=dy;}
        else{state.camera.yaw+=dx*.008;state.camera.pitch=Math.max(-1.54,Math.min(1.54,state.camera.pitch+dy*.008));}
        remember();event.preventDefault();
      };
      const endCamera=event=>{
        const pointer=pointers.get(event.pointerId);if(!pointer)return;
        pointers.delete(event.pointerId);if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);
        state.cameraSuppressUntil=Date.now()+350;
        if(event.type==='pointerup'&&!pointer.moved&&!pointer.multi&&!pointer.pan){
          if(pointer.node)play(pointer.node);
          else if(pointer.edge)pointer.edge.dispatchEvent(new Event('study-pair-select'));
        }
      };
      svg.onpointerup=endCamera;svg.onpointercancel=endCamera;
      svg.addEventListener('wheel',event=>{
        event.preventDefault();
        if(is3D)state.camera.zoom=Math.max(.35,Math.min(2.2,state.camera.zoom*Math.exp(-event.deltaY*.001)));
        else zoomAt(Math.max(.25,Math.min(8,state.camera.zoom*Math.exp(-event.deltaY*.001))),location(event));
        remember();
      },{passive:false});
    }
    if(data.kind==='trial'&&!data.public_demo){
      pairSelect=html('select');pairSelect.setAttribute('aria-label','Pair');
      for(const [a,b] of pairs){const option=html('option',null,`Pair ${index.get(a)}–${index.get(b)}`);option.value=key(a,b);pairSelect.append(option);}
      pairSelect.onchange=()=>{state.pair=pairSelect.value.split('|');pairInfo();};controls.append(pairSelect);
      overrideSelect=html('select');overrideSelect.setAttribute('aria-label','Pair judgment override');
      for(const [value,label] of [['auto','Automatic / clear override'],['0','0 · Unrelated'],['1','1 · Weakly related'],['2','2 · Moderately related'],['3','3 · Strongly related'],['uncertain','Unable to judge']]){
        const option=html('option',null,label);option.value=value;overrideSelect.append(option);
      }
      overrideSelect.onchange=()=>{
        if(!state.pair)state.pair=pairs[0];const k=key(...state.pair);
        if(overrideSelect.value==='auto')delete state.overrides[k];else state.overrides[k]=overrideSelect.value==='uncertain'?'uncertain':Number(overrideSelect.value);
        for(const id of state.pair)state.interactions[id].considered=true;
        update();emit('draft');
      };controls.append(overrideSelect);
      const label=html('label');confirm=html('input');confirm.type='checkbox';confirm.checked=state.confirmed;
      confirm.onchange=()=>{state.confirmed=confirm.checked;update();emit('draft');};label.append(confirm,document.createTextNode('I have considered the final arrangement'));controls.append(label);
      submit=html('button',null,'Submit Arrangement');submit.className='study-submit';submit.onclick=()=>{if(ready()){submit.disabled=true;emit('submit');}};controls.append(submit);
      state.pair=pairs[0];
    }
    if(data.kind==='trial'&&data.public_demo){
      submit=html('button','study-submit','Submit arrangement');submit.onclick=()=>emit('submit');controls.append(submit);
    }
    const resize=()=>{
      if(is3D){renderNodes();pathfinder?.update();return;}
      const scale=svg.getScreenCTM()?.a||1;
      for(const node of state.nodes.values()){
        node.querySelector('.body').setAttribute('r',(data.kind==='explore'?.5:1)*Math.max(16,12/scale));node.querySelector('.hit').setAttribute('r',Math.max(24,22/scale));
        node.querySelector('text').style.fontSize=`${(data.kind==='explore'?.75:1)*Math.max(12,10/scale)}px`;
      }
      renderNodes();drawEdges();
    };
    if(data.kind==='explore'){
      info.classList.add('study-explore-info');controls.append(info);
    }
    const observer=new ResizeObserver(resize);observer.observe(svg);
    state.refresh=()=>{
      if(state.exploreTagsToggle)state.exploreTagsToggle.checked=!!state.data.show_tags;
      if(state.durationButtons)for(const [seconds,button] of state.durationButtons){
        button.setAttribute('aria-pressed',String((state.data.audio_seconds??15)===seconds));button.disabled=false;
      }
      if(state.previewToggle){state.previewToggle.checked=!!state.data.fast_preview;state.previewToggle.disabled=false;}
      legend.replaceChildren();
      const labels=state.data.kind==='trial'?(state.data.feedback?['Your current arrangement responses','0 · Unrelated (d > .40)','1 · Weak (.23 < d ≤ .40)','2 · Moderate (.10 < d ≤ .23)','3 · Strong (d ≤ .10)','* Manual override · ? Unable to judge']:['Feedback hidden · manual judgments are optional']):state.data.evidence?['Evidence counts only','Unobserved · 1 measurement · 2 measurements · 3+ measurements']:['Recorded relationships · select a node','Unobserved ≠ Unrelated'];
      if(is4D){
        const scale=html('span','study-fourth-scale');
        scale.append(html('span',null,`W −${wExtent.toFixed(3)}`),html('span','study-fourth-gradient'),html('span',null,`+${wExtent.toFixed(3)}`));
        scale.title='Fourth fitted coordinate: violet = lower, blue/cyan = middle, yellow = higher; cyan transitions through desaturated tones to avoid green. Arbitrary axis orientation, not emotional categories.';
        legend.append(scale);
      }
      if(is3D&&state.data.connection_level&&state.data.connection_level!=='None')labels.push(`${state.data.connection_level} and stronger connections shown`);
      for(const label of labels){const span=html('span',null,label);const category=label.match(/^([0-3])/);if(category)span.title=state.data.category_descriptions[category[1]]||'';legend.append(span);}
      if(!state.drag&&state.data.kind==='explore')state.positions=structuredClone(state.data.positions);
      for(const item of state.data.items){
        if(!item.url)continue;
        let audio=state.audios.get(item.id);
        if(!audio){
          audio=document.createElement('audio');audio.preload='none';audio.src=item.url;state.audios.set(item.id,audio);state.unregister.push(shared.register(audio));
          const node=state.nodes.get(item.id);audio.onplay=()=>{node.classList.add('playing');if(state.data.kind==='trial'){state.interactions[item.id].auditioned=true;state.interactions[item.id].considered=true;emit('draft');}};audio.onpause=()=>node.classList.remove('playing');audio.onended=()=>node.classList.remove('playing');audio.onerror=()=>node.classList.remove('playing');audio.onemptied=()=>node.classList.remove('playing');
        }else if(audio.src!==new URL(item.url,location.href).href){shared.reset(audio);audio.src=item.url;}
      }
      for (const [id,audio] of state.audios) {
        if(!state.data.items.find(item=>item.id===id)?.url) {
          shared.reset(audio); shared.players.delete(audio); audio.removeAttribute('src'); audio.load();
          state.audios.delete(id);
        }
      }
      const request=state.data.play_request;
      if(request&&!state.autoPlayed.has(request.token)&&state.audios.has(request.id)&&(state.data.kind!=='explore'||state.selected===request.id)){
        state.autoPlayed.add(request.token);const audio=state.audios.get(request.id);if(state.data.kind==='trial')shared.reset(audio);shared.activate(audio);audio.play().catch(()=>{info.textContent='Tap the node again to start playback.';});
      }
      save.textContent=state.data.kind==='trial'?`Draft saved · trial ${state.data.pending.sequence}`:'';
      update();resize();
    };
    const exposureTokens=window.__hsgStudyExposureTokens||(window.__hsgStudyExposureTokens=new Set());
    if(!data.public_demo&&(data.kind==='explore'||data.feedback))requestAnimationFrame(()=>{
      const token=state.data.exposure_token;
      if(root.__study===state&&token&&!exposureTokens.has(token)){
        exposureTokens.add(token);setTriggerValue('exposure',{token});
      }
    });
    state.dispose=()=>{pathfinder?.dispose();cancelAnimationFrame(idleFrame);root.removeEventListener('pointerdown',stopIdle,true);root.removeEventListener('wheel',stopIdle,true);root.removeEventListener('keydown',stopIdle,true);cancelAnimationFrame(tagFrame);clearTimeout(state.timer);root.removeEventListener('pointerdown',closeMenu);observer.disconnect();state.unregister.forEach(fn=>fn());root.replaceChildren();if(root.__study===state)delete root.__study;};
  }
  const state=root.__study;
  if(data.pending && data.pending.revision>state.revision && !state.drag) {
    state.positions=structuredClone(data.positions);state.overrides=structuredClone(data.pending.overrides);
    state.interactions=structuredClone(data.pending.interactions);state.confirmed=data.pending.confirmed;
  }
  state.revision=Math.max(state.revision,data.pending?.revision||0);
  state.data=data;state.refresh();
  if(state.startIdle){state.startIdle();delete state.startIdle;}
  return ()=>state.dispose();
}
