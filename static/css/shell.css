// Read session/CSRF before API mutations. Cookies remain HttpOnly.
(()=>{
 const original=window.fetch.bind(window);
 window.accountReady=original('/auth/status').then(r=>r.json());
 window.fetch=async(input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  const method=(options.method||'GET').toUpperCase();
  if(url.origin===location.origin&&!['GET','HEAD','OPTIONS'].includes(method)){
   const auth=await window.accountReady;const headers=new Headers(options.headers);headers.set('X-CSRF-Token',auth.csrf);options={...options,headers};
  }
  const response=await original(input,options);
  if(response.status===401&&url.origin===location.origin)location.assign('/login?next='+encodeURIComponent(location.pathname+location.search+location.hash));
  return response;
 };
 document.addEventListener('DOMContentLoaded',async()=>{
  const auth=await window.accountReady;if(!auth.user)return;
  const area=document.querySelector('.sidebar-bottom')||document.querySelector('.client-footer');if(!area)return;
  const name=document.createElement('p');name.textContent=auth.user.name;name.dataset.noI18n='';
  const archive=document.createElement('a');archive.href='/archive';archive.textContent='Recordings';archive.className='quiet';
  const logout=document.createElement('button');logout.textContent='Sign out';logout.className='quiet';logout.onclick=async()=>{await fetch('/auth/logout',{method:'POST'});location.assign('/login');};
  area.append(name,logout);
  const navigation=document.querySelector('.app-sidebar nav');if(navigation){archive.className='sidebar-link';navigation.append(archive);}else area.append(archive);
  if(auth.google_enabled){const link=document.createElement('a');link.href='/auth/google';link.textContent='Link Google account';area.append(link);}
  if(window.i18n){i18n.text(archive,'Recordings');i18n.text(logout,'Sign out');}
 });
})();
