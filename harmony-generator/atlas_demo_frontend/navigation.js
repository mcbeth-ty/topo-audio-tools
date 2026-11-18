// One fixed, demo-only navigator; independent of fragment updates and scrolling.
function atlasSectionNav(){
  const host=document.createElement('div');host.className='atlas-section-nav-host';
  Object.assign(host.style,{position:'fixed',top:'clamp(80px,12vh,120px)',right:'clamp(12px,3vw,48px)',zIndex:'1000'});
  const shadow=host.attachShadow({mode:'open'});
  const style=document.createElement('style');style.textContent=`
    nav {display:flex;flex-direction:column;gap:2px;padding:7px 9px;
      background:#0a0a0ab8;border:1px solid #ffffff30;border-radius:3px;
      backdrop-filter:blur(5px);font:9px/1.5 Arial,Helvetica,sans-serif;letter-spacing:.08em}
    .index-title {color:#aaa;font-size:8px;padding:2px 5px 5px;border-bottom:1px solid #ffffff20;margin-bottom:2px}
    button {border:0;background:none;color:#888;text-align:left;font:inherit;
      letter-spacing:inherit;padding:3px 5px;cursor:pointer}
    button:hover,button[aria-current="location"] {color:#fff;background:#ffffff0c}
    button:focus-visible {outline:1px solid #bbb;outline-offset:1px}
  `;
  const nav=document.createElement('nav');nav.setAttribute('aria-label','Affective Atlas sections');
  const title=document.createElement('div');title.className='index-title';title.textContent='INDEX';nav.append(title);
  const sections=[['MODELS','Affective Atlas'],['ARRANGE','Arrange'],['GENERATE','Ambient Generator']];
  const heading=title=>[...document.querySelectorAll('h1,h2')].find(e=>e.textContent.trim()===title);
  const buttons=sections.map(([label,title],index)=>{
    const button=document.createElement('button');button.textContent=`${String(index+1).padStart(2,'0')} / ${label}`;
    button.onclick=()=>heading(title)?.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});
    nav.append(button);return button;
  });
  shadow.append(style,nav);document.body.append(host);
  let frame=null;
  const update=()=>{
    frame=null;let active=0;
    sections.forEach(([,title],i)=>{if(heading(title)?.getBoundingClientRect().top<=innerHeight*.3)active=i;});
    const scroller=document.querySelector('[data-testid=stMain]')||document.scrollingElement;
    if(scroller.scrollTop>0&&scroller.scrollTop+scroller.clientHeight>=scroller.scrollHeight-3&&heading('Ambient Generator')?.getBoundingClientRect().top<innerHeight)active=2;
    buttons.forEach((button,i)=>{if(i===active)button.setAttribute('aria-current','location');else button.removeAttribute('aria-current');});
  };
  const schedule=()=>{if(frame===null)frame=requestAnimationFrame(update);};
  const observer=new ResizeObserver(schedule);observer.observe(document.querySelector('[data-testid=stMainBlockContainer]')||document.body);
  document.addEventListener('scroll',schedule,true);window.addEventListener('resize',schedule);update();
  return ()=>{observer.disconnect();document.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',schedule);if(frame!==null)cancelAnimationFrame(frame);host.remove();};
}
