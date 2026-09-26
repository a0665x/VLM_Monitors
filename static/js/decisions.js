/* Parallel decisions use candidate scores, never invented model percentages. */
(() => {
  const labels = {person:'有人出現',baby:'寶寶哭鬧',fire:'火焰警示',smoke:'煙霧警示',pet:'寵物活動'};
  const outcomes = ['present','absent','unknown'];
  const outcomeLabels = {present:'Present',absent:'Absent',unknown:'Unknown'};
  const colors = ['#76e5c3','#79aefc','#f3c76b'];
  let status, settings, pending=false, renderKey='', panel;
  const t = key => window.i18n.t(key);
  const node = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  async function requestSettings(next) {
    if(pending)return;
    pending=true;
    const save=document.getElementById('decision-save');
    if(save)save.disabled=true;
    const modeSelect=document.getElementById('decision-mode');if(modeSelect)modeSelect.disabled=true;
    try {
      const response=await fetch('/api/settings/decisions',next?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)}:{});
      const data=await response.json();if(!response.ok)throw new Error(data.error);
      settings=data.settings;
      const mode=document.getElementById('decision-mode');if(mode)mode.value=settings.mode;
      const msg=document.getElementById('decision-service-status');
      if(msg)i18n.text(msg,next?'Analysis mode updated.':data.service.ready?'Decision service ready':'Start the decision service: ./run.sh decision-up');
      syncCards();
      if(next && typeof loadStatus==='function')loadStatus();
    } catch(error) {
      if(modeSelect&&settings)modeSelect.value=settings.mode;
      const msg=document.getElementById('decision-service-status');if(msg)i18n.text(msg,error.message);
      if(typeof showToast==='function')showToast(t(error.message),'error');
    } finally {pending=false;if(save)save.disabled=false;if(modeSelect)modeSelect.disabled=false;}
  }
  function syncCards() {
    const active=settings?.mode==='parallel_decision';
    document.body.classList.toggle('parallel-decisions',active);
    document.querySelectorAll('.scenario-card').forEach(card=>{
      if(active)card.setAttribute('aria-pressed',String(settings.scenarios.includes(card.dataset.scenario)));
      card.disabled=active && card.dataset.scenario==='custom';
    });
    if(!active && typeof markScenario==='function')markScenario(appliedPrompt);
    if(panel)panel.hidden=!active;
    const hint=document.getElementById('scenario-mode-hint');if(hint)i18n.text(hint,active?'Multiple scenarios · select one or more':'Single scenario · select one card');
  }
  function chart(canvas, results, selected) {
    const width=Math.max(300,Math.min(900,panel.clientWidth||window.innerWidth-80)),height=245,left=36,right=12,top=28,bottom=190;
    canvas.width=width*2;canvas.height=height*2;
    const c=canvas.getContext('2d');c.scale(2,2);
    c.font='11px system-ui';c.fillStyle='#a5bbc4';c.strokeStyle='#30434d';c.lineWidth=1;
    c.fillText(t('Score (%)'),0,12);
    for(const value of [0,.25,.5,.75,1]){const y=bottom-value*(bottom-top);c.beginPath();c.moveTo(left,y);c.lineTo(width-right,y);c.stroke();c.fillText(String(Math.round(value*100)),3,y+4);}
    const slot=(width-left-right)/selected.length,bar=Math.min(70,slot*.6);
    selected.forEach((id,index)=>{
      const x=left+slot*(index+.5),probability=results?.[id]?.probabilities?.present;
      if(typeof probability==='number'){
        const h=probability*(bottom-top);c.fillStyle=colors[0];c.fillRect(x-bar/2,bottom-h,bar,Math.max(1,h));
        c.textAlign='center';c.fillStyle='#edf7f6';c.fillText((probability*100).toFixed(1)+'%',x,Math.max(top-7,bottom-h-7));
      }else{c.textAlign='center';c.fillStyle='#a5bbc4';c.fillText('—',x,bottom-12);}
      c.fillStyle='#c7d8de';c.textAlign='center';
      const label=t(labels[id]),words=label.includes(' ')?label.split(' '):[...label];let line='',lines=[];
      for(const word of words){const next=line+(line&&label.includes(' ')?' ':'')+word;if(c.measureText(next).width>slot-4&&line){lines.push(line);line=word;}else line=next;}if(line)lines.push(line);
      lines.slice(0,3).forEach((text,i)=>c.fillText(text,x,bottom+18+i*13));
    });
  }
  function render(data, force=false) {
    status=data;settings=data.decision_settings||settings;syncCards();
    if(settings?.mode!=='parallel_decision'||!panel)return;
    const current=data.decision_result;
    const key=JSON.stringify([data.analysis_epoch,current?.frame_id,data.analysis_running,data.last_inference_error,i18n.language,settings]);
    // Override legacy binary status: no all-clear label for probabilistic results.
    const badge=document.getElementById('status-text');
    if(badge)i18n.text(badge,data.analysis_running?'正在分析':data.last_inference_error?'分析失敗':current?'Scores ready':'尚未分析');
    if(key===renderKey&&!force)return;renderKey=key;
    panel.replaceChildren();
    panel.append(node('h3',t('Scenario scores')),
      node('p',t('Experimental · uncalibrated candidate scores · notifications off'),'decision-note'));
    const state=node('p',data.analysis_running?t('正在分析'):data.last_inference_error?t('Analysis unavailable. Try again.'):current?`${current.vision_ms} ms ${t('Vision')} + ${current.decision_ms} ms ${t('Classification')} · ${current.total_ms} ms ${t('Total')}`:t('Run one analysis to see scores.'),'decision-note');
    state.setAttribute('role','status');panel.append(state);
    if(current)panel.append(node('p',`${current.decision_model} · ${new Date(current.timestamp).toLocaleTimeString(i18n.language)}`,'decision-note'));
    panel.append(node('p',t('Each bar shows the probability of that event being present. — means insufficient evidence.'),'decision-note'));
    const canvas=node('canvas',undefined,'decision-distribution');canvas.setAttribute('role','img');
    canvas.setAttribute('aria-label',settings.scenarios.map(id=>t(labels[id])+': '+(current?.results[id]?.probabilities?(100*current.results[id].probabilities.present).toFixed(1)+'%':t('Insufficient visual evidence'))).join('; '));
    panel.append(canvas);chart(canvas,current?.results,settings.scenarios);
    const details=node('details');details.append(node('summary',t('Full distribution')));
    const table=node('table',undefined,'decision-table'),head=node('tr');
    [t('Scenario'),...outcomes.map(x=>t(outcomeLabels[x]))].forEach(label=>head.append(node('th',label)));table.append(head);
    for(const id of settings.scenarios){const row=node('tr');row.append(node('td',t(labels[id])));for(const outcome of outcomes)row.append(node('td',current?.results[id]?.probabilities?(100*current.results[id].probabilities[outcome]).toFixed(1)+'%':'—'));table.append(row);}
    details.append(table);panel.append(details);

  }
  document.addEventListener('DOMContentLoaded',()=>{
    const host=document.querySelector('.scenario-workspace');
    panel=node('section',undefined,'decision-panel');panel.id='decision-panel';panel.hidden=true;
    if(host){
      host.insertBefore(panel,document.getElementById('prompt-workspace'));
      const hint=node('p',undefined,'decision-note');hint.id='scenario-mode-hint';host.insertBefore(hint,host.querySelector('.scenario-grid'));
      document.querySelector('.scenario-grid').addEventListener('click',async event=>{
        if(settings?.mode!=='parallel_decision')return;
        const card=event.target.closest('.scenario-card');if(!card)return;
        event.preventDefault();event.stopImmediatePropagation();
        const id=card.dataset.scenario;if(!labels[id]||pending)return;
        const selected=settings.scenarios.includes(id)?settings.scenarios.filter(x=>x!==id):[...settings.scenarios,id];
        if(!selected.length){showToast(t('Keep at least one scenario selected.'),'error');return;}
        await requestSettings({mode:'parallel_decision',scenarios:selected});
      },true);
      document.getElementById('decision-mode').addEventListener('change',event=>requestSettings({mode:event.target.value,scenarios:settings?.scenarios||Object.keys(labels)}));
      document.getElementById('decision-save').addEventListener('click',()=>requestSettings({mode:document.getElementById('decision-mode').value,scenarios:settings?.scenarios||Object.keys(labels)}));
      document.getElementById('decision-check').addEventListener('click',()=>requestSettings());
      requestSettings();
      document.addEventListener('monitor-status',event=>render(event.detail));
    }else{
      document.querySelector('.optional-ai')?.append(panel);
      const poll=()=>fetch('/api/status').then(r=>r.json()).then(render).catch(()=>{});poll();setInterval(poll,4000);
    }
    document.addEventListener('language-changed',()=>{if(status)render(status,true);});
    let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(status)render(status,true);},150);});
  });
})();
