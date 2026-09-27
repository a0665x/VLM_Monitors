'use strict';
const el = id => document.getElementById(id);
let sources = [], watching = '', playerKey = '', hlsPlayer = null;
let publisher = null, localStream = null, heartbeat = null, publishing = false, generation = 0, wakeLock = null;
let deviceId;
try {
    deviceId = localStorage.getItem('vlm-camera-client-id');
    if (!/^phone-[a-f0-9-]{36}$/.test(deviceId || '')) { deviceId = 'phone-' + crypto.randomUUID(); localStorage.setItem('vlm-camera-client-id', deviceId); }
    el('client-camera-name').value = localStorage.getItem('vlm-camera-client-name') || i18n.t('手機相機') + ' ' + deviceId.slice(-4);
} catch { deviceId = 'phone-' + crypto.randomUUID(); el('client-camera-name').value = '手機相機'; }
// Independent tabs must not overwrite each other's camera publisher.
deviceId += '-' + crypto.randomUUID().slice(0,8);
async function api(url, data) {
    const controller = new AbortController(); const timer = setTimeout(()=>controller.abort(), 8000);
    try {
        const options = data === undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)};
        const r = await fetch(url, {...options, signal:controller.signal});
        const body = await r.json();
        if (!r.ok || body.success === false) throw new Error(body.error || '服務暫時無法使用');
        return body;
    } finally { clearTimeout(timer); }
}
function changeTab(name) {
    for (const tab of ['watch','publish']) {
        el(tab+'-tab').setAttribute('aria-selected', String(tab===name)); el(tab+'-panel').hidden = tab!==name;
    }
}
el('share-phone').addEventListener('click',()=>{changeTab('publish');el('publish-panel').scrollIntoView({block:'start',behavior:'smooth'});});
for (const name of ['watch','publish']) el(name+'-tab').addEventListener('click',()=>changeTab(name));
el('help-toggle').addEventListener('click',()=>{el('connection-guide').hidden=!el('connection-guide').hidden;el('help-toggle').setAttribute('aria-expanded',String(!el('connection-guide').hidden));});
el('check-connection').addEventListener('click',refresh);
function renderPlayer() {
    if (!el('focused-view').open) return;
    const source = sources.find(s=>s.id===watching);
    if (!source) return;
    const mode = el('playback').value;
    const key = source.id + ':' + mode + ':' + source.ready;
    if (key===playerKey) return;
    playerKey = key;
    if (hlsPlayer) { hlsPlayer.destroy(); hlsPlayer=null; }
    el('viewer').replaceChildren(); el('view-title').textContent = source.label;
    if (source.ready === false) { const p=document.createElement('p'); p.textContent='這台相機尚未提供影像';el('viewer').append(p);i18n.text(el('view-hint'),'請在提供影像的裝置上開始分享，並保持頁面開啟。');return; }
    const path = source.path || (source.is_local ? 'camera' : source.id);
    if (mode==='webrtc') {
        const frame=document.createElement('iframe');frame.src='/proxy/webrtc/'+encodeURIComponent(path)+'/';frame.title=source.label+' · '+i18n.t('即時影像');frame.allow='autoplay; fullscreen';frame.allowFullscreen=true;
        frame.addEventListener('load',()=>{
            try {
                const video=frame.contentDocument.querySelector('video');
                const playing=()=>{if(playerKey===key)i18n.text(el('view-hint'),'正在播放 · WebRTC 即時影像');};
                if(video){video.addEventListener('playing',playing);if(video.readyState>=2)playing();}
            } catch {}
        });
        el('viewer').append(frame);
        i18n.text(el('view-hint'),'WebRTC 正在連線；若一直沒有影像，切換 HLS 相容模式並檢查 Tailscale。');
    } else {
        const video=document.createElement('video');video.autoplay=true;video.muted=true;video.playsInline=true;video.controls=true;el('viewer').append(video);
        const url='/proxy/hls/'+encodeURIComponent(path)+'/index.m3u8';
        if(video.canPlayType('application/vnd.apple.mpegurl')) video.src=url;
        else if(window.Hls && Hls.isSupported()){ hlsPlayer=new Hls();hlsPlayer.loadSource(url);hlsPlayer.attachMedia(video);hlsPlayer.on(Hls.Events.ERROR,(_,d)=>{if(d.fatal)i18n.text(el('view-hint'),'相容播放失敗，請確認來源仍在線，或切回 WebRTC。');}); }
        else i18n.text(el('view-hint'),'此瀏覽器不支援 HLS，請使用 WebRTC。');
        video.addEventListener('playing',()=>i18n.text(el('view-hint'),'正在播放 · HLS 相容模式可能有數秒延遲'));
    }
}
let gallerySignature = '';
function renderGallery() {
    const signature = JSON.stringify(sources.map(s=>[s.id,s.label,s.ready]));
    if (signature===gallerySignature) return;
    gallerySignature=signature;
    el('client-gallery').replaceChildren();
    for (const source of sources) {
        const card=document.createElement('article');card.className='gallery-card';
        if(source.ready!==false){
            const frame=document.createElement('iframe');
            frame.src='/proxy/webrtc/'+encodeURIComponent(source.path || (source.is_local?'camera':source.id))+'/';
            frame.title=source.label+' · '+i18n.t('即時影像');frame.allow='autoplay; fullscreen';frame.allowFullscreen=true;
            card.append(frame);
        } else {const p=document.createElement('p');p.textContent='尚未分享影像';card.append(p);}
        const button=document.createElement('button');button.dataset.sourceId=source.id;button.textContent=source.label+' · '+i18n.t(source.ready===false?'等待分享':'放大觀看');button.dataset.noI18n='';
        button.addEventListener('click',()=>{watching=source.id;el('focused-view').open=true;renderPlayer();el('focused-view').scrollIntoView({block:'start',behavior:'smooth'});});
        card.append(button);el('client-gallery').append(card);
    }
}
el('focused-view').addEventListener('toggle',()=>{
    if(el('focused-view').open)renderPlayer();
    else {if(hlsPlayer){hlsPlayer.destroy();hlsPlayer=null;}el('viewer').replaceChildren();playerKey='';}
});
function renderSources(selectedAI) {
    const list=el('client-sources');list.replaceChildren();
    for(const source of sources){
        const b=document.createElement('button');b.className='source-choice';b.setAttribute('aria-pressed',String(source.id===watching));
        const title=document.createElement('strong');title.textContent=source.label;title.dataset.noI18n='';
        const detail=document.createElement('small');detail.textContent=i18n.t(source.ready===true?'影像在線':source.ready===false?'等待影像':'狀態待確認')+(source.id===selectedAI?' · '+i18n.t('AI 來源'):'');b.append(title,detail);
        b.addEventListener('click',()=>{watching=source.id;el('focused-view').open=true;renderSources(selectedAI);renderPlayer();});list.append(b);
    }
    el('source-count').textContent=sources.filter(s=>s.ready).length+' · '+i18n.t('影像在線');
    el('select-ai').disabled=!sources.find(s=>s.id===watching)?.ready;
}
let refreshing=false;
async function refresh(){
    if(refreshing)return;refreshing=true;
    try{
        const data=await api('/api/network');sources=data.sources;
        i18n.text(el('connection-status'),data.share_ready?'已連上主機 · 私人分享已啟用':'已連上主機 · Tailscale 分享尚未就緒');el('connection-status').classList.remove('error');
        if(!watching || !sources.some(s=>s.id===watching))watching=sources.find(s=>s.ready)?.id || sources[0]?.id || '';
        el('network-engine').textContent=data.backend+' · '+data.model;
        const selected=sources.find(s=>s.id===data.selected_source_id);
        el('ai-status').textContent=i18n.t('AI 來源')+' · '+(selected?.label || i18n.t('未選擇'));
        renderSources(data.selected_source_id);renderGallery();renderPlayer();
        if(!data.media_ready)i18n.text(el('view-hint'),'媒體通道狀態尚未就緒。啟用 Tailscale Serve 後，請在主機執行 ./run.sh local-restart。');
        const status=await api('/api/status');el('client-result').textContent=status.analysis_running?i18n.t('主機正在分析…'):status.last_inference_error || status.last_inference_text || i18n.t('主機尚未產生分析結果。');
    }catch(error){i18n.text(el('connection-status'),'無法連到主機 · 請確認 Tailscale 與主機服務');el('connection-status').classList.add('error');}
    finally{refreshing=false;}
}
el('playback').addEventListener('change',renderPlayer);
el('select-ai').addEventListener('click',async()=>{el('select-ai').disabled=true;try{await api('/api/sources/select',{source_id:watching});await refresh();}catch(e){el('ai-status').textContent=e.message;}finally{el('select-ai').disabled=false;}});
async function register(){await api('/api/sources/register',{source_id:deviceId,label:el('client-camera-name').value.trim()||'手機相機'});}
async function releaseWakeLock(){if(wakeLock){try{await wakeLock.release();}catch{}wakeLock=null;}}
async function keepAwake(){if('wakeLock' in navigator && !document.hidden){try{wakeLock=await navigator.wakeLock.request('screen');}catch{}}}
async function stopPublishing(){
    generation++;publishing=false;el('sharing-banner').hidden=true;el('analyze-phone').hidden=true;clearInterval(heartbeat);heartbeat=null;
    if(publisher){publisher.close();publisher=null;}
    if(localStream){localStream.getTracks().forEach(t=>t.stop());localStream=null;}
    el('client-preview').srcObject=null;el('client-preview').hidden=true;
    el('start-publishing').hidden=false;el('start-publishing').disabled=true;el('stop-publishing').hidden=true;
    for(const id of ['client-camera-name','client-facing','client-microphone'])el(id).disabled=false;
    await releaseWakeLock();
    try{await api('/api/sources/disconnect',{source_id:deviceId});}catch{}
    el('start-publishing').disabled=false;i18n.text(el('publish-message'),'已停止分享，鏡頭與麥克風已關閉。');refresh();
}
el('start-publishing').addEventListener('click',async()=>{
    const current=++generation;el('start-publishing').disabled=true;el('stop-publishing').hidden=false;i18n.text(el('publish-message'),'請允許瀏覽器使用相機…');
    try{
        if(!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)throw new Error('分享相機需要 HTTPS；請使用 QR code 的私人網址。');
        if(!RTCRtpSender.getCapabilities('video')?.codecs.some(c=>c.mimeType.toLowerCase()==='video/h264'))throw new Error('此瀏覽器缺少 H264 相機編碼，請使用新版 Safari 或 Chrome。');
        const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:el('client-facing').value},width:{ideal:1280},height:{ideal:720},frameRate:{ideal:15,max:30}},audio:el('client-microphone').checked});
        if(current!==generation){stream.getTracks().forEach(t=>t.stop());return;}
        localStream=stream;el('client-preview').srcObject=stream;el('client-preview').hidden=false;el('start-publishing').hidden=true;el('stop-publishing').hidden=false;
        for(const id of ['client-camera-name','client-facing','client-microphone'])el(id).disabled=true;
        try{localStorage.setItem('vlm-camera-client-name',el('client-camera-name').value);}catch{}
        i18n.text(el('publish-message'),'鏡頭已開啟，正在建立私人 WebRTC 連線…');
        // Claim the source before WHIP signaling; the server checks its owner.
        await register();
        if(current!==generation)return;
        publisher=new MediaMTXWebRTCPublisher({url:new URL('/proxy/webrtc/'+deviceId+'/whip',location.origin).href,stream,videoCodec:'h264/90000',videoBitrate:1500,audioCodec:'opus/48000',audioBitrate:32,audioVoice:true,
            onConnected:async()=>{if(current!==generation)return;publishing=true;el('sharing-banner').hidden=false;try{await register();if(current!==generation)return;clearInterval(heartbeat);heartbeat=setInterval(()=>{if(publishing)register().catch(()=>{});},5000);i18n.text(el('publish-message'),'正在分享 · 其他手機已可在相機清單選擇這台裝置');keepAwake();refresh();const auth=await window.accountReady;if(current===generation&&auth.user?.role==='admin')el('analyze-phone').hidden=false;}catch(e){i18n.text(el('publish-message'),'影像已連接，但來源登記失敗，請停止後重試。');}},
            onError:err=>{if(current!==generation)return;publishing=false;el('analyze-phone').hidden=true;el('sharing-banner').hidden=true;clearInterval(heartbeat);i18n.text(el('publish-message'),'影像連線中斷，正在重試。請檢查 Tailscale；');}});
        stream.getTracks().forEach(track=>track.addEventListener('ended',()=>{if(current===generation)stopPublishing();}));
    }catch(error){if(current!==generation)return;await stopPublishing();i18n.text(el('publish-message'),error.name==='NotAllowedError'?'相機權限未允許。請在瀏覽器設定允許相機，再按開始。':error.message);}
});
el('analyze-phone').addEventListener('click',async()=>{el('analyze-phone').disabled=true;try{await api('/api/sources/select',{source_id:deviceId});i18n.text(el('publish-message'),'Camera selected. Start analysis from the host dashboard.');}catch(e){el('publish-message').textContent=e.message;}finally{el('analyze-phone').disabled=false;}});
el('stop-publishing').addEventListener('click',stopPublishing);
window.addEventListener('pagehide',()=>{generation++;publishing=false;el('sharing-banner').hidden=true;clearInterval(heartbeat);publisher?.close();localStream?.getTracks().forEach(t=>t.stop());fetch('/api/sources/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_id:deviceId}),keepalive:true}).catch(()=>{});});
document.addEventListener('visibilitychange',()=>{if(publishing && !document.hidden)keepAwake();if(publishing && document.hidden)i18n.text(el('publish-message'),'頁面已移到背景，手機可能暫停相機。回到前景後請確認其他装置仍可觀看。');});
if(new URLSearchParams(location.search).get('mode')==='publish')changeTab('publish');
refresh();setInterval(refresh,4000);

document.addEventListener('language-changed',()=>{
 document.querySelectorAll('#client-gallery button[data-source-id]').forEach(button=>{const source=sources.find(s=>s.id===button.dataset.sourceId);if(source)button.textContent=source.label+' · '+i18n.t(source.ready===false?'等待分享':'放大觀看');});
 refresh();
});
