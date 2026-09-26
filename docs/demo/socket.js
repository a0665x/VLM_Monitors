// Documentation-only status updates from the isolated fixture server.
window.io=()=>({on(name,callback){if(name==='connect')setTimeout(callback,0);if(name==='status_update'){const poll=()=>fetch('/api/status').then(r=>r.json()).then(callback);poll();setInterval(poll,2000);}},emit(){}});
