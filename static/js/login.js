(async()=>{
 const el=id=>document.getElementById(id),show=(id,key)=>i18n.text(el(id),key);let info;
 try{info=await(await fetch('/auth/status')).json();}catch{show('message','Cannot connect to host.');return;}
 if(info.user){location.replace('/');return;}
 el('google').hidden=!info.google_enabled||info.setup_required;
 if(info.setup_required){show('title','Set up your host');show('intro','Run ./run.sh account-setup on the host to get the setup code. Create your administrator account below.');el('code-label').hidden=false;el('password').minLength=6;el('password').autocomplete='new-password';show('submit','Create administrator');}
 if(location.search.includes('error=google'))show('message','Google sign-in could not be completed. Ask the host administrator to check account access and OAuth settings.');
 el('form').addEventListener('submit',async event=>{event.preventDefault();el('submit').disabled=true;try{
 const r=await fetch(info.setup_required?'/auth/setup':'/auth/login',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf},body:JSON.stringify({code:el('code').value,email:el('email').value,password:el('password').value})});const data=await r.json();if(!r.ok)throw Error(data.error||'Sign-in failed');location.replace('/');
 }catch(error){show('message',error.message);el('submit').disabled=false;}});
})();
