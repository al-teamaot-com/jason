"use strict";
const start=document.querySelector("#start"),stop=document.querySelector("#stop"),status=document.querySelector("#status"),stamp=document.querySelector("#stamp"),frame=document.querySelector("#frame");
let tabId=null, timer=null, running=false, pending=false;
const request = m => chrome.runtime.sendMessage(m);
const setStatus = s => {status.textContent=s;};
async function capture(){
  if(!running||pending)return;
  pending=true;
  try{
    const r=await request({type:"capture",tabId});
    if(!running)return;
    if(!r.ok){setStatus(r.error);return;}
    frame.src=r.image;frame.hidden=false;stamp.textContent="Local frame: "+new Date(r.capturedAt).toLocaleTimeString();setStatus("Observing — local preview only");
  }catch(e){setStatus("Observation error: "+e.message);}finally{pending=false;}
}
async function halt(){
  running=false;clearInterval(timer);timer=null;
  if(tabId!==null)await request({type:"stop",tabId}).catch(()=>{});
  start.disabled=false;stop.disabled=true;frame.removeAttribute("src");frame.hidden=true;stamp.textContent="No retained frame";setStatus("Stopped");
}
start.addEventListener("click",async()=>{
  try{
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!tab?.id)throw Error("No active tab.");
    tabId=tab.id;
    const result=await request({type:"start",tabId});
    if(!result.ok)throw Error(result.error);
    running=true;start.disabled=true;stop.disabled=false;
    await capture();timer=setInterval(capture,2000);
  }catch(e){setStatus("Cannot start: "+e.message);}
});
stop.addEventListener("click",halt);
window.addEventListener("pagehide",()=>{if(tabId!==null)request({type:"stop",tabId}).catch(()=>{});});
