import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../index.mjs", import.meta.url),
  "utf8",
);

test("direct Teams gateway emits no canned working acknowledgement", () => {
  assert.doesNotMatch(source, /Received - working on that now/);
  assert.doesNotMatch(source, /WORKING_ACK_TEXT/);
});

test("runtime result path sends one final Teams response", () => {
  const resultSend = source.match(
    /await context\.sendActivity\(replyForRuntimeResult\(result\)\);/g,
  );
  assert.equal(resultSend?.length ?? 0, 1);
});

test("failed runtime responses log only bounded correlation metadata", () => {
  const failureBlock = source.match(
    /event: "jason_teams_runtime_failure"[\s\S]*?\}\),\n  \);/,
  );
  assert.ok(failureBlock, "bounded runtime failure log block is required");

  for (const field of [
    /status:/,
    /httpStatus:/,
    /errorCode:/,
    /requestId:/,
    /correlationId:/,
    /conversationId,/, 
    /messageId,/, 
  ]) {
    assert.match(failureBlock[0], field);
  }

  for (const forbidden of [
    /\btext\b/,
    /\benvelope\b/,
    /\bsigned\b/,
    /api_key/,
    /clientSecret/,
    /PRIVATE_KEY_PATH/,
  ]) {
    assert.doesNotMatch(failureBlock[0], forbidden);
  }
});

test("approval card submit path supports request_changes and signs structured interaction", () => {
  assert.match(source, /"approve", "deny", "request_changes"/);
  assert.match(source, /kind: "approval\.submit"/);
  assert.match(source, /channel_response_id: messageId/);
});

test("proactive preflight diagnostics expose bounded reason codes without secrets", () => {
  for (const code of [
    "unauthorized",
    "invalid_request",
    "tenant_mismatch",
    "app_not_published",
    "stored_tenant_mismatch",
  ]) {
    assert.match(source, new RegExp(`jason_teams_proactive_rejected[^\\n]*${code}`));
  }
  assert.match(source, /jason_teams_proactive_preflight_passed/);
  const diagnosticLines = source
    .split("\n")
    .filter((line) => line.includes("jason_teams_proactive_rejected") || line.includes("jason_teams_proactive_preflight_passed"))
    .join("\n");
  assert.doesNotMatch(diagnosticLines, /PROACTIVE_TOKEN|authorization|clientSecret|message|card|text/);
});


test("hardware billing disposition card is constrained and signed as a governed interaction", () => {
  assert.match(source, /function parseBillingDispositionSubmit/);
  assert.match(source, /"charge_needed", "not_billable", "already_handled"/);
  assert.match(source, /kind: "hardware\.billing\.disposition"/);
  assert.match(source, /case_key: billingDispositionSubmit\.caseKey/);
  assert.match(source, /disposition: billingDispositionSubmit\.disposition/);
  assert.match(source, /channel_response_id: messageId/);
});
