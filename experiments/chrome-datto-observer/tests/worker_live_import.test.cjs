"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const crypto=require("node:crypto");

const dir=path.resolve(__dirname,"..");
function browserWorker(){
  const listeners={};
  const tab={id:42,windowId:10,url:"https://vidal.rmm.datto.com/device/1717088/console"};
  let active=42;
  const httpCalls=[];
  const chrome={
    runtime:{
      id:"pihjpgplfhmpenlghbcdbgdkadleflfi",
      getURL:p=>"chrome-extension://pihjpgplfhmpenlghbcdbgdkadleflfi/"+p,
      onMessage:{addListener:f=>listeners.message=f},
    },
    identity:{getRedirectURL:()=> "https://pihjpgplfhmpenlghbcdbgdkadleflfi.chromiumapp.org/jassist",
      launchWebAuthFlow:async()=>null},
    action:{onClicked:{addListener:()=>{}}},
    sidePanel:{open:async()=>{}},
    tabs:{
      get:async id=>id===42?tab:null,
      query:async()=>[{id:active}],
      captureVisibleTab:async()=>{throw Error("Capture should not run without backend");},
      onUpdated:{addListener:()=>{}},
      onRemoved:{addListener:()=>{}},
    }
  };
  const sandbox={chrome,crypto:crypto.webcrypto,URL,Uint8Array,
    TextEncoder,URLSearchParams,atob,fetch:async()=>{throw Error("No network");}};
  const context=vm.createContext(sandbox);
  sandbox.importScripts=(...files)=>{
    for(const file of files){
      const code=fs.readFileSync(path.join(dir,file),"utf8");
      vm.runInContext(code,context,{filename:file});
    }
  };
  const source=fs.readFileSync(path.join(dir,"worker.js"),"utf8");
  vm.runInContext(source,context,{filename:"worker.js"});
  const sender={
    id:chrome.runtime.id,
    url:chrome.runtime.getURL("panel.html"),
  };
  const send=(msg,origin=sender)=>new Promise(resolve=>{
    listeners.message(msg,origin,resolve);
  });
  return {context,send,chrome,tab,httpCalls,setActive:id=>active=id};
}
test("all worker browser scripts load and are reachable via trusted worker global",()=>{
  const b=browserWorker();
  for(const contract of ["JAssistEntraPkce","JAssistOneClick",
     "JAssistAuthenticatedTransport","JAssistLiveBridgeFactory","JAssistLiveSendBridge"]){
     assert.ok(b.context[contract],contract+" missing");
  }
  assert.equal(typeof b.context.JAssistLiveSendBridge.readiness,"function");
});
test("unverified sender cannot request screenshot or session upload",async()=>{
  const b=browserWorker();
  assert.equal((await b.send({type:"start",tabId:42})).ok,true);
  const start=await b.send({type:"start",tabId:42});
  assert.equal(start.ok,true);
  const bad=await b.send({type:"send-to-jason",tabId:42,sessionId:start.sessionId},
                        {id:"browser-tab",url:"https://vidal.rmm.datto.com/device/1717088"});
  assert.equal(bad.ok,false);
  const ready=await b.send({type:"send-readiness",tabId:42,sessionId:start.sessionId});
  assert.equal(ready.ready,false);
  const result=await b.send({type:"send-to-jason",tabId:42,sessionId:start.sessionId});
  assert.equal(result.ok,false);
  assert.notEqual(result.sent,true);
});
test("Entra bearer remains worker-private and sign-in alone cannot authorize upload",async()=>{
  const b=browserWorker();
  const original=b.context.JAssistEntraPkce;
  b.context.JAssistEntraPkce={
    ...original,
    createEntraPkce:()=>({authorizeInteractive:async()=>({
      accessToken:"signed-synthetic-private-token-"+("x".repeat(460)),
      expiresIn:3600
    })}),
  };
  const response=await b.send({type:"test-entra-signin"});
  assert.equal(response.ok,true);
  assert.equal(response.loginFlowCompleted,true);
  assert.equal(response.uploadEnabled,false);
  assert.equal(response.jasonAuthorizationVerified,false);
  assert.equal(JSON.stringify(response).includes("signed-synthetic-private-token"),false);
  const started=await b.send({type:"start",tabId:42});
  assert.equal(started.ok,true);
  const ready=await b.send({type:"send-readiness",tabId:42,sessionId:started.sessionId});
  assert.equal(ready.ready,false);
});
