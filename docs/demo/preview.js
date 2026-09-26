// Loaded only by scripts/docs_preview.py, never by the running application.
if(typeof getWebRtcBaseUrl==='function')getWebRtcBaseUrl=()=>location.origin+'/proxy/webrtc';
document.addEventListener('DOMContentLoaded',()=>{
 const banner=document.createElement('aside');banner.className='docs-demo-banner';banner.textContent='DOCUMENTATION DEMO · Generated images & illustrative scores · No live inference';document.body.prepend(banner);
 document.querySelectorAll('.system-stats').forEach(el=>el.hidden=true);
 if(typeof loadSources==='function')loadSources();
 const optional=document.querySelector('.optional-ai');if(optional&&location.search.includes('scores'))optional.open=true;
 const preview=document.getElementById('client-preview');if(preview){preview.poster='/docs/assets/scenario-fire-smoke.png';preview.hidden=false;}
});
// Never ask for real camera/microphone permission from a documentation demo.
document.addEventListener('click',event=>{
 if(event.target.closest('#start-publishing')){
  event.preventDefault();event.stopImmediatePropagation();
  document.getElementById('publish-message').textContent='Documentation demo: synthetic preview only. No camera is started.';
 }
},true);
