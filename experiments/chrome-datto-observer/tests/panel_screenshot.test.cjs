"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const panelCode=fs.readFileSync(path.join(__dirname,"..","panel.js"),"utf8");
const tinyImage="data:image/jpeg;base64,/9j/2Q==";
function harness(){
  const ids=["start","stop","status","stamp","frame","scope","screenshot","download","evidence-frame","evidence-status"];
  const nodes=new Map(ids.map(id=>[id,{id,disabled:false,hidden:true,textContent:"",src:"",href:"",download:"",listeners:{},addEventListener(type,handler){this.listeners[type]=handler;},removeAttribute(name){delete this[name];}}]));
  nodes.get("stop").disabled=true;nodes.get("screenshot").disabled=true;
  const calls=[];
  let activeTab=42;
  const handlers={};
  const chrome={tabs:{query:async()=>[{id:activeTab,url:"https://us.rmm.datto.com/device/42"}]},runtime:{sendMessage:async m=>{
    calls.push(m);
    if(m.type==="start")return {ok:true,sessionId:7};
    if(m.type==="stop")return {ok:true};
    if(m.type==="capture")return {ok:true,image:tinyImage,capturedAt:"2026-11-06T12:00:00.000Z"};
    throw Error("unexpected");
  }}};
  const ctx={document:{querySelector:selector=>nodes.get(selector.slice(1))},window:{addEventListener:(event,handler)=>handlers[event]=handler},chrome,JAssistScope:{classify:()=>({supported:true,label:"Datto graphical"})},Date,setInterval:()=>1,clearInterval:()=>{}};
  vm.runInNewContext(panelCode,ctx,{filename:"panel.js"});
  return {nodes,calls,handlers,chrome,select:id=>nodes.get(id),changeActive:id=>activeTab=id};
}
test("requires Start and explicit screenshot click; download is not automatic",async()=>{
 const h=harness(),shot=h.select("screenshot"),save=h.select("download");
 assert.equal(shot.disabled,true);
 await h.select("start").listeners.click();
 assert.equal(shot.disabled,false);
 assert.equal(save.hidden,true);
 await shot.listeners.click();
 assert.equal(save.hidden,false);
 assert.equal(save.href,tinyImage);
 assert.match(save.download,/^j-assist-evidence-2026-11-06T12-00-00-000Z.jpg$/);
 assert.equal(h.calls.filter(c=>c.type==="capture").length,2);
 assert.equal(h.calls.filter(c=>c.type==="upload").length,0);
 await h.select("stop").listeners.click();
 assert.equal(save.hidden,true);
 assert.equal(save.href,undefined);
 assert.equal(shot.disabled,true);
});
test("failed capture never offers stale downloadable screenshot",async()=>{
 const h=harness();
 await h.select("start").listeners.click();
 await h.select("screenshot").listeners.click();
 h.chrome.runtime.sendMessage=async m=>m.type==="capture"?{ok:false,error:"revoked"}:{ok:true};
 await h.select("screenshot").listeners.click();
 assert.equal(h.select("download").hidden,true);
 assert.equal(h.select("download").href,undefined);
});
test("page closure revokes download link and requests stop",async()=>{
 const h=harness();
 await h.select("start").listeners.click();
 await h.select("screenshot").listeners.click();
 h.handlers.pagehide();
 assert.equal(h.select("download").hidden,true);
 assert.equal(h.select("screenshot").disabled,true);
 assert.equal(h.calls.at(-1).type,"stop");
});
