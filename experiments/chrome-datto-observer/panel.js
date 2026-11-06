"use strict";
const start=document.querySelector("#start"),stop=document.querySelector("#stop"),status=document.querySelector("#status"),stamp=document.querySelector("#stamp"),frame=document.querySelector("#frame");
let tabId=null,sessionId=null,timer=null,running=false,pending=false;
const scope=document.querySelector("#scope");
const request=m=>chrome.runtime.sendMessage(m);
const setStatus=s=>{status.textContent=s;};
const clearPreview=()=>{frame.removeAttribute("src");frame.hidden=true;stamp.textContent="No retained frame";};
function endLocally(message){
  running=false;clearInterval(timer);timer=null;sessionId=null;
  start.disabled=false;stop.disabled=true;clearPreview();scope.textContent="No active assistance session";setStatus(message);
}
async function capture(){
  if(!running||pending)return;
  pending=true;
  try{
    const id=sessionId;
    const r=await request({type:"capture",tabId,sessionId:id});
    if(!running||id!==sessionId)return;
    if(r.ended){endLocally(r.error||"Observation ended.");return;}
    if(r.paused){clearPreview();setStatus(r.error||"Paused");return;}
    if(!r.ok){clearPreview();setStatus("Capture error: "+r.error);return;}
    frame.src=r.image;frame.hidden=false;stamp.textContent="Local frame: "+new Date(r.capturedAt).toLocaleTimeString();setStatus("Preview active — local only");
  }catch(e){if(running){clearPreview();setStatus("Capture error: "+e.message);}}
  finally{pending=false;}
}
async function halt(){
  const endingTab=tabId;
  endLocally("Stopped");
  if(endingTab!==null)await request({type:"stop",tabId:endingTab}).catch(()=>{});
}
start.addEventListener("click",async()=>{
  start.disabled=true;
  try{
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!tab?.id)throw Error("No active browser tab.");
    const selected=JAssistScope.classify(tab.url||"");
    if(!selected.supported)throw Error("Select an authorized Datto Web Remote or Datto RMM browser tab, then click Start.");
    scope.textContent="Assisting: "+selected.label;
    tabId=tab.id;
    const r=await request({type:"start",tabId});
    if(!r.ok)throw Error(r.error);
    sessionId=r.sessionId;running=true;stop.disabled=false;
    await capture();if(running)timer=setInterval(capture,2000);
  }catch(e){endLocally("Cannot start: "+e.message);}
});
stop.addEventListener("click",halt);
window.addEventListener("pagehide",()=>{
  if(tabId!==null)request({type:"stop",tabId}).catch(()=>{});
});
