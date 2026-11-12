"use strict";
// Explicitly isolated interactive AOT Entra sign-in pilot. This worker
// never sends screen content or returns access tokens to a panel/page.
if (typeof importScripts === "function") importScripts("entra_pkce.js","send_once.js","authenticated_transport.js","live_send_bridge.js");
let signInInProgress = false;
let aotSendToken = null; // worker-memory only; never persisted in Chrome storage
const liveSendFactory = globalThis.JAssistLiveBridgeFactory;
if (liveSendFactory?.createLiveSendBridge) {
  globalThis.JAssistLiveSendBridge = liveSendFactory.createLiveSendBridge({
    chromeApi:chrome,
    tokenForSend:async()=>aotSendToken,
  });
}
let sendInProgress = false;
const sessions = new Map();
let nextSessionId = 0;
const allowed = url => /^https:\/\/[a-z0-9-]+\.rmm\.datto\.com\//i.test(url || "");
chrome.action.onClicked.addListener(async tab => {
  if (!tab.id || !allowed(tab.url)) return;
  await chrome.sidePanel.open({tabId:tab.id});
});
chrome.runtime.onMessage.addListener((msg,sender,respond) => {
  (async()=>{
    if (msg?.type === "test-entra-signin") {
      // Never authorize an OAuth flow initiated by a Datto webpage,
      // arbitrary extension message or unrelated browser surface.
      if (typeof chrome.runtime.getURL !== "function" ||
          sender.id !== chrome.runtime.id ||
          sender.url !== chrome.runtime.getURL("panel.html")) {
        throw Error("Only the J-Assist panel can initiate technician sign-in.");
      }
      if (signInInProgress) throw Error("An AOT sign-in attempt is already active.");
      const adapter = globalThis.JAssistEntraPkce;
      if (!adapter || !chrome.identity?.launchWebAuthFlow) {
        throw Error("AOT Entra sign-in is not available in this build.");
      }
      signInInProgress = true;
      try {
        const auth = adapter.createEntraPkce({
          tenantId:adapter.AOT_ENTRA_TENANT_ID,
          clientId:adapter.AOT_PILOT_CLIENT_ID,
          scope:adapter.JASSIST_SEND_SCOPE,
          chromeIdentity:chrome.identity,
        });
        const signedIn = await auth.authorizeInteractive();
        // Bearer stays in the extension service-worker's volatile memory.
        // Neither this result nor panel/Datto DOM receives it. Sign-in is
        // not authority to capture or send; server readiness remains mandatory.
        if (!signedIn?.accessToken) throw Error("AOT sign-in was not completed.");
        if (!Number.isFinite(signedIn.expiresIn) || signedIn.expiresIn < 60) {
          // Old test stubs may omit lifetime; they may sign in for the
          // isolated pilot but cannot unlock the live upload.
          aotSendToken=null;
        } else {
          aotSendToken={token:signedIn.accessToken,
                        expiresAt:Date.now()+signedIn.expiresIn*1000};
        }
        return {ok:true,loginFlowCompleted:true,jasonAuthorizationVerified:false,
                uploadEnabled:false};
      } finally {
        signInInProgress = false;
      }
    }
    if (msg?.type === "send-readiness" || msg?.type === "send-to-jason") {
      // Only a technician's extension panel may request a send. Never accept
      // identity, device, a token, a destination or image bytes from the panel.
      if (sender?.id !== chrome.runtime.id ||
          sender?.url !== chrome.runtime.getURL("panel.html")) {
        throw Error("Only the J-Assist panel can request evidence delivery.");
      }
      const session=sessions.get(msg.tabId);
      if (!session || session.id !== msg.sessionId) {
        throw Error("Start an authorized Datto assistance session first.");
      }
      const live=globalThis.JAssistLiveSendBridge;
      if (!live || typeof live.readiness !== "function" ||
          typeof live.dependencies !== "function" ||
          !globalThis.JAssistOneClick?.sendOnce) {
        return {ok:false,ready:false,error:"Governed Jason send service is not connected."};
      }
      // A readiness response is advisory; sendOnce independently rechecks
      // all authority before capturing any image.
      if (msg.type === "send-readiness") {
        const ready=await live.readiness({tabId:msg.tabId,sessionId:session.id});
        return {ok:ready===true,ready:ready===true};
      }
      if (sendInProgress) throw Error("A J-Assist send is already in progress.");
      sendInProgress=true;
      try {
        const deps=await live.dependencies({tabId:msg.tabId,sessionId:session.id});
        return await globalThis.JAssistOneClick.sendOnce(deps);
      } finally { sendInProgress=false; }
    }
    if (msg.type === "start") {
      const tab = await chrome.tabs.get(msg.tabId);
      if (!allowed(tab.url)) throw Error("Not a supported Datto RMM tab.");
      const active = await chrome.tabs.query({active:true,windowId:tab.windowId});
      if (active[0]?.id !== tab.id) throw Error("Select the Datto RMM tab before starting.");
      const id=++nextSessionId;
      sessions.set(tab.id,{id,url:tab.url,windowId:tab.windowId});
      return {ok:true,sessionId:id,tabTitle:tab.title};
    }
    if (msg.type === "stop") {
      // Revoke server-side session as well as local capture. Revoke is
      // best-effort; the server must always enforce short TTL and checks.
      const existing=sessions.get(msg.tabId);
      sessions.delete(msg.tabId);
      if(existing) await globalThis.JAssistLiveSendBridge?.revoke?.({
        tabId:msg.tabId}).catch(()=>{});
      return {ok:true};
    }
    if (msg.type === "capture") {
      const s=sessions.get(msg.tabId);
      if (!s || s.id!==msg.sessionId) return {ok:false,ended:true,error:"Observation ended; click Start to begin a new session."};
      let tab;
      try { tab=await chrome.tabs.get(msg.tabId); }
      catch {sessions.delete(msg.tabId);return {ok:false,ended:true,error:"Observed tab was closed."};}
      if(!allowed(tab.url)||tab.url!==s.url||tab.windowId!==s.windowId){
        sessions.delete(msg.tabId);
        return {ok:false,ended:true,error:"Observation ended after navigation; click Start again."};
      }
      const active=await chrome.tabs.query({active:true,windowId:s.windowId});
      if(active[0]?.id!==tab.id) return {ok:false,paused:true,error:"Paused — Datto tab is not active."};
      const image=await chrome.tabs.captureVisibleTab(s.windowId,{format:"jpeg",quality:60});
      const still=sessions.get(msg.tabId);
      if(!still||still.id!==s.id) return {ok:false,ended:true,error:"Observation was stopped."};
      const after=await chrome.tabs.get(msg.tabId).catch(()=>null);
      if(!after||after.url!==s.url||after.windowId!==s.windowId){
        sessions.delete(msg.tabId);
        return {ok:false,ended:true,error:"Observation ended after navigation."};
      }
      const activeAfter=await chrome.tabs.query({active:true,windowId:s.windowId});
      if(activeAfter[0]?.id!==tab.id) return {ok:false,paused:true,error:"Paused — Datto tab is not active."};
      return {ok:true,image,capturedAt:new Date().toISOString()};
    }
    throw Error("Unknown request.");
  })().then(respond,error=>respond({ok:false,error:String(error.message||error)}));
  return true;
});
chrome.tabs.onRemoved.addListener(id=>sessions.delete(id));
chrome.tabs.onUpdated.addListener((id,changes)=>{
  const s=sessions.get(id);
  if(s && changes.url && changes.url!==s.url) sessions.delete(id);
});
