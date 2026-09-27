(function(){
    const languages=['en','zh-TW','ja','ko'];
    let language='en';try{const saved=localStorage.getItem('vlm-language');if(languages.includes(saved))language=saved;}catch{}
    const catalog=new Map();
    for(const row of window.UI_TRANSLATIONS) {if(!catalog.has(row[0]))catalog.set(row[0],row);catalog.set(row[1],row);if(row[4])catalog.set(row[4],row);}
    const entries=new Map();
    const skip='script,style,textarea,code,[data-no-i18n],#prompt-history,#model-select,#engine-model,.source-tile-title,.source-stream-overlay-text,#explanation-text,#client-result,#view-title,#inference-model,#selected-source-label,#network-engine';
    function t(key){const row=catalog.get(String(key));return row?row[languages.indexOf(language)]:String(key??'');}
    function text(element,key){if(!element)return;entries.set(element,String(key??''));element.textContent=t(key);}
    function annotate(root=document.body){
        const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
        const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
        for(const node of nodes){
            const parent=node.parentElement;if(!parent||parent.closest(skip)||parent.closest('[data-i18n]')||entries.has(parent))continue;
            const key=node.textContent.trim();if(!key||!catalog.has(key))continue;
            if(parent.tagName==='OPTION'){if(!parent.hasAttribute('value'))parent.value=parent.textContent;text(parent,key);continue;}
            const span=document.createElement('span');span.dataset.i18n=key;span.textContent=t(key);node.replaceWith(span);
        }
        root.querySelectorAll?.('[placeholder]').forEach(e=>{const key=e.dataset.placeholderKey||e.getAttribute('placeholder');if(catalog.has(key)){e.dataset.placeholderKey=key;e.placeholder=t(key);}});
    }
    function apply(){
        document.documentElement.lang=language;
        document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=t(e.dataset.i18n));
        for(const [element,key] of entries){if(!element.isConnected){entries.delete(element);continue;}element.textContent=t(key);}
        document.querySelectorAll('[data-language-select]').forEach(s=>s.value=language);
        document.querySelectorAll('[aria-label],[title],[alt]').forEach(e=>{for(const attr of ['aria-label','title','alt']){const name='i18n-'+attr;const key=e.getAttribute('data-'+name)||e.getAttribute(attr);if(key&&catalog.has(key)){e.setAttribute('data-'+name,key);e.setAttribute(attr,t(key));}}});
        annotate();
    }
    function setLanguage(value){if(!languages.includes(value))return;language=value;try{localStorage.setItem('vlm-language',value);}catch{}apply();document.dispatchEvent(new CustomEvent('language-changed',{detail:value}));}
    window.i18n={sourceLabel:source=>(source?.is_local||source?.id==='agx-local')?t('Host camera'):(source?.label||t('Camera')),t,text,annotate,apply,setLanguage,get language(){return language;}};
    document.documentElement.lang=language;
    document.addEventListener('DOMContentLoaded',()=>{
        document.querySelectorAll('[data-language-select]').forEach(s=>{s.value=language;s.addEventListener('change',e=>setLanguage(e.target.value));});
        annotate();apply();
        // Existing builders finish during the same DOMContentLoaded dispatch.
        queueMicrotask(()=>{annotate();apply();});
        const observer=new MutationObserver(records=>{
            const roots=new Set();
            for(const record of records){
                if(record.type==='characterData')roots.add(record.target.parentElement);
                else for(const node of record.addedNodes)roots.add(node.nodeType===Node.ELEMENT_NODE?node:node.parentElement);
            }
            for(const root of roots)if(root?.isConnected&&!root.closest(skip)&&!root.closest('[data-i18n]'))annotate(root);
        });
        observer.observe(document.body,{childList:true,subtree:true,characterData:true});
    });
    window.addEventListener('storage',e=>{if(e.key==='vlm-language'&&languages.includes(e.newValue)){language=e.newValue;apply();document.dispatchEvent(new CustomEvent('language-changed'));}});
})();
