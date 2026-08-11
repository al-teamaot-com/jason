import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../index.mjs", import.meta.url), "utf8");

test("bound Teams conversations have a phrase-agnostic pre-agent compatibility route", () => {
  assert.match(source, /"before_agent_reply"/);
  assert.match(source, /getCurrentPluginConversationBinding/);
  assert.match(source, /lookupCapturedWithBriefRetry/);
  assert.match(source, /forwardGovernedTeamsTurn/);
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
