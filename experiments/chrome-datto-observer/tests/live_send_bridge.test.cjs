"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const crypto=require("node:crypto");
const bridge=require("../live_send_bridge");
const {sendOnce}=require("../send_once");
const {createImageSender}=require("../authenticated_transport");

const image=Buffer.from("ffd8ffe000104a46494600","hex");
const jpeg=Buffer.concat([image,Buffer.from("safe synthetic browser test"),Buffer.from("ffd9","hex")]);
const base64="data:image/jpeg;base64,"+jpeg.toString("base64");
const goodBearer="a".repeat(512);
const now=Date.now();

function harness(deviceUid="1717088"){
 const tab={id:42,windowId:2,url:"https://vidal.rmm.datto.com/device/"+deviceUid+"/console"};
 const calls=[];
 let activeId=42,group=true,datto=true,review=true,expires=now+60000,readinessCode=200;
 let token={token:goodBearer,expiresAt:now+3600000};
 const chromeApi={tabs:{
    get:async id=>id===42?tab:null,
    query:async()=>[{id:activeId}],
    captureVisibleTab:async()=>{calls.push({path:"capture"});return base64;},
 }};
 const fetchImpl=async(url,opts)=>{
   const path=new URL(url).pathname;
   const method=opts.method;
   calls.push({path,method,opts});
   assert.ok(url.startsWith("https://mcp-jason.teamaot.com/"));
   assert.match(opts.headers.Authorization,/^Bearer a+$/);
   const response=(status,body)=>({status,ok:status>=200&&status<300,json:async()=>body});
   if(path==="/v1/jassist/readiness"){
     return response(readinessCode,{status:"ready",device_uid:deviceUid,
       technician_verified:true,entra_group_verified:group,
       datto_device_authorized:datto,image_review_ready:review,
       production_ingress:true});
   }
   if(path==="/v1/jassist/session"){
     return response(201,{status:"authorized",
       session_id:"server_session_123456789",device_uid:deviceUid,
       technician_verified:true,entra_group_verified:group,
       datto_device_authorized:datto,image_review_ready:review,
       production_ingress:true,expires_at_ms:expires});
   }
   if(path==="/v1/jassist/session/validate"){
     return response(200,{status:"authorized",session_id:"server_session_123456789",
       device_uid:deviceUid,image_review_ready:review,production_ingress:true});
   }
   if(path==="/v1/jassist/image"){
     const request=Buffer.from(opts.body);
     assert.deepEqual(request,jpeg);
     assert.equal(opts.headers["X-JAssist-Device"],deviceUid);
     assert.equal(opts.headers["X-JAssist-SHA256"],
       crypto.createHash("sha256").update(jpeg).digest("hex"));
     return response(201,{status:"accepted",session_id:"server_session_123456789",
       device_uid:deviceUid,image_sha256:opts.headers["X-JAssist-SHA256"],
       receipt_id:"test_receipt_12345678",analyzed_by_model:false});
   }
   if(path==="/v1/jassist/session/stop")return response(200,{ok:true});
   throw Error("Unexpected request: "+path);
 };
 const live=bridge.createLiveSendBridge({
   chromeApi,tokenForSend:async()=>token,fetchImpl,
   senderFactory:createImageSender,cryptoImpl:crypto.webcrypto,
   digestImpl:crypto.webcrypto.subtle,now:()=>now});
 return {live,calls,tab,
   setActive:x=>activeId=x,
   group:x=>group=x,
   datto:x=>datto=x,
   review:x=>review=x,
   expires:x=>expires=x,
   token:x=>token=x,
   readinessCode:x=>readinessCode=x};
}
test("only exact device URLs from reviewed Datto RMM origin are accepted",()=>{
 for(const url of [
   "https://vidal.rmm.datto.com/device/1717088/console",
   "https://us.rmm.datto.com/device/1717088",
   "https://vidal.rmm.datto.com/web-remote/1717088?tool=shell&windowsSessionId=1"
 ]) assert.equal(bridge.deviceFromDattoUrl(url),"1717088");
 for(const url of [
   "https://vidal.rmm.datto.com/dashboard",
   "https://evil.com/device/1717088","http://vidal.rmm.datto.com/device/1717088",
   "https://vidal.rmm.datto.com.evil.net/device/1717088",
   "https://vidal.rmm.datto.com/device/1717088/..#secret",
   "https://vidal.rmm.datto.com/device/abc",
   "https://vidal.rmm.datto.com/device/1234567890123456789012345",
   "not-a-url"
 ]) assert.equal(bridge.deviceFromDattoUrl(url),null,url);
});
test("full browser-shaped send requires server-authenticated group and Datto readiness",async()=>{
 const t=harness();
 assert.equal(await t.live.readiness({tabId:42,sessionId:7}),true);
 const deps=await t.live.dependencies({tabId:42,sessionId:7});
 const result=await sendOnce(deps);
 assert.equal(result.sent,true);
 assert.equal(result.receipt_id,"test_receipt_12345678");
 assert.equal(result.analyzed_by_model,false);
 assert.equal(t.calls.filter(c=>c.path==="capture").length,1);
 assert.equal(t.calls.filter(c=>c.path==="/v1/jassist/image").length,1);
 assert.equal(t.calls.filter(c=>c.path==="/v1/jassist/session").length,1);
 await t.live.revoke({tabId:42});
 assert.equal(t.calls.filter(c=>c.path==="/v1/jassist/session/stop").length,1);
});
test("native Datto UUID Web Remote device survives whole send and receipt",async()=>{
 const nativeUid="69571572-83f7-1e33-9cdf-01717d4e74a4";
 assert.equal(bridge.deviceFromDattoUrl(
   "https://vidal.rmm.datto.com/web-remote/"+nativeUid+"?tool=shell"),nativeUid);
 const t=harness(nativeUid);
 const deps=await t.live.dependencies({tabId:42,sessionId:7});
 const result=await sendOnce(deps);
 assert.equal(result.sent,true);
 assert.equal(result.device_uid,nativeUid);
 assert.equal(t.calls.filter(c=>c.path==="capture").length,1);
 assert.equal(t.calls.filter(c=>c.path==="/v1/jassist/image").length,1);
});
test("missing group, Datto ownership or reviewer rejects before capture",async()=>{
 for(const disable of ["group","datto","review"]){
   const t=harness();t[disable](false);
   assert.equal(await t.live.readiness({tabId:42,sessionId:7}),false);
   await assert.rejects(()=>t.live.dependencies({tabId:42,sessionId:7}));
   assert.equal(t.calls.filter(c=>c.path==="capture").length,0);
   assert.equal(t.calls.filter(c=>c.path==="/v1/jassist/image").length,0);
 }
});
test("disabled button diagnostics distinguish missing login, receiver and authorization",async()=>{
 const t=harness();
 t.token(null);
 let state=await t.live.readinessStatus({tabId:42,sessionId:7});
 assert.equal(state.ready,false);
 assert.match(state.reason,/sign-in/i);
 t.token({token:goodBearer,expiresAt:now+3600000});
 for(const [code,description] of [
   [404,/not deployed.*404/i],
   [401,/token was rejected/i],
   [403,/denied.*Entra group or Datto/i],
   [503,/review or intake service/i],
 ]){
   t.readinessCode(code);
   state=await t.live.readinessStatus({tabId:42,sessionId:7});
   assert.equal(state.ready,false);
   assert.match(state.reason,description);
 }
 assert.equal(t.calls.filter(c=>c.path==="capture").length,0);
 assert.equal(t.calls.filter(c=>c.path==="/v1/jassist/image").length,0);
 t.readinessCode(200);
 assert.equal((await t.live.readinessStatus({tabId:42,sessionId:7})).ready,true);
});

test("missing bearer, wrong tab and expired session fail before screenshot",async()=>{
 const t=harness();
 t.token(null);
 assert.equal(await t.live.readiness({tabId:42,sessionId:7}),false);
 t.token({token:goodBearer,expiresAt:now+3600000});
 t.setActive(88);
 assert.equal(await t.live.readiness({tabId:42,sessionId:7}),false);
 t.setActive(42);
 t.expires(now-1);
 await assert.rejects(()=>t.live.dependencies({tabId:42,sessionId:7}));
 assert.equal(t.calls.filter(c=>c.path==="capture").length,0);
});
test("navigation during capture prevents delivery",async()=>{
 const t=harness();
 const deps=await t.live.dependencies({tabId:42,sessionId:7});
 const originalCapture=deps.capture;
 deps.capture=async ctx=>{
   const captured=await originalCapture(ctx);
   t.tab.url="https://vidal.rmm.datto.com/dashboard";
   return captured;
 };
 const result=await sendOnce(deps);
 assert.equal(result.sent,false);
 assert.equal(t.calls.filter(c=>c.path==="/v1/jassist/image").length,0);
});
