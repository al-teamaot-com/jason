import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  detachPluginConversationBinding,
  getCurrentPluginConversationBinding,
  requestPluginConversationBinding,
  resolvePluginConversationBindingApproval,
} from "openclaw/plugin-sdk/conversation-runtime";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import {
  buildConversationEnvelope,
  isUuid,
  loadAndSignConversationEnvelope,
  postConversationEnvelope,
  replyForRuntimeResult,
} from "./bridge-core.mjs";

const DEFAULT_RUNTIME_URL = "http://jason-runtime:8080/v1/openclaw/teams/conversation";
const DEFAULT_KEY_ID = "openclaw-gateway-2";
const DEFAULT_PRIVATE_KEY_PATH =
  "/home/node/.config/openclaw/jason-ingress/openclaw-jason-ed25519-v2.pem";
const DEFAULT_TIMEOUT_MS = 150_000;
const MAX_TIMEOUT_MS = 170_000;
const HOOK_TIMEOUT_MS = 180_000;
const BINDING_CONTEXT_TTL_MS = 10 * 60_000;
const BINDING_APPROVAL_TTL_MS = 5 * 60_000;
const MAX_BINDING_CONTEXTS = 256;
const WORKING_ACK_TEXT = "Received - working on that now...";

function asObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function nonBlank(value) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function resolveConfig(api) {
  const current = asObject(api.runtime.config?.current?.() ?? api.config);
  const plugins = asObject(current.plugins);
  const entries = asObject(plugins.entries);
  const entry = asObject(entries["jason-bridge"]);
  const live = asObject(entry.config);
  const initial = asObject(api.pluginConfig);
  const source = Object.keys(live).length ? live : initial;

  const microsoftTenantId = nonBlank(source.microsoftTenantId);
  if (!microsoftTenantId || !isUuid(microsoftTenantId)) {
    throw new Error("jason-bridge requires a valid microsoftTenantId");
  }
  const requestTimeoutMs = Number(source.requestTimeoutMs ?? DEFAULT_TIMEOUT_MS);
  if (!Number.isFinite(requestTimeoutMs) || requestTimeoutMs < 1000 || requestTimeoutMs > MAX_TIMEOUT_MS) {
    throw new Error("jason-bridge requestTimeoutMs is invalid");
  }
  return {
    microsoftTenantId,
    runtimeUrl: nonBlank(source.runtimeUrl) ?? DEFAULT_RUNTIME_URL,
    keyId: nonBlank(source.keyId) ?? DEFAULT_KEY_ID,
    privateKeyPath: nonBlank(source.privateKeyPath) ?? DEFAULT_PRIVATE_KEY_PATH,
    requestTimeoutMs,
    passthroughAuthorizedCommands: source.passthroughAuthorizedCommands !== false,
    current,
  };
}

function configuredTeamsTenant(current) {
  const channels = asObject(current.channels);
  const teams = asObject(channels.msteams);
  return nonBlank(teams.tenantId);
}

function safeReply(text) {
  return { handled: true, reply: { text } };
}

function commandReply(text) {
  return { text };
}

function claimReply(reply) {
  if (reply?.handled === true) {
    return reply;
  }

  return {
    handled: true,
    reply,
  };
}

function commandChannel(ctx) {
  return nonBlank(ctx.channelId ?? ctx.channel)?.toLowerCase();
}

function agentChannel(ctx) {
  return nonBlank(ctx.channel ?? ctx.messageProvider)?.toLowerCase();
}

async function sendWorkingAcknowledgement({
  api,
  conversationId,
  accountId,
  threadId,
}) {
  try {
    const adapter = await api.runtime.channel.outbound.loadAdapter("msteams");
    if (!adapter?.sendText) {
      api.logger.warn?.(
        "jason-bridge: Teams working acknowledgement unavailable; governed request continues",
      );
      return false;
    }

    const cleanAccountId = nonBlank(accountId);

    await adapter.sendText({
      cfg: api.config,
      to: conversationId,
      text: WORKING_ACK_TEXT,
      ...(cleanAccountId ? { accountId: cleanAccountId } : {}),
      ...(threadId !== undefined && threadId !== null ? { threadId } : {}),
    });

    return true;
  } catch {
    api.logger.warn?.(
      "jason-bridge: Teams working acknowledgement failed; governed request continues",
    );
    return false;
  }
}

function resolvePluginRoot(api) {
  const declared = nonBlank(api.rootDir);
  if (declared) {
    return declared;
  }
  const source = nonBlank(api.source);
  if (!source) {
    return undefined;
  }
  try {
    return path.dirname(source.startsWith("file:") ? fileURLToPath(source) : source);
  } catch {
    return undefined;
  }
}

function bindingContextKeys({ runId, sessionKey, senderId }) {
  const keys = [];
  const run = nonBlank(runId);
  const session = nonBlank(sessionKey);
  const sender = nonBlank(senderId);
  if (run) keys.push(`run:${run}`);
  if (session && sender) keys.push(`session:${session}|sender:${sender}`);
  if (session) keys.push(`session:${session}`);
  if (sender) keys.push(`sender:${sender}`);
  return keys;
}

function createTeamsBindingCompatibility(api) {
  const contexts = new Map();
  const pendingApprovals = new Map();
  const pluginRoot = resolvePluginRoot(api);

  const prune = () => {
    const now = Date.now();
    for (const [key, value] of contexts) {
      if (now - value.capturedAt > BINDING_CONTEXT_TTL_MS) contexts.delete(key);
    }
    for (const [key, value] of pendingApprovals) {
      if (now - value.createdAt > BINDING_APPROVAL_TTL_MS) pendingApprovals.delete(key);
    }
    while (contexts.size > MAX_BINDING_CONTEXTS) {
      contexts.delete(contexts.keys().next().value);
    }
  };

  const capture = (event, ctx) => {
    if (ctx.channelId !== "msteams") return;
    const conversationId = nonBlank(ctx.conversationId);
    if (!conversationId) return;
    const senderId = nonBlank(event.senderId ?? ctx.senderId);
    const sessionKey = nonBlank(event.sessionKey ?? ctx.sessionKey);
    const runId = nonBlank(event.runId ?? ctx.runId);
    const accountId = nonBlank(ctx.accountId) ?? "default";
    const conversation = {
      channel: "msteams",
      accountId,
      conversationId,
      ...(event.threadId !== undefined && event.threadId !== null
        ? { threadId: event.threadId }
        : {}),
    };
    const captured = {
      conversation,
      messageId: nonBlank(event.messageId ?? ctx.messageId),
      senderId,
      sessionKey,
      runId,
      capturedAt: Date.now(),
    };
    for (const key of bindingContextKeys({ runId, sessionKey, senderId })) contexts.set(key, captured);
    prune();
  };

  const lookupCaptured = (ctx) => {
    prune();
    for (const key of bindingContextKeys({
      runId: ctx.runId,
      sessionKey: ctx.sessionKey,
      senderId: ctx.senderId,
    })) {
      const found = contexts.get(key);
      if (found) return found;
    }
    return undefined;
  };

  const lookup = (ctx) => lookupCaptured(ctx)?.conversation;

  const lookupWithBriefRetry = async (ctx) => {
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const found = lookup(ctx);
      if (found) return found;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    return undefined;
  };

  const lookupCapturedWithBriefRetry = async (ctx) => {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const found = lookupCaptured(ctx);
      if (found) return found;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    return undefined;
  };

  const approvalKey = (ctx) =>
    bindingContextKeys({
      runId: ctx.runId,
      sessionKey: ctx.sessionKey,
      senderId: ctx.senderId,
    })[0];

  const rememberApproval = (ctx, approvalId) => {
    const key = approvalKey(ctx);
    if (!key) return false;
    pendingApprovals.set(key, { approvalId, createdAt: Date.now() });
    prune();
    return true;
  };

  const takeApproval = (ctx) => {
    prune();
    const key = approvalKey(ctx);
    if (!key) return undefined;
    const pending = pendingApprovals.get(key);
    if (pending) pendingApprovals.delete(key);
    return pending?.approvalId;
  };

  const peekApproval = (ctx) => {
    prune();
    const key = approvalKey(ctx);
    return key ? pendingApprovals.get(key)?.approvalId : undefined;
  };

  return {
    capture,
    pluginRoot,
    lookupWithBriefRetry,
    lookupCapturedWithBriefRetry,
    rememberApproval,
    takeApproval,
    peekApproval,
  };
}

async function forwardGovernedTeamsTurn({
  api,
  text,
  microsoftObjectId,
  conversationId,
  accountId,
  threadId,
  messageId,
  correlationId,
}) {
  let config;
  try {
    config = resolveConfig(api);
  } catch {
    api.logger.error?.("jason-bridge: invalid bridge configuration; Teams turn denied closed");
    return safeReply("Jason is not available because its governed transport configuration is invalid.");
  }

  const channelTenant = configuredTeamsTenant(config.current);
  if (channelTenant && channelTenant.toLowerCase() !== config.microsoftTenantId.toLowerCase()) {
    api.logger.error?.("jason-bridge: configured Teams tenant does not match Jason transport tenant");
    return safeReply("Jason rejected this request because the Microsoft tenant binding could not be validated.");
  }

  const cleanText = nonBlank(text);
  if (!cleanText) {
    return safeReply("Jason currently requires a text request for this governed conversation path.");
  }

  const cleanMicrosoftObjectId = nonBlank(microsoftObjectId);
  if (!cleanMicrosoftObjectId || !isUuid(cleanMicrosoftObjectId)) {
    api.logger.warn?.("jason-bridge: Teams turn lacks an AAD object id; denied closed");
    return safeReply("Jason could not validate your Microsoft identity for this request.");
  }

  const cleanConversationId = nonBlank(conversationId);
  const cleanMessageId = nonBlank(messageId);
  if (!cleanConversationId || !cleanMessageId) {
    api.logger.warn?.("jason-bridge: Teams turn lacks required conversation correlation; denied closed");
    return safeReply("Jason could not validate the conversation context for this request.");
  }

  await sendWorkingAcknowledgement({
    api,
    conversationId: cleanConversationId,
    accountId,
    threadId,
  });

  try {
    const envelope = buildConversationEnvelope({
      text: cleanText,
      microsoftTenantId: config.microsoftTenantId,
      microsoftObjectId: cleanMicrosoftObjectId,
      conversationId: cleanConversationId,
      messageId: cleanMessageId,
      keyId: config.keyId,
      correlationId: nonBlank(correlationId) ?? undefined,
    });
    const signed = loadAndSignConversationEnvelope(envelope, config.privateKeyPath);
    const result = await postConversationEnvelope({
      runtimeUrl: config.runtimeUrl,
      envelope: signed,
      timeoutMs: config.requestTimeoutMs,
    });

    if (result.payload?.status !== "completed") {
      api.logger.warn?.(
        `jason-bridge: governed runtime returned ${String(result.payload?.status ?? "unknown")} (${result.httpStatus})`,
      );
    }
    return safeReply(replyForRuntimeResult(result));
  } catch {
    api.logger.error?.("jason-bridge: governed runtime request failed; no OpenClaw fallback permitted");
    return safeReply("Jason could not safely process that request. No action was taken.");
  }
}

async function handleJasonCommand(ctx, compatibility) {
  if (commandChannel(ctx) !== "msteams") {
    return commandReply("Jason conversation binding is currently available only in Microsoft Teams.");
  }
  if (!compatibility.pluginRoot) {
    return commandReply("Jason cannot safely manage the Teams binding because its OpenClaw plugin identity is unavailable.");
  }

  const action = (nonBlank(ctx.args) ?? "status").toLowerCase();
  const conversation = await compatibility.lookupWithBriefRetry(ctx);
  if (!conversation) {
    return commandReply(
      "Jason could not resolve this Teams conversation yet. Send /jason status once, then retry the command.",
    );
  }

  if (action === "bind") {
    const current = await getCurrentPluginConversationBinding({
      pluginRoot: compatibility.pluginRoot,
      conversation,
    });
    if (current?.pluginId === "jason-bridge") {
      return commandReply("This Microsoft Teams conversation is already bound to Jason's governed orchestration.");
    }
    if (compatibility.peekApproval(ctx)) {
      return commandReply("A Jason binding approval is already pending. Send /jason approve or /jason deny.");
    }
    const result = await requestPluginConversationBinding({
      pluginId: "jason-bridge",
      pluginName: "Jason Bridge",
      pluginRoot: compatibility.pluginRoot,
      requestedBySenderId: nonBlank(ctx.senderId),
      conversation,
      binding: {
        summary:
          "Route future plain Microsoft Teams messages in this conversation through Project Jason's governed orchestration.",
        detachHint: "/jason unbind",
        data: { mode: "governed-jason" },
      },
    });
    if (result.status === "bound") {
      return commandReply("This Microsoft Teams conversation is now bound to Jason's governed orchestration.");
    }
    if (result.status === "pending") {
      if (!compatibility.rememberApproval(ctx, result.approvalId)) {
        return commandReply("Jason created a binding request but could not safely correlate its approval. No binding was created.");
      }
      return commandReply(
        "Jason is ready to bind this Teams conversation. Send /jason approve to confirm, or /jason deny to cancel.",
      );
    }
    return commandReply(`Jason could not request this conversation binding: ${result.message}`);
  }

  if (action === "approve" || action === "deny") {
    const approvalId = compatibility.takeApproval(ctx);
    if (!approvalId) {
      return commandReply("There is no pending Jason binding approval for this Teams conversation. Send /jason bind first.");
    }
    const result = await resolvePluginConversationBindingApproval({
      approvalId,
      decision: action === "approve" ? "allow-once" : "deny",
      senderId: nonBlank(ctx.senderId),
    });
    if (result.status === "approved") {
      return commandReply("This Microsoft Teams conversation is now bound to Jason's governed orchestration.");
    }
    if (result.status === "denied") {
      return commandReply("Jason conversation binding was denied. Plain messages remain on normal OpenClaw routing.");
    }
    return commandReply("The Jason binding approval expired. Send /jason bind to create a new request.");
  }

  if (action === "unbind") {
    const current = await getCurrentPluginConversationBinding({
      pluginRoot: compatibility.pluginRoot,
      conversation,
    });
    if (!current) {
      return commandReply("This Microsoft Teams conversation is not currently bound to Jason.");
    }
    const result = await detachPluginConversationBinding({
      pluginRoot: compatibility.pluginRoot,
      conversation,
    });
    return commandReply(
      result.removed
        ? "Jason's governed conversation binding was removed. Plain messages will return to normal OpenClaw routing."
        : "Jason could not remove the conversation binding.",
    );
  }

  if (action === "status") {
    const current = await getCurrentPluginConversationBinding({
      pluginRoot: compatibility.pluginRoot,
      conversation,
    });
    if (!current) {
      return commandReply(
        "This Microsoft Teams conversation is not bound to Jason. Use /jason bind to request a governed binding.",
      );
    }
    if (current.pluginId === "jason-bridge") {
      return commandReply("This Microsoft Teams conversation is bound to Jason's governed orchestration.");
    }
    return commandReply(`This conversation is currently bound to ${current.pluginName ?? current.pluginId}.`);
  }

  return commandReply("Usage: /jason bind | /jason approve | /jason deny | /jason status | /jason unbind");
}

export default definePluginEntry({
  id: "jason-bridge",
  name: "Jason Bridge",
  description: "Governed Microsoft Teams transport bridge to Project Jason",
  register(api) {
    const compatibility = createTeamsBindingCompatibility(api);

    // OpenClaw 2026.7.1 does not expose a command conversation-binding resolver
    // for Microsoft Teams. Observe the canonical inbound hook context and keep a
    // short-lived correlation keyed by run/session/sender so command handling and
    // the compatibility forwarding path can reuse authenticated transport facts
    // without patching OpenClaw core or writing directly to its SQLite state.
    api.on("message_received", (event, ctx) => {
      compatibility.capture(event, ctx);
    });

    api.registerCommand({
      name: "jason",
      description: "Manage the governed Project Jason conversation binding.",
      acceptsArgs: true,
      requireAuth: true,
      handler: (ctx) => handleJasonCommand(ctx, compatibility),
    });

    api.on(
      "inbound_claim",
      async (event, ctx) => {
        if (ctx.channelId !== "msteams" && event.channel !== "msteams") {
          return undefined;
        }

        const text = nonBlank(event.content);

        let config;
        try {
          config = resolveConfig(api);
        } catch {
          api.logger.error?.(
            "jason-bridge: invalid bridge configuration; Teams turn denied closed",
          );

          return claimReply(
            safeReply(
              "Jason is not available because its governed transport configuration is invalid.",
            ),
          );
        }

        if (
          config.passthroughAuthorizedCommands &&
          event.commandAuthorized === true &&
          text?.startsWith("/")
        ) {
          return undefined;
        }

        api.logger.info?.(
          "jason-bridge: claiming Jason-bound Teams inbound before agent dispatch",
        );

        const reply = await forwardGovernedTeamsTurn({
          api,
          text,
          microsoftObjectId: event.senderId ?? ctx.senderId,
          conversationId:
            event.conversationId ??
            ctx.conversationId ??
            event.sessionKey ??
            ctx.sessionKey,
          accountId: event.accountId ?? ctx.accountId,
          threadId: event.threadId ?? ctx.threadId,
          messageId: event.messageId ?? ctx.messageId,
          correlationId: event.runId ?? ctx.runId,
        });

        return claimReply(reply);
      },
      { timeoutMs: HOOK_TIMEOUT_MS },
    );

  },
});
