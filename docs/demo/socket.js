// Documentation-only stand-in: no Socket.IO connection to any host.
window.io=()=>({on(name,callback){if(name==='connect')setTimeout(callback,0);},emit(){}});
