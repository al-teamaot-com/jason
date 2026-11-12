"use strict";
/*
 * Reviewed-source J-Assist worker adapter for a future authenticated HTTPS
 * intake. This module does not register a server, create secrets or grant
 * technician permission. The verified JAssist.Send JWT is held in worker
 * memory only. The server independently validates the Entra group,
 * individual technician, Datto device, session and content policy.
 */
const JASSIST_PINNED_ORIGIN="https://mcp-jason.teamaot.com";
const DEVICE_URL=/^\/(?:device|web-remote)\/([0-9]{1,24}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\/|$)/i;
const HTTPS_DATTO=/^https:\/\/[a-z0-9-]+\.rmm\.datto\.com\//i;
const SESSION_ID=/^[A-Za-z0-9_-]{12,128}$/;
function deviceFromDattoUrl(raw) {
  if (typeof raw!=="string" || !HTTPS_DATTO.test(raw)) return null;
  let url;
  try {url=new URL(raw);}catch{return null;}
  if(url.username||url.password||url.hash||url.port||url.protocol!=="https:")return null;
  if(!/^[a-z0-9-]+\.rmm\.datto\.com$/i.test(url.hostname))return null;
  const found=DEVICE_URL.exec(url.pathname);
  return found && found[1]!=="00000000-0000-0000-0000-000000000000" ? found[1].toLowerCase():null;
}
function createLiveSendBridge({chromeApi,tokenForSend,
                               fetchImpl=fetch,
                               senderFactory=globalThis.JAssistAuthenticatedTransport?.createImageSender,
                               digestImpl=crypto.subtle,
                               cryptoImpl=crypto,
                               now=()=>Date.now()}) {
  if(!chromeApi?.tabs?.get || !chromeApi.tabs.query ||
     !chromeApi.tabs.captureVisibleTab || typeof tokenForSend!=="function" ||
     typeof fetchImpl!=="function" || !digestImpl?.digest ||
     !cryptoImpl?.getRandomValues ||
     typeof senderFactory!=="function") {
    throw Error("Reviewed J-Assist browser send dependencies unavailable.");
  }
  const activeServerSessions=new Map();
  const origin=JASSIST_PINNED_ORIGIN;
  const json=async (url,options) => {
    const response=await fetchImpl(url,{
      credentials:"omit",redirect:"error",cache:"no-store",
      mode:"cors",...options
    });
    if(!response?.ok)return null;
    return response.json();
  };
  const token=async()=>{
    const result=await tokenForSend();
    if(!result || typeof result.token!=="string" ||
       result.token.length<100||result.token.length>8192 ||
       !Number.isFinite(result.expiresAt) ||
       result.expiresAt-now()<30000)throw Error("Reauthenticate AOT J-Assist.");
    return result.token;
  };
  const headers=async()=>({
    "Authorization":"Bearer "+await token(),
    "Accept":"application/json",
  });
  const boundTab=async (tabId,localSessionId)=>{
    if(!Number.isSafeInteger(tabId)||!Number.isSafeInteger(localSessionId))
      return null;
    const tab=await chromeApi.tabs.get(tabId).catch(()=>null);
    if(!tab || !deviceFromDattoUrl(tab.url))return null;
    const selected=await chromeApi.tabs.query({
      active:true,windowId:tab.windowId
    });
    if(selected?.[0]?.id!==tab.id)return null;
    return {tabId,localSessionId,tabUrl:tab.url,
            windowId:tab.windowId,deviceUid:deviceFromDattoUrl(tab.url)};
  };
  const stillCurrent=async ctx=>{
    const tab=await chromeApi.tabs.get(ctx.tabId).catch(()=>null);
    if(!tab || tab.windowId!==ctx.windowId || tab.url!==ctx.tabUrl ||
       deviceFromDattoUrl(tab.url)!==ctx.deviceUid)return false;
    const selected=await chromeApi.tabs.query({
      active:true,windowId:ctx.windowId
    });
    return selected?.[0]?.id===ctx.tabId;
  };
  const sender=senderFactory({
    pinnedOrigin:origin,
    tokenForSession:async context=>{
      if(!(await stillCurrent(context)))throw Error("Session changed.");
      const nonce=new Uint8Array(24);
      cryptoImpl.getRandomValues(nonce);
      return {token:await token(),nonce:Array.from(nonce,b=>b.toString(16).padStart(2,"0")).join("")};
    },
    fetchImpl,
  });
  async function readinessStatus({tabId,sessionId}) {
    const denied=reason=>({ready:false,reason});
    try{
      const tab=await boundTab(tabId,sessionId);
      if(!tab)return denied("Select the active Datto device or Web Remote tab.");
      let authorization;
      try {authorization=await headers();}
      catch {return denied("Complete AOT Microsoft sign-in to check Jason access.");}
      let result;
      try {
        result=await fetchImpl(origin+"/v1/jassist/readiness?device_uid="+tab.deviceUid,{
          method:"GET",headers:authorization,credentials:"omit",
          redirect:"error",cache:"no-store",mode:"cors",
        });
      }catch {
        return denied("Jason HTTPS receiver is unreachable or blocked.");
      }
      if(result?.status===404)return denied("Jason image receiver is not deployed (HTTP 404).");
      if(result?.status===401)return denied("AOT sign-in token was rejected by Jason.");
      if(result?.status===403)return denied("Jason denied current Entra group or Datto device access.");
      if(result?.status===503)return denied("Jason image review or intake service is unavailable.");
      if(!result?.ok)return denied("Jason receiver readiness check did not succeed.");
      let data;
      try {data=await result.json();}
      catch {return denied("Jason returned an invalid readiness response.");}
      const ready=data?.status==="ready" &&
        data.device_uid===tab.deviceUid &&
        data.technician_verified===true &&
        data.entra_group_verified===true &&
        data.datto_device_authorized===true &&
        data.image_review_ready===true &&
        data.production_ingress===true;
      return ready
        ? {ready:true,reason:"Jason verified Entra access, Datto device and content review."}
        : denied("Jason has not verified this technician, device and image review.");
    }catch {
      return denied("J-Assist could not verify the receiving service.");
    }
  }
  async function readiness(args){
    const result=await readinessStatus(args);
    return result.ready===true;
  }
  async function dependencies({tabId,sessionId}) {
    const tab=await boundTab(tabId,sessionId);
    if(!tab)throw Error("Datto tab not current.");
    if(!(await readiness({tabId,sessionId})))
      throw Error("Jason receiving service not authorized.");
    const response=await json(origin+"/v1/jassist/session",{
      method:"POST",headers:{...(await headers()),"Content-Type":"application/json"},
      body:JSON.stringify({device_uid:tab.deviceUid,consent:true}),
    });
    if(response?.status!=="authorized" ||
       !SESSION_ID.test(response.session_id||"") ||
       response.device_uid!==tab.deviceUid ||
       response.entra_group_verified!==true ||
       response.datto_device_authorized!==true ||
       response.technician_verified!==true ||
       response.image_review_ready!==true ||
       response.production_ingress!==true ||
       !Number.isFinite(response.expires_at_ms) ||
       response.expires_at_ms<=now() ||
       response.expires_at_ms>now()+300000) {
      throw Error("Jason session attestation missing.");
    }
    const context={...tab,sessionId:response.session_id,
      technicianVerified:true,dattoPermissionVerified:true,
      sessionAuthorized:true,imageReviewReady:true,
      expiresAt:response.expires_at_ms,transport:"authenticated-https"};
    activeServerSessions.set(tabId,context);
    return {
      getContext:async()=>context,
      checkReadiness:async c=>{
        if(!(await stillCurrent(c)))return false;
        const check=await json(origin+"/v1/jassist/session/validate",{
          method:"POST",
          headers:{...(await headers()),"Content-Type":"application/json"},
          body:JSON.stringify({session_id:c.sessionId,device_uid:c.deviceUid}),
        });
        return check?.status==="authorized" &&
          check.session_id===c.sessionId &&
          check.device_uid===c.deviceUid &&
          check.image_review_ready===true &&
          check.production_ingress===true;
      },
      capture:async c=>{
        if(!(await stillCurrent(c)))throw Error("Datto tab changed");
        const image=await chromeApi.tabs.captureVisibleTab(c.windowId,{
          format:"jpeg",quality:60
        });
        if(!(await stillCurrent(c)))throw Error("Datto tab changed");
        return {image};
      },
      deliver:async request=>sender(request),
      isCurrent:stillCurrent,
      digest:async bytes=>{
        const hash=await digestImpl.digest("SHA-256",bytes);
        return Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,"0")).join("");
      },now,
    };
  }
  async function revoke({tabId}){
    const ctx=activeServerSessions.get(tabId);
    activeServerSessions.delete(tabId);
    if(!ctx)return;
    try{
      await json(origin+"/v1/jassist/session/stop",{
        method:"POST",
        headers:{...(await headers()),"Content-Type":"application/json"},
        body:JSON.stringify({session_id:ctx.sessionId,device_uid:ctx.deviceUid}),
      });
    }catch{/* Server TTL and per-read authorization remain mandatory. */}
  }
  return Object.freeze({readiness,readinessStatus,dependencies,revoke});
}
const JAssistLiveBridgeFactory=Object.freeze({
  createLiveSendBridge,deviceFromDattoUrl,
});
if(typeof globalThis!=="undefined")globalThis.JAssistLiveBridgeFactory=JAssistLiveBridgeFactory;
if(typeof module!=="undefined"&&module.exports)module.exports=JAssistLiveBridgeFactory;
