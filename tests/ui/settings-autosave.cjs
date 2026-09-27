// Run with: node --test tests/ui/settings-autosave.cjs
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup(){
 const nodes={'engine-select':{value:'ollama'},'engine-model':{value:'vision-a',replaceChildren(...options){this.options=options;this.value=options[0]?.value||'';}}};
 const calls=[],responses=[];
 const context=vm.createContext({document:{getElementById:id=>nodes[id],addEventListener(){}},Option:function(text,value){this.value=value;},setText:(id,text)=>nodes[id]={text},loadStatus(){},loadVisionModels(){},fetch:async(url,options)=>{calls.push({url,options});return responses.shift();}});
 vm.runInContext(fs.readFileSync('static/js/workspace.js','utf8'),context);
 const reply=(data,ok=true)=>responses.push({ok,json:async()=>data});
 return {nodes,calls,reply,run:code=>vm.runInContext(code,context)};
}
const current={models:['vision-a','vision-b'],available:true,current_backend:'ollama',current_model:'vision-a'};
test('opening settings reads without applying; selecting a model posts once',async()=>{
 const x=setup();x.reply(current);await x.run('refreshEngine()');assert.equal(x.calls.length,1);assert.equal(x.calls[0].options,undefined);
 x.nodes['engine-model'].value='vision-b';x.reply({backend:'ollama',model:'vision-b'});await x.run('changeEngineModel()');
 assert.deepEqual(JSON.parse(x.calls[1].options.body),{backend:'ollama',model:'vision-b'});assert.equal(x.nodes['engine-model'].disabled,false);
});
test('selecting a ready framework automatically applies its listed model',async()=>{
 const x=setup();x.nodes['engine-select'].value='vllm';x.reply({...current,models:['vl-model']});x.reply({backend:'vllm',model:'vl-model'});await x.run('refreshEngine(true)');
 assert.deepEqual(JSON.parse(x.calls[1].options.body),{backend:'vllm',model:'vl-model'});
});
test('unavailable framework and rejected model changes revert the selection',async()=>{
 const x=setup();x.nodes['engine-select'].value='vllm';x.reply({...current,available:false,models:[]});await x.run('refreshEngine(true)');assert.equal(x.calls.length,1);assert.equal(x.nodes['engine-select'].value,'ollama');assert.equal(x.nodes['engine-model'].value,'vision-a');
 x.nodes['engine-model'].value='vision-b';x.reply({error:'Inference busy'},false);await x.run('changeEngineModel()');assert.equal(x.nodes['engine-model'].value,'vision-a');assert.equal(x.nodes['engine-status'].text,'Inference busy');assert.equal(x.nodes['engine-select'].disabled,false);
});
