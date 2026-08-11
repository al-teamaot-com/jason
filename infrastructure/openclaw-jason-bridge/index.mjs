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
const DEFAULT_TIMEOUT_MS = 30_000;

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
  if (!Number.isFinite(requestTimeoutMs) || requestTimeoutMs < 1000 || requestTimeoutMs > 40_000) {
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

function commandChannel(ctx) {
  return nonBlank(ctx.channelId ?? ctx.channel)?.toLowerCase();
}

async function handleJasonCommand(ctx) {
  if (commandChannel(ctx) !== "msteams") {
    return commandReply("Jason conversation binding is currently available only in Microsoft Teams.");
  }

  const action = (nonBlank(ctx.args) ?? "status").toLowerCase();
  if (action === "bind") {
    const current = await ctx.getCurrentConversationBinding();
    if (current?.pluginId === "jason-bridge") {
      return commandReply("This Microsoft Teams conversation is already bound to Jason's governed orchestration.");
    }
    const result = await ctx.requestConversationBinding({
      summary:
        "Route future plain Microsoft Teams messages in this conversation through Project Jason's governed orchestration.",
      detachHint: "/jason unbind",
      data: { mode: "governed-jason" },
    });
    if (result.status === "pending") {
      return result.reply;
    }
    if (result.status === "bound") {
      return commandReply("This Microsoft Teams conversation is now bound to Jason's governed orchestration.");
    }
    return commandReply(`Jason could not request this conversation binding: ${result.message}`);
  }

  if (action === "unbind") {
    const current = await ctx.getCurrentConversationBinding();
    if (!current) {
      return commandReply("This Microsoft Teams conversation is not currently bound to Jason.");
    }
    if (current.pluginId !== "jason-bridge") {
      return commandReply(
        `This conversation is bound to ${current.pluginName ?? current.pluginId}; Jason will not detach another plugin's binding.`,
      );
    }
    const result = await ctx.detachConversationBinding();
    return commandReply(
      result.removed
        ? "Jason's governed conversation binding was removed. Plain messages will return to normal OpenClaw routing."
        : "Jason could not remove the conversation binding.",
    );
  }

  if (action === "status") {
    const current = await ctx.getCurrentConversationBinding();
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

  return commandReply("Usage: /jason bind | /jason status | /jason unbind");
}

export default definePluginEntry({
  id: "jason-bridge",
  name: "Jason Bridge",
  description: "Governed Microsoft Teams transport bridge to Project Jason",
  register(api) {
    api.registerCommand({
      name: "jason",
      description: "Manage the governed Project Jason conversation binding.",
      acceptsArgs: true,
      requireAuth: true,
      handler: handleJasonCommand,
    });

    api.on(
      "inbound_claim",
      async (event, ctx) => {
        if (ctx.channelId !== "msteams" && event.channel !== "msteams") {
          return undefined;
        }

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

        const text = nonBlank(event.content);
        if (
          config.passthroughAuthorizedCommands &&
          event.commandAuthorized === true &&
          text?.startsWith("/")
        ) {
          return undefined;
        }
        if (!text) {
          return safeReply("Jason currently requires a text request for this governed conversation path.");
        }

        // OpenClaw's Microsoft Teams adapter uses activity.from.aadObjectId as
        // senderId when available. Reject the Bot Framework fallback id instead
        // of presenting it to Jason as Microsoft object identity evidence.
        const microsoftObjectId = nonBlank(event.senderId ?? ctx.senderId);
        if (!microsoftObjectId || !isUuid(microsoftObjectId)) {
          api.logger.warn?.("jason-bridge: Teams turn lacks an AAD object id; denied closed");
          return safeReply("Jason could not validate your Microsoft identity for this request.");
        }

        const conversationId = nonBlank(event.conversationId ?? ctx.conversationId ?? event.sessionKey ?? ctx.sessionKey);
        const messageId = nonBlank(event.messageId ?? ctx.messageId);
        if (!conversationId || !messageId) {
          api.logger.warn?.("jason-bridge: Teams turn lacks required conversation correlation; denied closed");
          return safeReply("Jason could not validate the conversation context for this request.");
        }

        try {
          const envelope = buildConversationEnvelope({
            text,
            microsoftTenantId: config.microsoftTenantId,
            microsoftObjectId,
            conversationId,
            messageId,
            keyId: config.keyId,
            correlationId: nonBlank(event.runId ?? ctx.runId) ?? undefined,
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
      },
      { timeoutMs: 45_000 },
    );
  },
});