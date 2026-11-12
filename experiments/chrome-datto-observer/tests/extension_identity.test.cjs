"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const crypto=require("node:crypto");
const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,"..","manifest.json"),"utf8"));
test("preproduction Chrome ID is pinned by public manifest key and survives install path changes",()=>{
 assert.equal(manifest.version,"0.2.1");
 const publicDer=Buffer.from(manifest.key,"base64");
 assert.ok(publicDer.length>=250);
 const digest=crypto.createHash("sha256").update(publicDer).digest().subarray(0,16);
 const extensionId=[...digest].map(x=>String.fromCharCode(97+(x>>>4))+String.fromCharCode(97+(x&15))).join("");
 assert.equal(extensionId,"pihjpgplfhmpenlghbcdbgdkadleflfi");
 assert.equal("https://"+extensionId+".chromiumapp.org/jassist",
              "https://pihjpgplfhmpenlghbcdbgdkadleflfi.chromiumapp.org/jassist");
 assert.ok(manifest.permissions.includes("identity")); // explicit sign-in only
 assert.deepEqual(manifest.host_permissions,[
   "https://login.microsoftonline.com/*",
   "https://mcp-jason.teamaot.com/*",
 ]);
 assert.ok(!manifest.host_permissions.some(x=>x==="https://*/*"));
 assert.ok(!manifest.host_permissions.some(x=>x.includes("rmm.datto.com")));
});
