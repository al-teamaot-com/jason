import { pathToFileURL } from "node:url";

const DEFAULT_RUNTIME_URL = "http://jason-runtime:8080/v1/openclaw/teams/conversation";
const DEFAULT_KEY_ID = "openclaw-gateway-2";
const DEFAULT_PRIVATE_KEY_PATH =
  "/home/node/.config/openclaw/jason-ingress/openclaw-jason-ed25519-v2.pem";
const DEFAULT_TIMEOUT_MS = 150_000;
const MAX_TIMEOUT_MS = 170_000;
const DEFAULT_BRIDGE_CORE_PATH =
  "/home/node/.openclaw/extensions/jason-bridge/bridge-core.mjs";
const WORKING_ACK_TEXT = "Received - working on that now...";
const SAFE_FAILURE_TEXT = "Jason could not safely process that request. No action was taken.";

function asObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function nonBlank(value) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export function resolveJasonTeamsTransportConfig(cfg) {
  const root = asObject(cfg);
  const channels = asObject(root.channels);
  const teams = asObject(channels.msteams);
  const plugins = asObject(root.plugins);
  const entries = asObject(plugins.entries);
  const bridgeEntry = asObject(entries["jason-bridge"]);
  const bridge = asObject(bridgeEntry.config);

  const teamsTenantId = nonBlank(teams.tenantId);
  const microsoftTenantId = nonBlank(bridge.microsoftTenantId) ?? teamsTenantId;
  if (!microsoftTenantId) {
    throw new Error("Jason Teams transport requires a Microsoft tenant id");
  }
  if (
    teamsTenantId &&
    teamsTenantId.toLowerCase() !== microsoftTenantId.toLowerCase()
  ) {
    throw new Error("Microsoft Teams tenant does not match Jason transport tenant");
  }

  const requestTimeoutMs = Number(bridge.requestTimeoutMs ?? DEFAULT_TIMEOUT_MS);
  if (
    !Number.isFinite(requestTimeoutMs) ||
    requestTimeoutMs < 1000 ||
    requestTimeoutMs > MAX_TIMEOUT_MS
  ) {
    throw new Error("Jason Teams transport request timeout is invalid");
  }

  return {
    microsoftTenantId,
    runtimeUrl: nonBlank(bridge.runtimeUrl) ?? DEFAULT_RUNTIME_URL,
    keyId: nonBlank(bridge.keyId) ?? DEFAULT_KEY_ID,
    privateKeyPath: nonBlank(bridge.privateKeyPath) ?? DEFAULT_PRIVATE_KEY_PATH,
    requestTimeoutMs,
    bridgeCorePath:
      nonBlank(process.env.JASON_BRIDGE_CORE_PATH) ?? DEFAULT_BRIDGE_CORE_PATH,
  };
}

async function sendActivity(context, text, log) {
  try {
    await context.sendActivity(text);
    return true;
  } catch (error) {
    log?.warn?.("jason-teams-transport: Teams reply delivery failed", {
      error: String(error?.message ?? error),
    });
    return false;
  }
}

async function loadBridgeCore(path) {
  return import(pathToFileURL(path).href);
}

export async function dispatchJasonGovernedTeamsTurn({
  cfg,
  context,
  activity,
  text,
  senderId,
  conversationId,
  log,
}) {
  const cleanText = nonBlank(text);

  // Explicit OpenClaw commands remain available. Ordinary Teams conversation
  // traffic is owned by Jason and never enters the OpenClaw agent loop.
  if (cleanText?.startsWith("/")) {
    return { handled: false, finalResponses: 0 };
  }

  log?.info?.(
    "jason-teams-transport: intercepting Teams turn before OpenClaw agent dispatch",
  );

  let config;
  try {
    config = resolveJasonTeamsTransportConfig(cfg);
  } catch (error) {
    log?.error?.("jason-teams-transport: invalid governed transport configuration", {
      error: String(error?.message ?? error),
    });
    const delivered = await sendActivity(
      context,
      "Jason is not available because its governed transport configuration is invalid.",
      log,
    );
    return { handled: true, finalResponses: delivered ? 1 : 0 };
  }

  try {
    const bridgeCore = await loadBridgeCore(config.bridgeCorePath);
    const cleanSenderId = nonBlank(senderId);
    const cleanConversationId = nonBlank(conversationId);
    const cleanMessageId = nonBlank(activity?.id);

    if (!cleanText) {
      const delivered = await sendActivity(
        context,
        "Jason currently requires a text request for this governed conversation path.",
        log,
      );
      return { handled: true, finalResponses: delivered ? 1 : 0 };
    }
    if (!cleanSenderId || !bridgeCore.isUuid(cleanSenderId)) {
      const delivered = await sendActivity(
        context,
        "Jason could not validate your Microsoft identity for this request.",
        log,
      );
      return { handled: true, finalResponses: delivered ? 1 : 0 };
    }
    if (!cleanConversationId || !cleanMessageId) {
      const delivered = await sendActivity(
        context,
        "Jason could not validate the conversation context for this request.",
        log,
      );
      return { handled: true, finalResponses: delivered ? 1 : 0 };
    }

    await sendActivity(context, WORKING_ACK_TEXT, log);

    const envelope = bridgeCore.buildConversationEnvelope({
      text: cleanText,
      microsoftTenantId: config.microsoftTenantId,
      microsoftObjectId: cleanSenderId,
      conversationId: cleanConversationId,
      messageId: cleanMessageId,
      keyId: config.keyId,
    });
    const signed = bridgeCore.loadAndSignConversationEnvelope(
      envelope,
      config.privateKeyPath,
    );
    const result = await bridgeCore.postConversationEnvelope({
      runtimeUrl: config.runtimeUrl,
      envelope: signed,
      timeoutMs: config.requestTimeoutMs,
    });
    const replyText = bridgeCore.replyForRuntimeResult(result);
    const delivered = await sendActivity(context, replyText, log);

    log?.info?.("jason-teams-transport: governed Teams turn completed", {
      httpStatus: result.httpStatus,
      status: result.payload?.status ?? "unknown",
    });

    return { handled: true, finalResponses: delivered ? 1 : 0 };
  } catch (error) {
    log?.error?.("jason-teams-transport: governed runtime dispatch failed closed", {
      error: String(error?.message ?? error),
    });
    const delivered = await sendActivity(context, SAFE_FAILURE_TEXT, log);
    return { handled: true, finalResponses: delivered ? 1 : 0 };
  }
}
