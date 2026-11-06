"use strict";
const sessions = new Map();
let nextSessionId = 0;
const allowed = url => /^https:\/\/[a-z0-9-]+\.rmm\.datto\.com\//i.test(url || "");
chrome.action.onClicked.addListener(async tab => {
  if (!tab.id || !allowed(tab.url)) return;
  await chrome.sidePanel.open({tabId:tab.id});
});
chrome.runtime.onMessage.addListener((msg,sender,respond) => {
  (async()=>{
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
      sessions.delete(msg.tabId);
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
