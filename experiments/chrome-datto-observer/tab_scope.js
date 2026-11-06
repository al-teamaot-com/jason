"use strict";
// Session classification is descriptive, never an authority decision.
// The active-tab permission and background origin checks remain authoritative.
const JAssistScope = Object.freeze({
  classify(url) {
    let parsed;
    try { parsed = new URL(url); } catch { return {supported:false,kind:"unsupported",label:"Unsupported page"}; }
    if (parsed.protocol !== "https:" || !/^[a-z0-9-]+\.rmm\.datto\.com$/i.test(parsed.hostname)) {
      return {supported:false,kind:"unsupported",label:"Unsupported page"};
    }
    if (parsed.pathname.startsWith("/web-remote/")) {
      if (parsed.searchParams.get("tool") === "shell") {
        return {supported:true,kind:"powershell",label:"Datto Web Remote PowerShell"};
      }
      return {supported:true,kind:"graphical",label:"Datto Web Remote (graphical or other tool)"};
    }
    return {supported:true,kind:"datto-tab",label:"Datto RMM browser tab"};
  }
});
if (typeof module !== "undefined" && module.exports) module.exports = JAssistScope;
