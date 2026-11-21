"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const scope=require("../tab_scope.js");
test("classifies the technician's Datto PowerShell page",()=>{
 const value=scope.classify("https://vidal.rmm.datto.com/web-remote/1717088?tool=shell&windowsSessionId=1");
 assert.equal(value.kind,"powershell"); assert.equal(value.supported,true);
});
test("classifies non-shell Web Remote page as potentially graphical",()=>{
 const value=scope.classify("https://vidal.rmm.datto.com/web-remote/1717088");
 assert.equal(value.kind,"graphical"); assert.equal(value.supported,true);
});
test("classifies Datto device UI without claiming it is remote desktop",()=>{
 const value=scope.classify("https://vidal.rmm.datto.com/device/1717088/al-samsung");
 assert.equal(value.kind,"datto-tab");
});
test("rejects lookalikes, non-HTTPS and arbitrary tabs",()=>{
 for(const url of ["https://vidal.rmm.datto.com.bad.example/web-remote/1", "http://vidal.rmm.datto.com/web-remote/1", "https://example.com", "chrome://extensions", "not a URL"]){
  assert.equal(scope.classify(url).supported,false,url);
 }
});
