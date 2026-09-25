import assert from "node:assert/strict";
import test from "node:test";
import { resolveProactiveSendResult } from "../proactive-send-result.mjs";

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
