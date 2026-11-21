"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {createImageSender}=require("../authenticated_transport");
const context={sessionId:"ValidSessionId_123",deviceUid:"1717088"};
const image=new Uint8Array([255,216,0,255,217]);
const digest="f".repeat(64);
const valid={token:"MicrosoftBearerValidExample1234",nonce:"UniqueNonce12345678"};
function fake(){const calls=[];const fetchImpl=async(url,options)=>{
 calls.push({url,options});
 return {status:201,ok:true,json:async()=>({
  status:"accepted",analyzed_by_model:false,
  session_id:context.sessionId,device_uid:context.deviceUid,
  image_sha256:digest,receipt_id:"ReceiptValid12345",
 })};
};return {calls,fetchImpl};}
test("pinned HTTPS endpoint with no redirect and no cookies",async()=>{
 const f=fake();
 const sender=createImageSender({pinnedOrigin:"https://jason.example.test",
  tokenForSession:async()=>valid,fetchImpl:f.fetchImpl});
 const result=await sender({context,image,sha256:digest});
 assert.equal(result.status,"accepted");
 assert.equal(f.calls.length,1);
 assert.equal(f.calls[0].url,"https://jason.example.test/v1/jassist/image");
 assert.equal(f.calls[0].options.redirect,"error");
 assert.equal(f.calls[0].options.credentials,"omit");
 assert.equal(f.calls[0].options.method,"POST");
 assert.equal(f.calls[0].options.headers["Content-Type"],"image/jpeg");
 assert.equal(f.calls[0].options.body,image);
});
test("invalid unpinned URLs blocked before any fetch",()=>{
 for(const url of ["http://jason.example.test","https://jason.example.test/a",
    "https://u:p@jason.example.test","https://jason.example.test/","not-a-url",
    "https://jason.example.test:443","https://evil.example.test/?redirect=https://jason.example.test"]){
  assert.throws(()=>createImageSender({pinnedOrigin:url,
      tokenForSession:async()=>valid,fetchImpl:async()=>{}}));
 }
});
test("missing verified bearer and nonce never transmit",async()=>{
 for(const access of [null,{token:"short",nonce:"UniqueNonce12345678"},
  {token:"MicrosoftBearerValidExample1234",nonce:"bad"}]){
  const f=fake();
  const sender=createImageSender({pinnedOrigin:"https://jason.example.test",
   tokenForSession:async()=>access,fetchImpl:f.fetchImpl});
  await assert.rejects(sender({context,image,sha256:digest}));
  assert.equal(f.calls.length,0);
 }
});
test("server error or invalid receipt is never treated as success",async()=>{
 for(const response of [
  {status:401,ok:false,json:async()=>({})},
  {status:201,ok:true,json:async()=>({analyzed_by_model:true})}
 ]){
  const sender=createImageSender({pinnedOrigin:"https://jason.example.test",
   tokenForSession:async()=>valid,fetchImpl:async()=>response});
  await assert.rejects(sender({context,image,sha256:digest}));
 }
});
