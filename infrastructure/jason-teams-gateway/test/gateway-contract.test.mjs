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
  assert.match(source, /event: "jason_teams_runtime_failure"/);
  for (const key of [
    "status",
    "httpStatus",
    "errorCode",
    "requestId",
    "correlationId",
    "conversationId",
    "messageId",
  ]) {
    assert.match(source, new RegExp(`${key}:`));
  }
  const failureBlock = source.match(
    /event: "jason_teams_runtime_failure"[\s\S]*?\}\),\n  \);/,
  );
  assert.ok(failureBlock, "bounded runtime failure log block is required");
  for (const forbidden of [
    "text,",
    "envelope",
    "signed",
    "api_key",
    "clientSecret",
    "PRIVATE_KEY_PATH",
  ]) {
    assert.doesNotMatch(failureBlock[0], new RegExp(forbidden));
  }
});
