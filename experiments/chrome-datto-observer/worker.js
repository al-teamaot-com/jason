"use strict";
const sessions = new Map();
const allowed = url => /^https:\/\/[a-z0-9-]+\.rmm\.datto\.com\//i.test(url || "");
chrome.action.onClicked.addListener(async tab => {
  if (!tab.id || !allowed(tab.url)) return;
  await chrome.sidePanel.open({tabId: tab.id});
});
chrome.runtime.onMessage.addListener((msg, sender, respond) => {
  (async () => {
    if (msg.type === "start") {
      const tab = await chrome.tabs.get(msg.tabId);
      if (!allowed(tab.url)) throw Error("Not a supported Datto RMM tab.");
      const active = await chrome.tabs.query({active:true, currentWindow:true});
      if (active[0]?.id !== tab.id) throw Error("Select the Datto RMM tab before starting.");
      sessions.set(tab.id, {started:Date.now(),windowId:tab.windowId});
      return {ok:true, tabTitle:tab.title, note:"Full visible browser tab; local only."};
    }
    if (msg.type === "stop") {
      sessions.delete(msg.tabId);
      return {ok:true};
    }
    if (msg.type === "capture") {
      const s = sessions.get(msg.tabId);
      if (!s) throw Error("Observation is stopped.");
      const tab = await chrome.tabs.get(msg.tabId);
      if (!allowed(tab.url) || tab.windowId !== s.windowId) {sessions.delete(msg.tabId);throw Error("Session no longer matches the authorized Datto tab.");}
      const active = await chrome.tabs.query({active:true, windowId:s.windowId});
      if (active[0]?.id !== tab.id) throw Error("Observation paused: Datto tab is not active.");
      const dataUrl = await chrome.tabs.captureVisibleTab(s.windowId,{format:"jpeg",quality:60});
      if (!sessions.has(msg.tabId)) throw Error("Session stopped before preview delivery.");
      return {ok:true,image:dataUrl,capturedAt:new Date().toISOString()};
    }
    throw Error("Unknown request.");
  })().then(respond, error => respond({ok:false,error:String(error.message || error)}));
  return true;
});
chrome.tabs.onRemoved.addListener(id => sessions.delete(id));
chrome.tabs.onUpdated.addListener((id,changes) => { if (changes.url && !allowed(changes.url)) sessions.delete(id); });
