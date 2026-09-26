// Shared, visible connection entry on the host and every client page.
async function updateConnectEntry() {
    const status = document.querySelectorAll('[data-connect-status]');
    try {
        const response = await fetch('/api/share', {cache:'no-store'});
        if (!response.ok) throw new Error();
        const data = await response.json();
        document.querySelectorAll('[data-connect-qr]').forEach(img => { img.hidden = !data.ready; if(data.ready) img.src='/api/share/qr.svg?t='+Date.now(); });
        document.querySelectorAll('[data-connect-placeholder]').forEach(p=>{p.hidden=!!data.ready;i18n.text(p,'完成主機連線後，這裡會顯示 QR code。');});
        document.querySelectorAll('[data-connect-link]').forEach(a=>{a.hidden=!data.ready;if(data.ready)a.href=data.url;});
        status.forEach(p=>i18n.text(p,data.ready?'✓ 主機已就緒，可以掃碼加入':data.message));
    } catch { status.forEach(p=>i18n.text(p,'暫時無法確認主機，請按重新檢查。')); }
}
document.addEventListener('DOMContentLoaded',()=>{
    document.querySelectorAll('[data-connect-refresh]').forEach(b=>b.addEventListener('click',updateConnectEntry));
    document.getElementById('invite-open')?.addEventListener('click',()=>{document.getElementById('invite-dialog').showModal();updateConnectEntry();});
    document.getElementById('invite-close')?.addEventListener('click',()=>document.getElementById('invite-dialog').close());
    updateConnectEntry();
});
