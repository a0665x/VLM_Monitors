const scenarios = [
    ['person', '01', '有人出現', '偵測畫面中的人', 'Is there a person visible in the image?'],
    ['baby', '02', '寶寶哭鬧', '僅依表情與姿勢判斷', 'Is a baby visibly showing signs of crying or distress? Judge only visible facial expressions and body posture, not sound.'],
    ['fire', '03', '火焰警示', '留意可見火焰', 'Are there visible flames or a fire in the image?'],
    ['smoke', '04', '煙霧警示', '留意可見煙霧', 'Is there visible smoke in the image? Distinguish smoke from clouds, steam, and low lighting when possible.'],
    ['pet', '05', '寵物活動', '貓狗是否進入畫面', 'Is a cat or dog visible in the image?'],
    ['custom', '＋', '自訂情境', '寫下你想觀察的行為', null]
];
let appliedPrompt = '';
let engineRequest = 0;
function markScenario(text) {
    appliedPrompt = text;
    const match = scenarios.find(s => s[4] === text)?.[0] || 'custom';
    document.querySelectorAll('.scenario-card').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.scenario === match)));
    setText('prompt-state', i18n.t('已套用') + ' · ' + i18n.t(scenarios.find(s => s[0] === match)[2]));
}
let engineBusy = false;
let activeEngine = null;
function setEngineBusy(value) {
    engineBusy=value;
    document.getElementById('engine-select').disabled=value;
    document.getElementById('engine-model').disabled=value;
}
function restoreEngineSelection() {
    if(!activeEngine)return;
    document.getElementById('engine-select').value=activeEngine.backend;
    const select=document.getElementById('engine-model');
    if(!Array.from(select.options||[]).some(option=>option.value===activeEngine.model))select.replaceChildren(new Option(activeEngine.model,activeEngine.model));
    select.value=activeEngine.model;
}
async function saveEngineSelection() {
    const backend=document.getElementById('engine-select').value;
    const model=document.getElementById('engine-model').value;
    if(activeEngine?.backend===backend && activeEngine?.model===model)return;
    setText('engine-status','Saving…');
    const r=await fetch('/api/settings/engine',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({backend,model})});
    const data=await r.json();if(!r.ok)throw new Error(data.error);
    activeEngine={backend:data.backend,model:data.model};
    setText('engine-status','已儲存，下一次分析將使用此引擎。');
    loadVisionModels();loadStatus();
}
async function refreshEngine(apply=false) {
    if(engineBusy)return;
    const requestId=++engineRequest;
    const backend=document.getElementById('engine-select').value;
    const select=document.getElementById('engine-model');
    setEngineBusy(true);setText('engine-status','正在連線…');
    try {
        const r=await fetch('/api/settings/engine?backend='+backend);
        const data=await r.json();if(!r.ok)throw new Error(data.error);
        if(requestId!==engineRequest)return;
        activeEngine={backend:data.current_backend,model:data.current_model};
        if(!data.available)throw new Error('尚未就緒，請先啟動引擎並載入視覺模型。');
        select.replaceChildren(...data.models.map(model=>new Option(model,model)));
        if(data.current_backend===backend && data.models.includes(data.current_model))select.value=data.current_model;
        setText('engine-status','Settings saved automatically');
        if(apply)await saveEngineSelection();
    } catch(error) {
        restoreEngineSelection();setText('engine-status',error.message);
    } finally {setEngineBusy(false);}
}
async function changeEngineModel() {
    if(engineBusy)return;
    setEngineBusy(true);
    try {await saveEngineSelection();}
    catch(error){restoreEngineSelection();setText('engine-status',error.message);}
    finally {setEngineBusy(false);}
}
async function refreshShare() {
    const qr = document.getElementById('share-qr');
    const link = document.getElementById('share-link');
    qr.hidden = link.hidden = true;
    try {
        const r = await fetch('/api/share'); const data = await r.json();
        setText('share-message', data.message);
        if (data.ready) {
            qr.src = '/api/share/qr.svg?t=' + Date.now(); qr.hidden = false;
            link.href = data.url; link.textContent = data.url; link.hidden = false;
        }
    } catch { setText('share-message', '無法讀取分享狀態，請重新檢查。'); }
}
document.addEventListener('DOMContentLoaded', async () => {
    const main = document.querySelector('#situation-room-view > .video-panel');
    const workspace = document.createElement('section'); workspace.className = 'scenario-workspace';
    workspace.innerHTML = '<div class="section-heading"><div><p class="eyebrow">DETECTION SCENARIOS</p><h2>你想留意什麼？</h2></div><span class="helper-copy">點選卡片即可切換判斷條件</span></div><div class="scenario-grid"></div><p class="scenario-note">影像分析可能誤判。哭鬧情境只看畫面；聲音音量偵測可在設定另行開啟。</p><div id="prompt-workspace"><div class="section-heading"><h3>提示詞</h3><span id="prompt-state" role="status">讀取中…</span></div></div>';
    main.append(workspace);
    for (const [id, number, title, subtitle, prompt] of scenarios) {
        const button = document.createElement('button'); button.className = 'scenario-card'; button.dataset.scenario = id; button.setAttribute('aria-pressed','false');
        button.innerHTML = `<span class="scenario-number">${number}</span><strong>${title}</strong><small>${subtitle}</small>`;
        button.addEventListener('click', async () => {
            const input = document.getElementById('prompt-textarea');
            if (prompt === null) { input.focus(); input.scrollIntoView({block:'center', behavior:'smooth'}); return; }
            document.querySelectorAll('.scenario-card').forEach(b => b.disabled = true);
            input.value = prompt;
            await applyPromptText(prompt);
            document.querySelectorAll('.scenario-card').forEach(b => b.disabled = false);
        });
        workspace.querySelector('.scenario-grid').append(button);
    }
    const prompt = document.getElementById('prompt-settings');
    const oldPromptSection = prompt.parentElement;
    document.getElementById('prompt-workspace').append(prompt);
    prompt.classList.add('always-open'); oldPromptSection.remove();
    document.getElementById('advanced-settings').append(document.querySelector('.settings-accordion'));
    const soundToggle = document.getElementById('sound-detection-toggle').closest('.toggle-group');
    document.getElementById('device-settings').append(soundToggle, document.getElementById('sound-info'));
    const controls = document.querySelector('.analysis-controls');
    const action = document.createElement('button'); action.className = 'btn btn-primary'; action.id = 'monitor-toggle'; action.textContent = '開始持續監控';
    action.addEventListener('click', () => { const toggle = document.getElementById('auto-analysis-toggle'); toggle.checked = !toggle.checked; toggle.dispatchEvent(new Event('change')); });
    const autoGroup = document.getElementById('auto-analysis-toggle').closest('.toggle-group'); autoGroup.hidden = true;
    controls.insertBefore(action, controls.children[1]);
    const summary = document.createElement('p'); summary.id = 'monitor-summary'; summary.className = 'helper-copy'; summary.textContent = '尚未開始持續監控'; controls.append(summary);
    document.querySelector('.control-panel').prepend(controls);
    // The model selector in the settings dialog owns engine and model changes together.
    document.getElementById('model-select').closest('.form-group').hidden = true;
    document.getElementById('prompt-textarea').addEventListener('input', e => setText('prompt-state', e.target.value === appliedPrompt ? '已套用' : 'Finish editing to save'));
    document.getElementById('prompt-textarea').addEventListener('change',e=>applyPromptText(e.target.value));
    document.addEventListener('prompt-applied', e => markScenario(e.detail));
    document.addEventListener('monitor-status', e => {
        const d = e.detail;
        i18n.text(action, d.auto_analyze ? '暫停持續監控' : '開始持續監控');
        action.classList.toggle('monitor-active', !!d.auto_analyze);
        setText('monitor-summary', `${d.inference_backend || 'ollama'} · ${d.analysis_interval ?? 5}s · ${i18n.t(d.auto_analyze ? '持續監控中' : '已暫停')}`);
    });
    document.getElementById('settings-open').addEventListener('click',()=>window.navigateHost('settings'));
    document.getElementById('share-open').addEventListener('click',()=>window.navigateHost('connect'));
    document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => document.getElementById(b.dataset.close).close()));
    document.getElementById('share-refresh').addEventListener('click', refreshShare);
    document.getElementById('engine-select').addEventListener('change',()=>refreshEngine(true));
    document.getElementById('engine-model').addEventListener('change',changeEngineModel);
    try { const r = await fetch('/api/prompt/current'); const d = await r.json(); markScenario(d.text); } catch {}
    loadStatus();
});

document.addEventListener('language-changed',()=>{
 const input=document.getElementById('prompt-textarea');
 if(input.value===appliedPrompt)markScenario(appliedPrompt);
 else setText('prompt-state','Finish editing to save');
 loadStatus();
});
