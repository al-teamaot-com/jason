import assert from "node:assert/strict";
import test from "node:test";
import { buildProactiveActivity, resolveProactiveSendResult } from "../proactive-send-result.mjs";

test("uses real provider message id when present", () => {
  const r = resolveProactiveSendResult({ result: { id: "msg-1" }, isCard: true });
  assert.deepEqual(r, {
    messageId: "msg-1",
    evidenceType: "provider_message_id",
    synthetic: false,
  });
});

test("card send without message id returns bounded provider-acceptance receipt", () => {
  const r = resolveProactiveSendResult({
    result: undefined,
    isCard: true,
    receiptFactory: () => "receipt-1",
  });
  assert.deepEqual(r, {
    messageId: "accepted:receipt-1",
    evidenceType: "provider_call_completed_without_message_id",
    synthetic: true,
  });
});

test("plain text send without message id still fails closed", () => {
  assert.equal(resolveProactiveSendResult({ result: undefined, isCard: false }), null);
});


test("approval card is one attachment-only activity, not text plus card", () => {
  const card = Object.freeze({
    type: "AdaptiveCard", version: "1.4",
    body: [{ type: "TextBlock", text: "Review the exact action" }],
    actions: [{ type: "Action.Submit", title: "Approve",
      data: { approval_id: "test-request", decision: "approve", card_challenge: "test-proof" } }],
  });
  const activity = buildProactiveActivity("Approval required", card);
  assert.equal(activity.type, "message");
  assert.equal(Object.hasOwn(activity, "text"), false);
  assert.equal(activity.summary, "Approval required");
  assert.equal(activity.attachments.length, 1);
  assert.equal(activity.attachments[0].contentType, "application/vnd.microsoft.card.adaptive");
  assert.equal(activity.attachments[0].content, card);
  assert.equal(activity.attachments[0].content.actions[0].data.card_challenge, "test-proof");
});

test("text-only notification is unchanged and has no synthetic card", () => {
  assert.equal(buildProactiveActivity("Plain notification", null), "Plain notification");
  assert.equal(buildProactiveActivity("Plain notification", undefined), "Plain notification");
});

test("single-card response keeps genuine provider identity and unknown remains unknown", () => {
  const activity = buildProactiveActivity("Approval", { type: "AdaptiveCard", body: [] });
  assert.equal(Object.hasOwn(activity,"text"),false);
  assert.equal(resolveProactiveSendResult({ result: { id: "1792855000000" }, isCard: true }).synthetic,false);
  const unknown=resolveProactiveSendResult({ result: undefined, isCard: true, receiptFactory:()=>"unknown" });
  assert.equal(unknown.synthetic,true);
  assert.equal(unknown.evidenceType,"provider_call_completed_without_message_id");
});
