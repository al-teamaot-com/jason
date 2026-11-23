import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { createApprovalDecisionStore } from "../approval-decision-store.mjs";

function fixture() {
  const dir = mkdtempSync(join(tmpdir(), "jason-approval-store-"));
  const path = join(dir, "approval-decisions.json");
  const times = [
    new Date("2026-09-25T17:10:00Z"),
    new Date("2026-09-25T17:10:01Z"),
  ];
  return {
    path,
    store: createApprovalDecisionStore({ path, now: () => times.shift() ?? new Date("2026-09-25T17:10:02Z") }),
  };
}

test("first approval decision wins and conflicting second click is blocked", () => {
  const { store } = fixture();
  const first = store.begin({
    tenantId: "tenant-a",
    approvalId: "approval-1",
    aadObjectId: "user-a",
    decision: "deny",
    messageId: "message-1",
  });
  assert.equal(first.accepted, true);
  store.finalize({ tenantId: "tenant-a", approvalId: "approval-1", resultStatus: "completed" });

  const second = store.begin({
    tenantId: "tenant-a",
    approvalId: "approval-1",
    aadObjectId: "user-a",
    decision: "approve",
    messageId: "message-2",
  });
  assert.equal(second.accepted, false);
  assert.equal(second.record.decision, "deny");
  assert.equal(second.record.state, "decided");
});

test("processing claim survives restart and blocks a retry with uncertain outcome", () => {
  const { path, store } = fixture();
  store.begin({
    tenantId: "tenant-a",
    approvalId: "approval-2",
    aadObjectId: "user-a",
    decision: "approve",
    messageId: "message-1",
  });

  const reopened = createApprovalDecisionStore({ path });
  const retry = reopened.begin({
    tenantId: "tenant-a",
    approvalId: "approval-2",
    aadObjectId: "user-a",
    decision: "approve",
    messageId: "message-2",
  });
  assert.equal(retry.accepted, false);
  assert.equal(retry.record.state, "processing");
  assert.equal(retry.record.decision, "approve");

  const persisted = JSON.parse(readFileSync(path, "utf8"));
  assert.equal(Object.keys(persisted).length, 1);
});

test("definitively unauthorized claim can be released for the real owner", () => {
  const dir = mkdtempSync(join(tmpdir(), "jason-approval-release-"));
  const path = join(dir, "decisions.json");
  try {
    const store = createApprovalDecisionStore({ path });
    const first = store.begin({
      tenantId: "tenant-1",
      approvalId: "approval-1",
      aadObjectId: "tech-object",
      decision: "approve",
      messageId: "message-tech",
    });
    assert.equal(first.accepted, true);
    store.release({
      tenantId: "tenant-1",
      approvalId: "approval-1",
      aadObjectId: "tech-object",
      decision: "approve",
    });
    const owner = store.begin({
      tenantId: "tenant-1",
      approvalId: "approval-1",
      aadObjectId: "owner-object",
      decision: "approve",
      messageId: "message-owner",
    });
    assert.equal(owner.accepted, true);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("release refuses a mismatched sender or decision", () => {
  const dir = mkdtempSync(join(tmpdir(), "jason-approval-release-scope-"));
  const path = join(dir, "decisions.json");
  try {
    const store = createApprovalDecisionStore({ path });
    store.begin({
      tenantId: "tenant-1",
      approvalId: "approval-1",
      aadObjectId: "tech-object",
      decision: "approve",
      messageId: "message-tech",
    });
    assert.throws(() => store.release({
      tenantId: "tenant-1",
      approvalId: "approval-1",
      aadObjectId: "other-object",
      decision: "approve",
    }), /scope mismatch/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('communication receipts survive restart and suppress duplicate provider sends',()=>{
  const {path,store}=fixture();
  const scope={tenantId:'tenant-a',aadObjectId:'user-a',communicationId:'comm-'+ 'a'.repeat(64),payloadDigest:'b'.repeat(64)};
  assert.equal(store.beginSend(scope).accepted,true);
  const result={status:'succeeded',message_id:'real-provider-id',message_id_synthetic:false};
  store.completeSend({...scope,result});
  const recovered=createApprovalDecisionStore({path});
  assert.equal(recovered.beginSend(scope).accepted,false);
  assert.deepEqual(recovered.sendReceipt(scope).result,result);
  assert.throws(()=>recovered.beginSend({...scope,payloadDigest:'c'.repeat(64)}),/scope changed/);
  assert.equal(recovered.sendReceipt({...scope,aadObjectId:'different-user'}),null);
});

test('unknown interrupted provider attempt remains blocked without a made-up receipt',()=>{
  const {path,store}=fixture();
  const scope={tenantId:'tenant-a',aadObjectId:'user-a',communicationId:'comm-'+ 'c'.repeat(64),payloadDigest:'b'.repeat(64)};
  assert.equal(store.beginSend(scope).accepted,true);
  const recovered=createApprovalDecisionStore({path});
  const retry=recovered.beginSend(scope);
  assert.equal(retry.accepted,false);
  assert.equal(retry.record.state,'processing');
  assert.equal(recovered.sendReceipt(scope).result,undefined);
});
