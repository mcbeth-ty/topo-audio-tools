function atlasPopup(root){
  const popup=document.createElement('aside');popup.className='atlas-popup';popup.hidden=true;popup.setAttribute('aria-label','Introduction');
  const close=document.createElement('button');close.className='atlas-popup-close';close.textContent='×';close.setAttribute('aria-label','Dismiss introduction');
  const title=document.createElement('h3'),body=document.createElement('div');body.className='atlas-popup-text';body.setAttribute('aria-live','off');
  const actions=document.createElement('div');actions.className='atlas-popup-actions';
  const reveal=document.createElement('button');reveal.className='atlas-popup-reveal';reveal.textContent='Show all';reveal.title='Reveal remaining text';
  popup.append(close,title,body,reveal,actions);root.append(popup);
  let timer=null,text='',dismiss=null;
  const finish=()=>{cancelAnimationFrame(timer);body.textContent=text;reveal.hidden=true;};reveal.onclick=finish;
  const hide=()=>{cancelAnimationFrame(timer);popup.hidden=true;};close.onclick=()=>{hide();dismiss?.();};
  return {element:popup,hide,show(heading,content,buttons=[],onDismiss=null){
    cancelAnimationFrame(timer);dismiss=onDismiss;text=content;title.textContent=heading;actions.replaceChildren();body.textContent='';
    for(const [label,callback] of buttons){const b=document.createElement('button');b.textContent=label;b.onclick=callback;actions.append(b);}
    popup.hidden=false;popup.classList.remove('atlas-popup-enter');void popup.offsetWidth;popup.classList.add('atlas-popup-enter');
    if(matchMedia('(prefers-reduced-motion:reduce)').matches){finish();return;}
    // Use elapsed time, not timer ticks: larger models must not slow the text.
    const started=performance.now(),duration=1200;reveal.hidden=false;
    const tick=now=>{
      const progress=Math.min(1,(now-started)/duration);
      body.textContent=text.slice(0,Math.ceil(text.length*progress));
      if(progress>=1)finish();else timer=requestAnimationFrame(tick);
    };
    timer=requestAnimationFrame(tick);
  },dispose(){hide();popup.remove();}};
}
const ATLAS_TEXT={
  intro:'This model contains 24 short sound samples, organized according to their perceived relationships.\n\nListeners compare sounds in manageable groups of four. These judgments are combined using multidimensional scaling to produce a spatial representation of their relationships.\n\nThree dimensions determine the positions of the sounds, while a fourth is represented through color.\n\nConnections between sounds are drawn as lines of varying thickness, representing the strength of their judged relationships.\n\nClick and drag to rotate the model. Select any node to listen to its sound.',
  tags:'During experimental listening trials, participants can assign descriptive tags to sounds, but these labels remain hidden while relational judgments are being collected.\n\nThis encourages listeners to focus on the sounds themselves and their non-verbal relationships, rather than allowing descriptive language to guide their decisions.\n\nOnce a model has been established, tags can be revealed to help interpret and explore the resulting landscape.',
  path:'Pathfinder searches for routes through the model that balance gradual perceptual transitions with efficient travel between two selected sounds.\n\nRather than jumping directly from one experience to another, it identifies possible sequences of intermediate sounds that may create smoother changes in perceived character.\n\nThis is an exploratory foundation for investigating how musical transitions might eventually support more continuous, emotionally meaningful listening experiences.',
  usePath:'1. Select Start, then click a node in the model to choose your starting sound.\n2. Select Destination, then click another node to choose your destination.\n3. Click Calculate smooth path to discover possible routes between them.\n\nExplore the resulting paths to hear how different sequences travel through the sound landscape.',
  arrange:'Affective Atlas uses an augmented free-arrangement method to collect judgments about how sounds relate to one another.\n\nRather than rating each relationship separately, listeners arrange small groups of sounds in a shared space. Sounds perceived as more closely related can be placed nearer together, while more distinct sounds can be positioned farther apart.\n\nThis allows multiple relationships to be judged simultaneously, making the process more efficient and intuitive.\n\nListen to each sample, arrange the four sounds according to their perceived relationships, and submit your arrangement.\n\nThis is a demonstration. Your judgments will not be recorded or added to the research data.',
  generator:'The Ambient Generator creates short musical textures using a constrained system of harmonic structures, voice movement, and temporal development.\n\nRather than relying on predefined musical excerpts, the system produces new stimuli from configurable harmonic relationships. This allows researchers to investigate how relatively controlled musical changes influence the character of the resulting sound.\n\nThis generator remains a work in progress. Current research is focused on producing more musically meaningful and perceptually diverse stimuli.\n\nNot every generated result is equally useful or pleasant to hear. Many samples currently require filtering, particularly because some combinations can overrepresent harsh, unstable, or unpleasant musical experiences.\n\nTry generating a group of four sounds, listening to their differences, and experimenting with the available harmonic targeting options.'
};
function atlasOnceVisible(target,callback){
  const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting&&e.intersectionRatio>=.35)){observer.disconnect();callback();}},{threshold:[.35]});
  observer.observe(target);return ()=>observer.disconnect();
}
