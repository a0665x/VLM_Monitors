(()=>{
 const el=id=>document.getElementById(id),t=key=>window.i18n.t(key);let signature='',dirty=false;
 const names={person:'Person',baby:'Baby distress',fire:'Fire',smoke:'Smoke',pet:'Pets',custom:'Custom'};
 async function request(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
 function message(text){el('archive-message').textContent=t(text);}
 async function refresh(){
  try{
   const data=await request('/api/archive');
   if(!dirty){el('archive-enabled').checked=!!data.config?.enabled;if(data.config)el('archive-source').value=data.config.source_id;}
   el('retention').textContent=`${t('Retention')}: ${data.retention_days} ${t('days')}`;
   el('usage-meter').value=Math.min(100,100*data.usage.bytes/data.quota_bytes);
   el('usage').textContent=`${data.usage.n} ${t('saved frames')} · ${(data.usage.bytes/1048576).toFixed(1)} / ${(data.quota_bytes/1048576).toFixed(0)} MB`;
   if(data.error)message(data.error);else if(data.storage?.paused)message('Host disk space is low. Recording paused.');
   el('retention').textContent+=` · ${t('Host storage')}: ${(data.storage.used_bytes/1073741824).toFixed(2)} / ${(data.storage.quota_bytes/1073741824).toFixed(0)} GB`;
   const days=data.days.map(d=>d.day).join(',');if(el('export-day').dataset.days!==days){const previous=el('export-day').value;el('export-day').replaceChildren();data.days.forEach(d=>el('export-day').add(new Option(`${d.day} · ${d.frames} ${t('frames')}`,d.day)));if(data.days.some(d=>d.day===previous))el('export-day').value=previous;el('export-day').dataset.days=days;}
   el('export-button').disabled=!data.days.length||data.job?.state==='working';
   el('export-status').textContent=t(data.job?.state==='working'?'Creating video…':data.job?.state==='ready'?'Video ready':data.job?.state==='error'?'Video export failed':'');el('downloads').hidden=data.job?.state!=='ready';
   const key=JSON.stringify([data.events,i18n.language]);if(key!==signature){signature=key;el('timeline').replaceChildren();
    if(!data.events.length){const p=document.createElement('p');p.textContent=t('No saved events yet.');el('timeline').append(p);}
    for(const event of data.events){const item=document.createElement('article');item.className='timeline-event';if(event.frame_id){const img=document.createElement('img');img.src='/api/archive/frame/'+encodeURIComponent(event.frame_id);img.alt=t('Event snapshot');img.loading='lazy';img.onerror=()=>img.remove();item.append(img);}const body=document.createElement('div'),time=document.createElement('time'),title=document.createElement('h3'),tags=document.createElement('div');time.dateTime=new Date(event.ts*1000).toISOString();time.textContent=new Date(event.ts*1000).toLocaleString(i18n.language);title.textContent=event.source_id;tags.className='event-tags';event.categories.forEach(id=>{const tag=document.createElement('span');tag.textContent=t(names[id]||id);tags.append(tag);});body.append(time,title,tags);item.append(body);el('timeline').append(item);}
   }
  }catch(error){message(error.message);}
 }
 el('recording-form').addEventListener('input',()=>dirty=true);
 el('recording-form').addEventListener('submit',async e=>{e.preventDefault();try{await request('/api/archive/config',{source_id:el('archive-source').value,enabled:el('archive-enabled').checked});dirty=false;message('Saved');await refresh();}catch(error){message(error.message);}});
 el('export-form').addEventListener('submit',async e=>{e.preventDefault();el('export-button').disabled=true;try{await request('/api/archive/export',{day:el('export-day').value});await refresh();}catch(error){message(error.message);el('export-button').disabled=false;}});
 request('/api/network').then(data=>{data.sources.forEach(s=>el('archive-source').add(new Option(s.label,s.id)));return refresh();}).catch(error=>message(error.message));
 setInterval(refresh,5000);document.addEventListener('language-changed',refresh);
})();
