"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const source=fs.readFileSync(require("node:path").join(__dirname,"..","worker.js"),"utf8");
const datto="https://vidal.rmm.datto.com/web-remote/1717088?tool=shell";
function setup(url=datto){
 const listeners={};let target={id:7,url,windowId:3,title:"PowerShell"};
 let active=target,captures=0,captureHook=null;
 const chrome={
   action:{onClicked:{addListener:f=>listeners.click=f}},
   runtime:{onMessage:{addListener:f=>listeners.message=f}},
   sidePanel:{open:async()=>{}},
   tabs:{
     get:async id=>{if(id!==target.id)throw Error("No tab");return {...target};},
     query:async()=>[active],
     captureVisibleTab:async()=>{captures++;if(captureHook)await captureHook();return "data:image/jpeg;base64,TEST";},
     onRemoved:{addListener:f=>listeners.removed=f},
     onUpdated:{addListener:f=>listeners.updated=f}
   }
 };
 vm.runInNewContext(source,{chrome,Map,Date,Error,Promise});
 const send=message=>new Promise(resolve=>listeners.message(message,{},resolve));
 return {send,captures:()=>captures,nav:url=>{target={...target,url};listeners.updated(target.id,{url});},setActive:id=>{active={...target,id};},setCaptureHook:f=>captureHook=f,listeners};
}
test("rejects lookalike Datto domain",async()=>{
 const x=setup("https://vidal.rmm.datto.com.attacker.example/");
 assert.equal((await x.send({type:"start",tabId:7})).ok,false);
});
test("capture requires explicit session",async()=>{
 const x=setup();const r=await x.send({type:"capture",tabId:7,sessionId:1});
 assert.equal(r.ended,true);assert.equal(x.captures(),0);
});
test("capture and stop, no capture after stop",async()=>{
 const x=setup();const start=await x.send({type:"start",tabId:7});
 assert.equal(start.ok,true);assert.equal((await x.send({type:"capture",tabId:7,sessionId:start.sessionId})).ok,true);
 await x.send({type:"stop",tabId:7});
 assert.equal((await x.send({type:"capture",tabId:7,sessionId:start.sessionId})).ended,true);
 assert.equal(x.captures(),1);
});
test("tab switch pauses and resumes without foreign capture",async()=>{
 const x=setup();const s=await x.send({type:"start",tabId:7});
 x.setActive(9);
 assert.equal((await x.send({type:"capture",tabId:7,sessionId:s.sessionId})).paused,true);
 assert.equal(x.captures(),0);
 x.setActive(7);
 assert.equal((await x.send({type:"capture",tabId:7,sessionId:s.sessionId})).ok,true);
});
test("navigation away revokes old session, return requires new Start",async()=>{
 const x=setup();const s=await x.send({type:"start",tabId:7});
 x.nav("https://example.com/");
 assert.equal((await x.send({type:"capture",tabId:7,sessionId:s.sessionId})).ended,true);
 x.nav(datto);
 assert.equal((await x.send({type:"capture",tabId:7,sessionId:s.sessionId})).ended,true);
 const newer=await x.send({type:"start",tabId:7});
 assert.equal(newer.ok,true);assert.notEqual(newer.sessionId,s.sessionId);
 assert.equal((await x.send({type:"capture",tabId:7,sessionId:newer.sessionId})).ok,true);
});
test("changing Datto device/path also revokes",async()=>{
 const x=setup();const s=await x.send({type:"start",tabId:7});
 x.nav("https://vidal.rmm.datto.com/web-remote/OTHER");
 assert.equal((await x.send({type:"capture",tabId:7,sessionId:s.sessionId})).ended,true);
});
test("in-flight capture is not delivered after navigation",async()=>{
 const x=setup();const s=await x.send({type:"start",tabId:7});
 x.setCaptureHook(async()=>x.nav("https://example.com/"));
 const r=await x.send({type:"capture",tabId:7,sessionId:s.sessionId});
 assert.equal(r.ended,true);assert.equal(r.image,undefined);
});
test("restarted session cannot receive stale frame",async()=>{
 const x=setup();const s=await x.send({type:"start",tabId:7});
 x.setCaptureHook(async()=>{await x.send({type:"stop",tabId:7});await x.send({type:"start",tabId:7});});
 const r=await x.send({type:"capture",tabId:7,sessionId:s.sessionId});
 assert.equal(r.ended,true);assert.equal(r.image,undefined);
});
