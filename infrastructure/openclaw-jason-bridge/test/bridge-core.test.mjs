import assert from "node:assert/strict";
import { generateKeyPairSync, verify } from "node:crypto";
import test from "node:test";

import {
  buildConversationEnvelope,
  canonicalSignedPayload,
  replyForRuntimeResult,
  signConversationEnvelope,
} from "../bridge-core.mjs";

const tenantId = "f7054323-d52b-4863-8c2f-1898f0b6077c";
const objectId = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f";

function envelope() {
  return buildConversationEnvelope({
    text: "Who is logged into AOT-50282?",
    microsoftTenantId: tenantId,
    microsoftObjectId: objectId,
    conversationId: "conversation-1",
    messageId: "message-1",
    keyId: "openclaw-gateway-2",
    now: new Date("2026-08-11T10:30:00.000Z"),
    requestId: "request-1",
    correlationId: "correlation-1",
    nonce: "00112233445566778899aabbccddeeff",
  });
}

test("builds only the governed Teams transport contract", () => {
  const value = envelope();
  assert.equal(value.kind, "conversation.turn");
  assert.equal(value.channel, "msteams");
  assert.equal(value.transport_identity.microsoft_object_id, objectId);
  assert.equal(value.transport_identity.authentication_assurance, "botframework-authenticated");
  for (const forbidden of [
    "principal_id",
    "organization_id",
    "client_id",
    "capability",
    "capability_name",
    "provider",
    "provider_id",
    "connector",
    "connector_id",
    "arguments",
    "shell",
    "target_agent",
  ]) {
    assert.equal(Object.hasOwn(value, forbidden), false, forbidden);
  }
});

test("preserves arbitrary natural-language wording without trigger phrases", () => {
  const phrasings = [
    "Who was on AOT-50282 last?",
    "Can you tell me the most recent person to use AOT-50282?",
    "What account last signed into AOT-50282?",
    "Check AOT-50282 and tell me who used it most recently.",
  ];

  for (const [index, text] of phrasings.entries()) {
    const value = buildConversationEnvelope({
      text,
      microsoftTenantId: tenantId,
      microsoftObjectId: objectId,
      conversationId: "conversation-1",
      messageId: `message-${index + 10}`,
      keyId: "openclaw-gateway-2",
    });
    assert.equal(value.text, text);
  }
});

test("signs exactly the canonical payload Jason verifies", () => {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const signed = signConversationEnvelope(envelope(), privateKey);
  assert.ok(signed.signature);
  assert.equal(
    verify(
      null,
      canonicalSignedPayload(signed),
      publicKey,
      Buffer.from(signed.signature, "base64"),
    ),
    true,
  );
});

test("canonicalization is stable across object insertion order", () => {
  const left = { z: 1, a: { y: 2, b: 3 }, signature: "ignored" };
  const right = { a: { b: 3, y: 2 }, z: 1 };
  assert.deepEqual(canonicalSignedPayload(left), canonicalSignedPayload(right));
});

test("rejects a non-AAD sender identity", () => {
  assert.throws(
    () =>
      buildConversationEnvelope({
        text: "test",
        microsoftTenantId: tenantId,
        microsoftObjectId: "opaque-botframework-user-id",
        conversationId: "conversation-1",
        messageId: "message-1",
        keyId: "openclaw-gateway-2",
      }),
    /Microsoft object id is unavailable/,
  );
});

test("never falls back to an ungoverned answer for runtime failures", () => {
  assert.match(
    replyForRuntimeResult({ httpStatus: 500, payload: { status: "failed" } }),
    /No action was taken/,
  );
  assert.match(
    replyForRuntimeResult({ httpStatus: 403, payload: { status: "denied" } }),
    /denied/i,
  );
  assert.equal(
    replyForRuntimeResult({
      httpStatus: 200,
      payload: { status: "completed", reply: { text: "Datto RMM reports Al." } },
    }),
    "Datto RMM reports Al.",
  );
});


test("renders governed clarification without inventing an answer", () => {
  const reply = replyForRuntimeResult({
    httpStatus: 200,
    payload: {
      status: "clarification_required",
      error_code: "canonical_fact_ambiguous",
      clarification: {
        text:
          "I need one detail before I can continue. Do you mean LAN IP address or WAN IP address? Please send a complete request naming the one you want.",
        candidate_facts: [
          "LAN IP address",
          "WAN IP address",
        ],
        requires_complete_request: true,
      },
    },
  });

  assert.equal(
    reply,
    "I need one detail before I can continue. Do you mean LAN IP address or WAN IP address? Please send a complete request naming the one you want.",
  );
});
