"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const source=fs.readFileSync(require("node:path").join(__dirname,"..","worker.js"),"utf8");
function setup(url="https://vidal.rmm.datto.com/device/1717088/al-samsung"){
  const listeners={};
  let activeTab={id:7,url,windowId:3,title:"Datto device"};
  let captures=0;
  const chrome={
    action:{onClicked:{addListener:f=>listeners.click=f}},
    runtime:{onMessage:{addListener:f=>listeners.message=f}},
    sidePanel:{open:async()=>{}},
    tabs:{
      get:async()=>activeTab,
      query:async()=>[activeTab],
      captureVisibleTab:async()=>{captures++;return "data:image/jpeg;base64,TEST";},
      onRemoved:{addListener:f=>listeners.removed=f},
      onUpdated:{addListener:f=>listeners.updated=f}
    }
  };
  vm.runInNewContext(source,{chrome,Map,Date,Error,Promise});
  const send=message=>new Promise(resolve=>listeners.message(message,{},resolve));
  return {send,captures:()=>captures,setTab:t=>activeTab=t,listeners};
}
test("rejects non-Datto host even if domain contains datto",async()=>{
 const x=setup("https://vidal.rmm.datto.com.attacker.example/device"); 
 const r=await x.send({type:"start",tabId:7});assert.equal(r.ok,false);assert.equal(x.captures(),0);
});
test("cannot capture before explicit start",async()=>{
 const x=setup();const r=await x.send({type:"capture",tabId:7});assert.equal(r.ok,false);assert.equal(x.captures(),0);
});
test("start, capture, stop and denial after stop",async()=>{
 const x=setup();assert.equal((await x.send({type:"start",tabId:7})).ok,true);
 const c=await x.send({type:"capture",tabId:7});assert.equal(c.ok,true);assert.match(c.image,/^data:image\/jpeg/);
 assert.equal(x.captures(),1);assert.equal((await x.send({type:"stop",tabId:7})).ok,true);
 assert.equal((await x.send({type:"capture",tabId:7})).ok,false);assert.equal(x.captures(),1);
});
test("navigating outside Datto revokes observation",async()=>{
 const x=setup();await x.send({type:"start",tabId:7});
 x.setTab({id:7,url:"https://example.org/",windowId:3});
 assert.equal((await x.send({type:"capture",tabId:7})).ok,false);assert.equal(x.captures(),0);
});
test("switching browser tabs stops snapshots",async()=>{
 const x=setup();await x.send({type:"start",tabId:7});
 x.setTab({id:9,url:"https://example.org/",windowId:3});
 assert.equal((await x.send({type:"capture",tabId:7})).ok,false);assert.equal(x.captures(),0);
});
