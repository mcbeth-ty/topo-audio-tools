// Exploratory graph routes only; never changes coordinates or study observations.
function studyPathGraph(ids,coordinates,pairs){
  const graph=new Map(ids.map(id=>[id,new Map()]));graph.rawDistances=new Map();
  for(const pair of Object.values(pairs)){
    if(!pair.valid_count||pair.relatedness<1)continue;
    const [a,b]=pair.ids;if(!graph.has(a)||!graph.has(b)||a===b)continue;
    const p=coordinates[a],q=coordinates[b];
    const distance=Math.hypot(...p.map((v,i)=>v-q[i]));
    if(!Number.isFinite(distance))continue;
    const penalty={1:4,2:2,3:1}[pair.relatedness];if(!penalty)continue;
    graph.get(a).set(b,distance*penalty);graph.get(b).set(a,distance*penalty);
    graph.rawDistances.set([a,b].sort().join('|'),distance);
  }
  return graph;
}
function studyShortestRoute(graph,start,end,blockedNodes=new Set(),blockedEdges=new Set()){
  if(!graph.has(start)||!graph.has(end)||blockedNodes.has(start)||blockedNodes.has(end))return null;
  const queue=[{nodes:[start],cost:0}],visited=new Set();
  const compare=(a,b)=>a.cost-b.cost||a.nodes.join('|').localeCompare(b.nodes.join('|'));
  while(queue.length){
    queue.sort(compare);const current=queue.shift(),last=current.nodes.at(-1);
    if(visited.has(last))continue;visited.add(last);
    if(last===end)return current;
    for(const [next,weight] of graph.get(last)){
      if(visited.has(next)||blockedNodes.has(next)||blockedEdges.has(`${last}|${next}`))continue;
      queue.push({nodes:[...current.nodes,next],cost:current.cost+weight});
    }
  }
  return null;
}
function studyPathRoutes(graph,start,end,count=3){
  const first=studyShortestRoute(graph,start,end);if(!first)return [];
  const routes=[first],candidates=new Map();
  const signature=nodes=>nodes.join('|');
  for(let n=1;n<count;n++){
    const previous=routes[n-1];
    for(let i=0;i<previous.nodes.length-1;i++){
      const root=previous.nodes.slice(0,i+1),blockedEdges=new Set();
      for(const route of routes)if(root.every((id,j)=>route.nodes[j]===id)&&route.nodes.length>i+1)
        blockedEdges.add(`${route.nodes[i]}|${route.nodes[i+1]}`);
      const spur=studyShortestRoute(graph,root.at(-1),end,new Set(root.slice(0,-1)),blockedEdges);
      if(!spur)continue;
      const nodes=[...root.slice(0,-1),...spur.nodes],key=signature(nodes);
      if(routes.some(route=>signature(route.nodes)===key))continue;
      let cost=0;for(let j=1;j<nodes.length;j++)cost+=graph.get(nodes[j-1]).get(nodes[j]);
      candidates.set(key,{nodes,cost});
    }
    const choices=[...candidates.values()].sort((a,b)=>a.cost-b.cost||signature(a.nodes).localeCompare(signature(b.nodes)));
    if(!choices.length)break;
    routes.push(choices[0]);candidates.delete(signature(choices[0].nodes));
  }
  for(const route of routes){route.distance=0;for(let i=1;i<route.nodes.length;i++)route.distance+=graph.rawDistances?.get([route.nodes[i-1],route.nodes[i]].sort().join('|'))??graph.get(route.nodes[i-1]).get(route.nodes[i]);}
  return routes;
}

function createStudyPathfinder({root,svg,state,index,point,worldCenter,getCamera,setCamera,update,stopIdle}){
  const ns='http://www.w3.org/2000/svg';
  const element=(tag,cls,text)=>{const el=document.createElement(tag);el.className=cls;if(text)el.textContent=text;return el;};
  const svgElement=(tag,attrs)=>{const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);return el;};
  const button=(text,label,callback)=>{const el=element('button','',text);el.type='button';el.title=label;el.setAttribute('aria-label',label);el.onclick=callback;return el;};
  const overlay=element('div','study-pathfinder'),panel=element('div','study-pathfinder-panel');panel.hidden=true;
  const launcher=button('⌁','Open pathfinder',()=>open?close():show());launcher.className='study-pathfinder-launch';launcher.setAttribute('aria-expanded','false');
  const heading=element('div','study-pathfinder-heading','Pathfinder');heading.append(button('×','Close pathfinder',()=>close()));panel.append(heading);
  let open=false,picking=null,hovered=null,start=null,end=null,routes=[],routeIndex=0,nodeIndex=0,animation=null,originalCamera=null;
  const picks=element('div','study-pathfinder-picks');
  const startButton=button('Start · —','Choose start node',()=>pick('start'));
  const endButton=button('Destination · —','Choose destination node',()=>pick('end'));picks.append(startButton,endButton);panel.append(picks);
  const hint=element('div','study-pathfinder-hint','Choose start, then click a node.');hint.setAttribute('role','status');hint.setAttribute('aria-live','polite');panel.append(hint);
  const calculate=button('Calculate smooth path','Calculate smooth path',()=>{
    routes=studyPathRoutes(studyPathGraph(state.data.ids,state.data.world_positions,state.data.pairs),start,end);
    routeIndex=0;nodeIndex=0;picking=null;markRoute();paint();
    if(routes.length)focusCurrent();else hint.textContent='No Weak-or-stronger route connects these nodes.';
  });calculate.className='study-pathfinder-calculate';panel.append(calculate);
  const routeControls=element('div','study-pathfinder-step'),routeLabel=element('span','','Route —');
  const previousRoute=button('‹','Previous route',()=>switchRoute(-1)),nextRoute=button('›','Next route',()=>switchRoute(1));routeControls.append(previousRoute,routeLabel,nextRoute);panel.append(routeControls);
  const nodeControls=element('div','study-pathfinder-step'),nodeLabel=element('span','study-pathfinder-index','—');
  const previousNode=button('‹','Previous path node',()=>step(-1)),nextNode=button('›','Next path node',()=>step(1));nodeControls.append(previousNode,nodeLabel,nextNode);panel.append(nodeControls);
  const details=element('div','study-pathfinder-detail');panel.append(details);
  const rule=element('div','study-pathfinder-footnote',`Weak+ only · ${state.data.n_components}D distance × strength penalty`);
  rule.title='Minimize total fitted MDS distance × penalty: Strong ×1, Moderate ×2, Weak ×4. Unrelated and unobserved pairs are excluded. This is an exploratory routing rule, not a new MDS fit.';panel.append(rule);
  overlay.append(panel,launcher);root.append(overlay);
  const layer=svgElement('g',{'class':'study-pathfinder-path','pointer-events':'none','aria-hidden':'true'});
  svg.append(layer);
  const hoverRing=svgElement('circle',{'class':'study-pathfinder-hover-ring','fill':'none','pointer-events':'none','vector-effect':'non-scaling-stroke','aria-hidden':'true'});
  hoverRing.style.display='none';svg.append(hoverRing);
  function updateHover(){
    const node=hovered&&state.nodes.get(hovered),p=node?point(hovered):null;
    const visible=open&&picking&&node&&node.style.display!=='none'&&p.visible;
    hoverRing.style.display=visible?'':'none';
    if(!visible)return;
    const scale=svg.getScreenCTM()?.a||1;
    hoverRing.setAttribute('cx',p.x);hoverRing.setAttribute('cy',p.y);
    hoverRing.setAttribute('r',Number(node.querySelector('.body').getAttribute('r'))+4/scale);
  }
  function paint(){
    svg.classList.toggle('pathfinder-picking',open&&!!picking);updateHover();
    startButton.textContent=`Start · ${start?index.get(start):'—'}`;endButton.textContent=`Destination · ${end?index.get(end):'—'}`;
    startButton.setAttribute('aria-pressed',String(picking==='start'));endButton.setAttribute('aria-pressed',String(picking==='end'));
    calculate.disabled=!start||!end||start===end;
    const route=routes[routeIndex];routeControls.hidden=nodeControls.hidden=!route;
    routeLabel.textContent=route?`Route ${routeIndex+1} / ${routes.length}`:'Route —';
    previousRoute.disabled=nextRoute.disabled=routes.length<2;
    previousNode.disabled=!route||nodeIndex===0;nextNode.disabled=!route||nodeIndex===route.nodes.length-1;
    nodeLabel.textContent=route?String(index.get(route.nodes[nodeIndex])):'—';
    nodeLabel.setAttribute('aria-label',route?`Stimulus ${index.get(route.nodes[nodeIndex])}`:'No path node');
    details.textContent=route?`${nodeIndex+1} / ${route.nodes.length} · distance ${route.distance.toFixed(2)} · score ${route.cost.toFixed(2)}`:'';
    if(picking)hint.textContent=`Click a node for ${picking==='start'?'start':'destination'}.`;
    else if(route)hint.textContent=routeIndex===0?'Smoothest route':'Alternative smooth route';
    else if(start&&end)hint.textContent=start===end?'Choose two different nodes.':'No route yet. Calculate to search Weak+ connections.';
  }
  function clearRoute(){routes=[];routeIndex=nodeIndex=0;markRoute();}
  function pick(which){picking=which;hovered=null;paint();}
  function markRoute(){
    layer.replaceChildren();
    for(const node of state.nodes.values()){
      node.classList.remove('pathfinder-route','pathfinder-current');node.style.removeProperty('--pathfinder-delay');
      node.querySelector('.study-pathfinder-node-ring')?.remove();
    }
    const route=routes[routeIndex];if(!open||!route){update();return;}
    for(let i=1;i<route.nodes.length;i++)layer.append(svgElement('line',{'class':'study-pathfinder-line','style':`animation-delay:${(i-1)*.12}s`,'vector-effect':'non-scaling-stroke'}));
    for(const [i,id] of route.nodes.entries()){
      const node=state.nodes.get(id);node.classList.add('pathfinder-route');node.style.setProperty('--pathfinder-delay',`${i*.12}s`);
      const ring=svgElement('circle',{'class':'study-pathfinder-node-ring','fill':'none','pointer-events':'none','vector-effect':'non-scaling-stroke'});
      node.insertBefore(ring,node.querySelector('text'));
    }
    update();
  }
  function interrupt(){cancelAnimationFrame(animation);animation=null;}
  function animateCamera(target){
    interrupt();const from=structuredClone(getCamera()),begin=performance.now();
    const yawDelta=Math.atan2(Math.sin(target.yaw-from.yaw),Math.cos(target.yaw-from.yaw));
    const reduced=window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    function tick(time){
      const t=reduced?1:Math.min(1,(time-begin)/650),smooth=t*t*(3-2*t);
      const camera={...from,yaw:from.yaw+yawDelta*smooth};
      for(const key of ['pitch','zoom','panX','panY'])camera[key]=from[key]+(target[key]-from[key])*smooth;
      setCamera(camera);update();
      if(t<1)animation=requestAnimationFrame(tick);else animation=null;
    }
    animation=requestAnimationFrame(tick);
  }
  function focusCurrent(){
    const route=routes[routeIndex];if(!route)return;
    const id=route.nodes[nodeIndex],p=state.data.world_positions[id].slice(0,3).map((v,i)=>v-worldCenter[i]);
    const camera=getCamera(),horizontal=Math.hypot(p[0],p[2]);
    const target={...camera,zoom:Math.min(1,camera.zoom),panX:0,panY:0};
    if(Math.hypot(...p)>1e-12){target.yaw=Math.atan2(-p[0],p[2]);target.pitch=Math.atan2(p[1],horizontal);}
    animateCamera(target);paint();update();
  }
  function step(direction){const route=routes[routeIndex];if(!route)return;nodeIndex=Math.max(0,Math.min(route.nodes.length-1,nodeIndex+direction));focusCurrent();}
  function switchRoute(direction){if(!routes.length)return;routeIndex=(routeIndex+direction+routes.length)%routes.length;nodeIndex=0;markRoute();focusCurrent();}
  function show(){open=true;originalCamera=structuredClone(getCamera());stopIdle();panel.hidden=false;launcher.setAttribute('aria-expanded','true');paint();position();}
  function close(){open=false;picking=null;hovered=null;paint();panel.hidden=true;launcher.setAttribute('aria-expanded','false');clearRoute();if(originalCamera)animateCamera(originalCamera);launcher.focus();}
  function position(){
    const box=svg.getBoundingClientRect(),parent=root.getBoundingClientRect();
    overlay.style.left=`${box.left-parent.left+10}px`;overlay.style.top=`${box.bottom-parent.top-10}px`;
    panel.style.maxHeight=`${Math.max(72,box.height-46)}px`;panel.style.width=`${Math.min(260,Math.max(120,box.width-20))}px`;
  }
  const observer=new ResizeObserver(position);observer.observe(svg);
  const onKey=event=>{if(event.key==='Escape'&&open){event.preventDefault();close();}};
  root.addEventListener('keydown',onKey);
  root.addEventListener('pointerdown',interrupt,true);root.addEventListener('wheel',interrupt,{capture:true,passive:true});
  paint();position();
  return {
    pick(id){if(!open||!picking)return false;hovered=null;const which=picking;clearRoute();if(which==='start')start=id;else end=id;picking=which==='start'&&!end?'end':null;paint();return true;},
    hover(id){hovered=open&&picking?id:null;updateHover();},
    update(){
      updateHover();
      const route=routes[routeIndex];if(!open||!route)return;
      const lines=[...layer.children];
      for(let i=1;i<route.nodes.length;i++){
        const p=point(route.nodes[i-1]),q=point(route.nodes[i]),line=lines[i-1];line.style.display=p.visible&&q.visible?'':'none';
        for(const [key,value] of Object.entries({x1:p.x,y1:p.y,x2:q.x,y2:q.y}))line.setAttribute(key,value);
      }
      const scale=svg.getScreenCTM()?.a||1;
      for(const id of route.nodes){
        const node=state.nodes.get(id),ring=node.querySelector('.study-pathfinder-node-ring');
        if(ring)ring.setAttribute('r',Number(node.querySelector('.body').getAttribute('r'))+3/scale);
        node.classList.toggle('pathfinder-current',id===route.nodes[nodeIndex]);
      }
    },
    dispose(){interrupt();observer.disconnect();root.removeEventListener('keydown',onKey);root.removeEventListener('pointerdown',interrupt,true);root.removeEventListener('wheel',interrupt,true);overlay.remove();layer.remove();hoverRing.remove();svg.classList.remove('pathfinder-picking');},
    get routes(){return routes;},get routeIndex(){return routeIndex;},get nodeIndex(){return nodeIndex;}
  };
}
