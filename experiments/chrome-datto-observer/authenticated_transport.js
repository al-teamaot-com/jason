"use strict";
/*
 * Transport boundary for one-click screenshots, not an OAuth implementation.
 * Installation must pin Jason's HTTPS origin through a reviewed extension
 * build. Never accept the destination from a Datto page, URL, or message.
 * The technician token must come from a verified Entra OAuth implementation.
 * This module is inert until those two independent adapters exist.
 */
function createImageSender({pinnedOrigin,tokenForSession,fetchImpl=fetch}) {
  let url;
  try {
    const origin=new URL(pinnedOrigin);
    if(origin.protocol!=="https:" ||
       origin.origin!==pinnedOrigin ||
       origin.username || origin.password ||
       !/^[a-z0-9.-]+$/i.test(origin.hostname)) {
      throw Error("invalid pinned origin");
    }
    url=new URL("/v1/jassist/image",origin).href;
  } catch {
    throw Error("A reviewed, pinned HTTPS Jason service origin is required.");
  }
  if(typeof tokenForSession!=="function"||typeof fetchImpl!=="function"){
    throw Error("Authenticated sender dependencies unavailable.");
  }
  return async function deliver({context,image,sha256}) {
    if(!(image instanceof Uint8Array) || image.length<4 || image.length>1024*1024 ||
       typeof sha256!=="string" || !/^[0-9a-f]{64}$/.test(sha256) ||
       !context || typeof context.sessionId!=="string" ||
       typeof context.deviceUid!=="string") {
      throw Error("Invalid governed screenshot request.");
    }
    const access=await tokenForSession(context);
    if(!access || typeof access.token!=="string" ||
       access.token.length<20 || access.token.length>8192 ||
       typeof access.nonce!=="string" ||
       !/^[A-Za-z0-9]{16,96}$/.test(access.nonce)) {
      throw Error("Verified Microsoft bearer and nonce unavailable.");
    }
    const response=await fetchImpl(url,{
      method:"POST",
      mode:"cors",
      credentials:"omit",
      cache:"no-store",
      redirect:"error",
      headers:{
        "Authorization":"Bearer "+access.token,
        "Content-Type":"image/jpeg",
        "X-JAssist-Session":context.sessionId,
        "X-JAssist-Device":context.deviceUid,
        "X-JAssist-SHA256":sha256,
        "X-JAssist-Nonce":access.nonce,
      },
      body:image,
    });
    if(!response || response.status!==201 || !response.ok){
      throw Error("Jason did not accept the image.");
    }
    const payload=await response.json();
    // Never trust arbitrary server responses as evidence of model analysis.
    // Session, device, image hash, and receipt are checked by send_once.js.
    if(!payload || payload.analyzed_by_model!==false){
      throw Error("Invalid Jason receipt.");
    }
    return payload;
  };
}
const JAssistAuthenticatedTransport=Object.freeze({createImageSender});
if(typeof module!=="undefined"&&module.exports)module.exports=JAssistAuthenticatedTransport;
