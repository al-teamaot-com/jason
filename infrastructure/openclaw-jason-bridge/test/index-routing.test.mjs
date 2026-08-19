import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../index.mjs", import.meta.url), "utf8");
const manifest = JSON.parse(
  readFileSync(new URL("../openclaw.plugin.json", import.meta.url), "utf8"),
);

test("bound Teams conversations have a phrase-agnostic pre-agent compatibility route", () => {
  assert.match(source, /"inbound_claim"/);
  assert.doesNotMatch(source, /"before_agent_run"/);
  assert.doesNotMatch(source, /"before_agent_reply"/);
  assert.match(source, /claimReply/);
  assert.match(source, /forwardGovernedTeamsTurn/);

  assert.match(source, /getCurrentPluginConversationBinding/);
  assert.match(source, /lookupCapturedWithBriefRetry/);
  assert.match(source, /forwardGovernedTeamsTurn/);
});

test("governed Teams turns remain silent until the governed final response", () => {
  assert.doesNotMatch(source, /WORKING_ACK_TEXT/);
  assert.doesNotMatch(source, /sendWorkingAcknowledgement/);
  assert.doesNotMatch(source, /Received - working on that now/);
  assert.doesNotMatch(source, /channel\.outbound\.loadAdapter\("msteams"\)/);
  assert.doesNotMatch(source, /await adapter\.sendText\(\{/);
  assert.match(source, /const envelope = buildConversationEnvelope\(\{/);
  assert.match(source, /return safeReply\(replyForRuntimeResult\(result\)\);/);
});

test("governed Teams turn timeout hierarchy leaves room for bounded Jason stages", () => {
  assert.match(source, /const DEFAULT_TIMEOUT_MS = 150_000;/);
  assert.match(source, /const MAX_TIMEOUT_MS = 170_000;/);
  assert.match(source, /const HOOK_TIMEOUT_MS = 180_000;/);
  assert.match(source, /requestTimeoutMs > MAX_TIMEOUT_MS/);
  assert.equal((source.match(/\{ timeoutMs: HOOK_TIMEOUT_MS \}/g) ?? []).length, 1);

  const timeoutSchema = manifest.configSchema.properties.requestTimeoutMs;
  assert.equal(timeoutSchema.default, 150000);
  assert.equal(timeoutSchema.maximum, 170000);
  assert.match(
    manifest.uiHints.requestTimeoutMs.help,
    /separate from the short signed-envelope freshness window/i,
  );
});

test("Teams bridge routing contains no endpoint-specific trigger phrase", () => {
  for (const forbidden of [
    "AOT-50282",
    "who is logged into",
    "last user logged",
    "most recent person",
  ]) {
    assert.equal(source.toLowerCase().includes(forbidden.toLowerCase()), false, forbidden);
  }
});
