"use strict";
/*
 * J-Assist Microsoft Entra authorization-code + PKCE adapter.
 * Preproduction source: does NOT register an app or grant permissions.
 * The extension's redirect URI must be explicitly registered as SPA in
 * AOT Entra. The server independently validates issuer/audience/subject.
 *
 * Token lives only in the caller's memory, never localStorage or Datto DOM.
 */
const GUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ENTRA_HOST="login.microsoftonline.com";
// Existing AOT Jason MCP resource. This is NOT an unverified api:// URI.
const JASSIST_SEND_SCOPE="https://mcp-jason.teamaot.com/mcp/JAssist.Send";
const PINNED_CHROME_EXTENSION_ID="pihjpgplfhmpenlghbcdbgdkadleflfi";
function b64url(data){
  const bytes=typeof data==="string"?new TextEncoder().encode(data):data;
  let raw="";for(const byte of bytes)raw+=String.fromCharCode(byte);
  return btoa(raw).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
}
function randomUrlSafe(cryptoImpl,bytes=32) {
  const buffer=new Uint8Array(bytes);
  cryptoImpl.getRandomValues(buffer);
  return b64url(buffer);
}
function validateOptions({tenantId,clientId,scope}) {
  if(!GUID.test(tenantId||"")||!GUID.test(clientId||"")||
     typeof scope!=="string" ||
     scope!==JASSIST_SEND_SCOPE){
    throw Error("Reviewed AOT Entra application configuration required.");
  }
  return true;
}
function createEntraPkce({
  tenantId,clientId,scope,chromeIdentity,
  cryptoImpl=crypto,fetchImpl=fetch,
}) {
  validateOptions({tenantId,clientId,scope});
  if(!chromeIdentity?.getRedirectURL||!chromeIdentity?.launchWebAuthFlow ||
     !cryptoImpl?.getRandomValues||!cryptoImpl?.subtle?.digest||
     typeof fetchImpl!=="function")throw Error("Secure PKCE browser dependencies required.");
  const redirectUri=chromeIdentity.getRedirectURL("jassist");
  const redirect=new URL(redirectUri);
  if(redirect.protocol!=="https:" ||
     redirect.hostname!==PINNED_CHROME_EXTENSION_ID+".chromiumapp.org" ||
     redirect.pathname!=="/jassist" ||
     redirect.search || redirect.hash) {
    throw Error("Expected pinned Chrome extension OAuth redirect.");
  }
  const authBase=`https://${ENTRA_HOST}/${tenantId}/oauth2/v2.0/`;
  return Object.freeze({
    redirectUri,
    async authorizeInteractive() {
      // Only invoke synchronously downstream of a technician click.
      const verifier=randomUrlSafe(cryptoImpl,48);
      const state=randomUrlSafe(cryptoImpl,24);
      const digest=await cryptoImpl.subtle.digest("SHA-256",new TextEncoder().encode(verifier));
      const challenge=b64url(new Uint8Array(digest));
      const authorize=new URL(authBase+"authorize");
      const params=authorize.searchParams;
      params.set("client_id",clientId);
      params.set("response_type","code");
      params.set("redirect_uri",redirectUri);
      params.set("response_mode","query");
      params.set("scope",scope);
      params.set("state",state);
      params.set("code_challenge",challenge);
      params.set("code_challenge_method","S256");
      const result=await chromeIdentity.launchWebAuthFlow({url:authorize.href,interactive:true});
      if(!result)throw Error("Entra sign-in was cancelled.");
      const answer=new URL(result);
      if(answer.origin!==redirect.origin || answer.pathname!==redirect.pathname ||
         answer.searchParams.get("state")!==state ||
         answer.searchParams.has("error"))throw Error("Invalid or denied Entra OAuth response.");
      const code=answer.searchParams.get("code");
      if(!code || code.length>4096)throw Error("Missing Entra authorization code.");
      const body=new URLSearchParams({
        client_id:clientId,grant_type:"authorization_code",
        code,redirect_uri:redirectUri,code_verifier:verifier,scope,
      });
      const response=await fetchImpl(authBase+"token",{
        method:"POST",mode:"cors",credentials:"omit",redirect:"error",
        headers:{"Content-Type":"application/x-www-form-urlencoded"},
        body:body.toString(),
      });
      if(!response?.ok)throw Error("Entra access-token exchange failed.");
      const data=await response.json();
      if(typeof data?.access_token!=="string" ||
         data.access_token.length<20 || data.access_token.length>8192 ||
         typeof data.expires_in!=="number" ||
         !Number.isFinite(data.expires_in) ||
         data.expires_in<60 || data.expires_in>86400) {
        throw Error("Invalid Entra access-token response.");
      }
      // The server must verify the JWT issuer, tid, oid, aud and scope.
      return {accessToken:data.access_token,expiresIn:data.expires_in};
    }
  });
}
const JAssistEntraPkce=Object.freeze({createEntraPkce,validateOptions,JASSIST_SEND_SCOPE,PINNED_CHROME_EXTENSION_ID});
if(typeof module!=="undefined"&&module.exports)module.exports=JAssistEntraPkce;
