"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {sendOnce}=require("../send_once");
const frame=Buffer.from([255,216,0,1,2,3,255,217]);
const image="data:image/jpeg;base64,"+frame.toString("base64");
const hash="a".repeat(64);
function rig(changes={}) {
 const calls=[];
 const context={
   technicianVerified:true,dattoPermissionVerified:true,
   sessionAuthorized:true,deviceUid:"1717088",
   sessionId:"ValidSessionId_123",expiresAt:2000,
   transport:"authenticated-https",imageReviewReady:true,
 };
 const contract={...context,...changes};
 let current=true;
 const args={
   getContext:async()=>{calls.push("context");return contract;},
   checkReadiness:async()=>{calls.push("preflight");return true;},
   isCurrent:async()=>{calls.push("current");return current;},
   capture:async()=>{calls.push("capture");return {image};},
   digest:async()=>{calls.push("digest");return hash;},
   deliver:async()=>{calls.push("deliver");return {
     status:"accepted",analyzed_by_model:false,
     session_id:contract.sessionId,device_uid:contract.deviceUid,
     image_sha256:hash,receipt_id:"aValidReceipt_12345"
   };},
   now:()=>1000,
 };
 return {args,calls,context:contract,revoke:()=>{current=false;}};
}

test("one click captures once, sends once, and requires matching receipt",async()=>{
 const r=rig();
 const result=await sendOnce(r.args);
 assert.equal(result.ok,true);
 assert.equal(result.sent,true);
 assert.equal(result.receipt_id,"aValidReceipt_12345");
 assert.deepEqual(r.calls,["context","preflight","current","capture","current","digest","deliver","current"]);
});
test("not authenticated blocks capture and transmission",async()=>{
 for(const field of ["technicianVerified","dattoPermissionVerified","sessionAuthorized","imageReviewReady"]){
   const r=rig({[field]:false});
   assert.equal((await sendOnce(r.args)).sent,false);
   assert.deepEqual(r.calls,["context"]);
 }
});
test("unavailable HTTPS session or expired authority blocks capture",async()=>{
 for(const change of [{transport:"http"},{expiresAt:999},{deviceUid:"whatever"},{sessionId:"x"}]){
   const r=rig(change);
   assert.equal((await sendOnce(r.args)).sent,false);
   assert.deepEqual(r.calls,["context"]);
 }
});
test("failed preflight never captures a client image",async()=>{
 const r=rig();
 r.args.checkReadiness=async()=>false;
 assert.equal((await sendOnce(r.args)).sent,false);
 assert.equal(r.calls.includes("capture"),false);
});
test("inactive tab denies image capture",async()=>{
 const r=rig();r.revoke();
 assert.equal((await sendOnce(r.args)).sent,false);
 assert.equal(r.calls.includes("capture"),false);
});
test("bad image fails without sending",async()=>{
 for(const img of ["data:text/plain;base64,QQ==","data:image/jpeg;base64,not_base64", "data:image/jpeg;base64,"+Buffer.from("fake").toString("base64")]){
   const r=rig();r.args.capture=async()=>({image:img});
   assert.equal((await sendOnce(r.args)).sent,false);
   assert.equal(r.calls.includes("deliver"),false);
 }
});
test("hash mismatch or fake receipt is rejected",async()=>{
 for(const patch of [{status:"accepted-for-test"},{image_sha256:"b".repeat(64)},{receipt_id:""},{analyzed_by_model:true},{device_uid:"9"}]){
   const r=rig();
   const original=r.args.deliver;
   r.args.deliver=async(payload)=>({...await original(payload),...patch});
   const answer=await sendOnce(r.args);
   assert.equal(answer.sent,false);
 }
});
test("lost authorization during capture or upload denies success",async()=>{
 const during=rig();
 during.args.capture=async()=>{during.revoke();return {image};};
 assert.equal((await sendOnce(during.args)).sent,false);
 assert.equal(during.calls.includes("deliver"),false);
 const after=rig();
 const original=after.args.deliver;
 after.args.deliver=async args=>{const answer=await original(args);after.revoke();return answer;};
 assert.equal((await sendOnce(after.args)).sent,false);
});
test("sender throwing an error never returns sent true",async()=>{
 const r=rig();r.args.deliver=async()=>{throw Error("network denied");};
 const result=await sendOnce(r.args);
 assert.equal(result.ok,false);
 assert.equal(result.sent,false);
});
