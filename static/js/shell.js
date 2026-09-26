window.navigateHost = async function(page) {
    if(!['monitor','connect','settings'].includes(page))page='monitor';
    document.body.dataset.page=page;
    document.getElementById('settings-dialog').hidden=page!=='settings';
    document.querySelectorAll('[data-page-link]').forEach(b=>{if(b.dataset.pageLink===page)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    if(location.hash!=='#'+page) history.replaceState(null,'','#'+page);
    if(page==='connect')updateConnectEntry();
    if(page==='settings'){
        try{const r=await fetch('/api/service');const d=await r.json();document.getElementById('engine-select').value=d.inference_backend;}catch{}
        refreshEngine();
    }
};
document.addEventListener('DOMContentLoaded',()=>{
    document.querySelectorAll('[data-page-link]').forEach(b=>b.addEventListener('click',()=>navigateHost(b.dataset.pageLink)));
    window.addEventListener('hashchange',()=>navigateHost(location.hash.slice(1)));
    navigateHost(location.hash.slice(1)||'monitor');
});
