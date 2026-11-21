"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"..","worker.js"),"utf8");
const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,"..","manifest.json"),"utf8"));
const id="pihjpgplfhmpenlghbcdbgdkadleflfi";
function rig(override={}) {
 const listeners={};
 let calls=0,authentication=async()=>({accessToken:"signed-test-not-retained"});
 let args;
 const chrome={
  runtime:{id,onMessage:{addListener:f=>listeners.message=f},
   getURL:(path)=>"chrome-extension://"+id+"/"+path},
  identity:{launchWebAuthFlow:async()=>{},getRedirectURL:()=>"https://"+id+".chromiumapp.org/jassist"},
  action:{onClicked:{addListener:()=>{}}},
  sidePanel:{open:async()=>{}},
  tabs:{onRemoved:{addListener:()=>{}},onUpdated:{addListener:()=>{}}},
 };
 const adapter={
  AOT_ENTRA_TENANT_ID:"f7054323-d52b-4863-8c2f-1898f0b6077c",
  AOT_PILOT_CLIENT_ID:"d1cc801b-13ba-4d44-bea6-e7f08186e4d5",
  JASSIST_SEND_SCOPE:"https://mcp-jason.teamaot.com/mcp/JAssist.Send",
  createEntraPkce:(options)=>{
   args=options;
   return {authorizeInteractive:async()=>{calls++;return authentication();}};
  }
 };
 vm.runInNewContext(source,{chrome,Map,Date,Error,Promise,JAssistEntraPkce:adapter,
  importScripts:()=>{},...override});
 const trusted={id,url:"chrome-extension://"+id+"/panel.html"};
 const send=(sender=trusted)=>new Promise(resolve=>listeners.message(
  {type:"test-entra-signin"},sender,resolve));
 return {send,calls:()=>calls,options:()=>args,auth:f=>authentication=f};
}
test("pilot build pins reviewed AOT SPA and single Jason HTTPS origin",()=>{
 assert.equal(manifest.version,"0.2.2");
 assert.ok(manifest.permissions.includes("identity"));
 assert.deepEqual(manifest.host_permissions,[
   "https://login.microsoftonline.com/*",
   "https://mcp-jason.teamaot.com/*",
 ]);
 assert.ok(!manifest.permissions.includes("tabs"));
 assert.ok(manifest.host_permissions.every(p=>p.startsWith("https://")));
});
test("only exact extension panel can start Entra sign-in, never Datto content or other panel",async()=>{
 const r=rig();
 for(const sender of [{},{id:"attacker",url:"https://vidal.rmm.datto.com/"},
  {id,url:"https://vidal.rmm.datto.com/"},
  {id,url:"chrome-extension://"+id+"/other.html"}]){
  const x=await r.send(sender);
  assert.equal(x.ok,false);
 }
 assert.equal(r.calls(),0);
});
test("approved SPA sign-in completes without returning or persisting any access token",async()=>{
 const r=rig();
 const result=await r.send();
 assert.equal(result.ok,true);
 assert.equal(result.loginFlowCompleted,true);
 assert.equal(result.jasonAuthorizationVerified,false);
 assert.equal(result.uploadEnabled,false);
 assert.equal(result.accessToken,undefined);
 assert.equal(r.calls(),1);
 assert.equal(r.options().clientId,"d1cc801b-13ba-4d44-bea6-e7f08186e4d5");
 assert.equal(r.options().tenantId,"f7054323-d52b-4863-8c2f-1898f0b6077c");
 assert.equal(r.options().scope,"https://mcp-jason.teamaot.com/mcp/JAssist.Send");
});
test("concurrent sign-in is denied, failure remains retryable",async()=>{
 const r=rig();
 let release;
 r.auth(()=>new Promise(resolve=>release=resolve));
 const first=r.send();
 await new Promise(resolve=>setImmediate(resolve));
 const second=await r.send();
 assert.equal(second.ok,false);
 assert.match(second.error,/already active/);
 release({accessToken:"synthetic"});
 assert.equal((await first).ok,true);
 r.auth(async()=>{throw Error("OAuth rejected");});
 const failed=await r.send();
 assert.equal(failed.ok,false);
 assert.equal((await r.send()).ok,false);
});
test("missing pilot sign-in module always fails closed",async()=>{
 const r=rig({JAssistEntraPkce:null});
 const result=await r.send();
 assert.equal(result.ok,false);
 assert.equal(result.uploadEnabled,undefined);
});
