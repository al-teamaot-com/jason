import { createPrivateKey, randomBytes, randomUUID, sign } from "node:crypto";
import { readFileSync } from "node:fs";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value !== null && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) {
      out[key] = canonicalize(value[key]);
    }
    return out;
  }
  return value;
}

export function canonicalSignedPayload(envelope) {
  const unsigned = {};
  for (const [key, value] of Object.entries(envelope)) {
    if (key !== "signature") {
      unsigned[key] = value;
    }
  }
  return Buffer.from(JSON.stringify(canonicalize(unsigned)), "utf8");
}

export function buildConversationEnvelope({
  text,
  microsoftTenantId,
  microsoftObjectId,
  conversationId,
  messageId,
  keyId,
  now = new Date(),
  ttlMs = 30_000,
  requestId = randomUUID(),
  correlationId = randomUUID(),
  nonce = randomBytes(16).toString("hex"),
}) {
  const cleanText = String(text ?? "").trim();
  const cleanTenant = String(microsoftTenantId ?? "").trim();
  const cleanObject = String(microsoftObjectId ?? "").trim();
  const cleanConversation = String(conversationId ?? "").trim();
  const cleanMessage = String(messageId ?? "").trim();
  const cleanKeyId = String(keyId ?? "").trim();

  if (!cleanText) throw new Error("message text is required");
  if (!UUID_RE.test(cleanTenant)) throw new Error("Microsoft tenant id is invalid");
  if (!UUID_RE.test(cleanObject)) throw new Error("Microsoft object id is unavailable");
  if (!cleanConversation) throw new Error("conversation id is required");
  if (!cleanMessage) throw new Error("message id is required");
  if (!cleanKeyId) throw new Error("transport key id is required");
  if (!(now instanceof Date) || Number.isNaN(now.getTime())) throw new Error("current time is invalid");
  if (!Number.isFinite(ttlMs) || ttlMs <= 0 || ttlMs > 60_000) throw new Error("request ttl is invalid");

  const expires = new Date(now.getTime() + ttlMs);
  return {
    kind: "conversation.turn",
    channel: "msteams",
    request_id: String(requestId),
    correlation_id: String(correlationId),
    issued_at: now.toISOString(),
    expires_at: expires.toISOString(),
    nonce: String(nonce),
    text: cleanText,
    transport_identity: {
      microsoft_tenant_id: cleanTenant,
      microsoft_object_id: cleanObject,
      authentication_assurance: "botframework-authenticated",
    },
    conversation_id: cleanConversation,
    message_id: cleanMessage,
    key_id: cleanKeyId,
  };
}

export function signConversationEnvelope(envelope, privateKeyPem) {
  const key = createPrivateKey(privateKeyPem);
  const signature = sign(null, canonicalSignedPayload(envelope), key).toString("base64");
  return { ...envelope, signature };
}

export function loadAndSignConversationEnvelope(envelope, privateKeyPath) {
  const pem = readFileSync(privateKeyPath);
  return signConversationEnvelope(envelope, pem);
}

export async function postConversationEnvelope({ runtimeUrl, envelope, timeoutMs = 30_000, fetchImpl = fetch }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(runtimeUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(envelope),
      signal: controller.signal,
    });
    let payload;
    try {
      payload = await response.json();
    } catch {
      payload = { status: "failed", error_code: "invalid_runtime_response" };
    }
    return { httpStatus: response.status, payload };
  } finally {
    clearTimeout(timer);
  }
}

export function replyForRuntimeResult(result) {
  const payload = result?.payload;
  if (!payload || typeof payload !== "object") {
    return "Jason could not safely process that request. No action was taken.";
  }
  if (payload.status === "completed") {
    const text = payload.reply?.text;
    if (typeof text === "string" && text.trim()) {
      return text.trim();
    }
    return "Jason completed the request but did not return a usable response.";
  }
  if (payload.status === "approval_required") {
    return "Jason requires approval before this request can continue.";
  }
  if (payload.status === "denied") {
    return "Jason denied this request under the current authority and policy.";
  }
  if (payload.status === "rejected") {
    return "Jason rejected this request because its governed transport or request contract could not be validated.";
  }
  return "Jason could not safely process that request. No action was taken.";
}

export function isUuid(value) {
  return UUID_RE.test(String(value ?? "").trim());
}
