"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const crypto=require("node:crypto").webcrypto;
const {createEntraPkce}=require("../entra_pkce");
const tenantId="12345678-1234-1234-1234-123456789abc";
const clientId="87654321-4321-4321-4321-abcdefabcdef";
const scope="https://mcp-jason.teamaot.com/mcp/JAssist.Send";
const redirect="https://pihjpgplfhmpenlghbcdbgdkadleflfi.chromiumapp.org/jassist";
function rig(changes={}) {
 let requested, posted;
 const chromeIdentity={
   getRedirectURL:()=>redirect,
   launchWebAuthFlow:async({url,interactive})=>{
     requested=new URL(url);
     assert.equal(interactive,true);
     return redirect+"?code=synthetic-authorized-code&state="+
       encodeURIComponent(requested.searchParams.get("state"));
   },
 };
 const fetchImpl=async(url,args)=>{
   posted={url,args};
   return {ok:true,json:async()=>({access_token:"synthetic_token_for_testing_1234567",expires_in:3600})};
 };
 const client=createEntraPkce({tenantId,clientId,scope,chromeIdentity,
   cryptoImpl:crypto,fetchImpl,...changes});
 return {client,requested:()=>requested,posted:()=>posted};
}
test("PKCE challenge, state and code redemption without client secret",async()=>{
 const r=rig();
 const result=await r.client.authorizeInteractive();
 assert.equal(result.expiresIn,3600);
 assert.equal(r.requested().hostname,"login.microsoftonline.com");
 assert.equal(r.requested().searchParams.get("code_challenge_method"),"S256");
 assert.equal(r.requested().searchParams.get("scope"),scope);
 assert.equal(r.requested().searchParams.get("redirect_uri"),redirect);
 const x=r.posted();
 assert.equal(x.url,"https://login.microsoftonline.com/"+tenantId+"/oauth2/v2.0/token");
 assert.equal(x.args.method,"POST");
 assert.equal(x.args.redirect,"error");
 assert.equal(x.args.credentials,"omit");
 const p=new URLSearchParams(x.args.body);
 assert.equal(p.get("grant_type"),"authorization_code");
 assert.ok(p.get("code_verifier").length>=43);
 assert.equal(p.get("client_id"),clientId);
 assert.equal(p.has("client_secret"),false);
});
test("rejects wrong state and forged redirect host",async()=>{
 for(const returnUrl of [
   redirect+"?code=foo&state=invalid",
   "https://evil.example/jassist?code=foo&state=whatever"
 ]) {
   let fetchCount=0;
   const chromeIdentity={
     getRedirectURL:()=>redirect,
     launchWebAuthFlow:async()=>returnUrl,
   };
   const c=createEntraPkce({tenantId,clientId,scope,chromeIdentity,
     cryptoImpl:crypto,fetchImpl:async()=>{fetchCount++;}});
   await assert.rejects(c.authorizeInteractive());
   assert.equal(fetchCount,0);
 }
});
test("rejects wrong app identifiers and broad scopes",()=>{
 for(const patch of [
  {tenantId:"common"},{clientId:"invalid"},{scope:"User.Read"},
  {scope:"api://12345678-1234-1234-1234-123456789abc/JAssist.Send"},
  {scope:"api://x/Send"},{scope:scope+" openid offline_access"},
  {scope:"https://mcp-jason.teamaot.com/mcp/Jason.Read"}
 ])assert.throws(()=>createEntraPkce({
   tenantId,clientId,scope,chromeIdentity:{
     getRedirectURL:()=>redirect,launchWebAuthFlow:async()=>redirect
   },cryptoImpl:crypto,fetchImpl:async()=>{},...patch
 }));
});
test("rejects token exchange failures and invalid results",async()=>{
 for(const response of [
   {ok:false},
   {ok:true,json:async()=>({access_token:"short",expires_in:3600})},
 ]) {
   const r=rig({fetchImpl:async()=>response});
   await assert.rejects(r.client.authorizeInteractive());
 }
});

test("rejects an old unpacked Chrome extension ID even with a valid-shaped redirect",()=>{
 const old="https://kckeghklalamkjloakolkdceajkbmehj.chromiumapp.org/jassist";
 assert.throws(()=>createEntraPkce({
  tenantId,clientId,scope,chromeIdentity:{
   getRedirectURL:()=>old,
   launchWebAuthFlow:async()=>old
  },
  cryptoImpl:crypto,fetchImpl:async()=>{}
 }));
});
