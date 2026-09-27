// Same-origin live playback with recovery after host/camera restarts.
(()=>{
 function attachHls(video,url){
  let hls,timer,closed=false;
  const message=document.createElement('span');message.className='stream-feedback';message.setAttribute('role','status');video.parentElement.append(message);
  function note(key){message.hidden=false;window.i18n?.text(message,key);}
  function retry(){if(closed||timer)return;note('Reconnecting camera…');timer=setTimeout(()=>{timer=null;start();},3000);}
  function start(){if(closed)return;hls?.destroy();hls=null;note('Connecting camera…');
   if(!window.Hls?.isSupported()&&video.canPlayType('application/vnd.apple.mpegurl')){video.src=url;video.load();video.play().catch(()=>note('Tap play to watch'));}
   else if(window.Hls?.isSupported()){hls=new Hls({lowLatencyMode:true,backBufferLength:10,maxBufferLength:15});hls.on(Hls.Events.MANIFEST_PARSED,()=>video.play().catch(()=>note('Tap play to watch')));hls.on(Hls.Events.ERROR,(_,error)=>{if(error.fatal)retry();});hls.loadSource(url);hls.attachMedia(video);}
   else note('This browser cannot play this stream.');
  }
  const playing=()=>{clearTimeout(timer);timer=null;message.hidden=true;};video.addEventListener('playing',playing);video.addEventListener('error',retry);start();
  return ()=>{closed=true;clearTimeout(timer);hls?.destroy();video.removeEventListener('playing',playing);video.removeEventListener('error',retry);video.removeAttribute('src');video.load();message.remove();};
 }
 function watchWebRtc(frame,url){let lastProgress=Date.now(),lastTime=-1,cleanup;const timer=setInterval(()=>{
  if(!frame.isConnected){clearInterval(timer);return;}
  try{const video=frame.contentDocument?.querySelector('video');if(video&&video.currentTime!==lastTime&&video.readyState>=2){lastTime=video.currentTime;lastProgress=Date.now();}}catch{}
  if(Date.now()-lastProgress<15000)return;
  clearInterval(timer);const video=document.createElement('video');video.className='source-video';video.autoplay=true;video.muted=true;video.playsInline=true;video.controls=true;video.title=frame.title;frame.replaceWith(video);cleanup=attachHls(video,url);
 },3000);return ()=>{clearInterval(timer);cleanup?.();};}
 window.livePlayer={attachHls,watchWebRtc};
})();
