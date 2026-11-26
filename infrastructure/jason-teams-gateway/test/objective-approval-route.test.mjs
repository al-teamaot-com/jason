import test from "node:test";
import assert from "node:assert/strict";
import { objectiveApprovalRuntimeUrl as route } from "../objective-approval-route.mjs";

const legacy = "http://jason-runtime:8080/v1/openclaw/teams/conversation";
const objective = "http://jason-owner-objective:8097/v1/openclaw/teams/conversation";
const id = "planapproval-objective-" + "a".repeat(32);

test("ordinary messages and existing approval families retain their route", () => {
  for (const approvalId of [undefined, "relapproval-a", "planapproval-old", "procurement-a"]) {
    assert.equal(route({ approvalId, runtimeUrl: legacy, objectiveUrl: objective }), legacy);
  }
});

test("an exact objective card uses only the configured isolated component", () => {
  assert.equal(route({ approvalId: id, runtimeUrl: legacy, objectiveUrl: objective }), objective);
});

test("an unavailable objective component cannot silently become a legacy approval", () => {
  assert.throws(() => route({ approvalId: id, runtimeUrl: legacy }));
});

test("malformed identifiers and unregistered destinations fail closed", () => {
  for (const approvalId of ["planapproval-objective-latest", id + "/extra"]) {
    assert.throws(() => route({ approvalId, runtimeUrl: legacy, objectiveUrl: objective }));
  }
  for (const objectiveUrl of [
    "https://external.example/v1/openclaw/teams/conversation",
    "http://jason-owner-objective:8097/other",
    objective + "?override=true",
    "http://user:pass@jason-owner-objective:8097/v1/openclaw/teams/conversation",
  ]) assert.throws(() => route({ approvalId: id, runtimeUrl: legacy, objectiveUrl }));
});
