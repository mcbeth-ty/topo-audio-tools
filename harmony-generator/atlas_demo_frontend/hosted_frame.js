// Community Cloud's same-origin wrapper can leave its app iframe at the
// browser's 150px default. Repair only that collapsed wrapper, never topo.audio.
function atlasHostedFrame(){
  let frame,owner;
  try{
    frame=window.frameElement;owner=window.parent;
    if(!frame||frame.title!=='streamlitApp'||owner.location.origin!==location.origin)return ()=>{};
    if(frame.getBoundingClientRect().height>=owner.innerHeight*.6)return ()=>{};
  }catch(_){return ()=>{};}
  const original=frame.style.height;
  const fit=()=>{
    const fullscreen=[...owner.document.querySelectorAll('a,button')].find(e=>/fullscreen/i.test(e.textContent));
    const bottom=fullscreen?Math.min(owner.innerHeight,fullscreen.getBoundingClientRect().top-8):owner.innerHeight-32;
    frame.style.height=`${Math.max(240,bottom-frame.getBoundingClientRect().top-2)}px`;
  };
  fit();owner.addEventListener('resize',fit);
  return ()=>{owner.removeEventListener('resize',fit);frame.style.height=original;};
}
