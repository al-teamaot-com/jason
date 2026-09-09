import { existsSync, readFileSync } from "node:fs";
import express from "express";
import JSON5 from "json5";
import {
  AgentApplication,
  CloudAdapter,
  MemoryStorage,
} from "@microsoft/agents-hosting";
import { createAgentRequestHandler } from "@microsoft/agents-hosting-express";
import {
  buildConversationEnvelope,
  isUuid,
  loadAndSignConversationEnvelope,
  postConversationEnvelope,
  replyForRuntimeResult,
} from "./bridge-core.mjs";

const PORT = Number(process.env.PORT ?? 3979);
const OPENCLAW_CONFIG_PATH =
  process.env.OPENCLAW_CONFIG_PATH ?? "/run/openclaw/openclaw.json";
const RUNTIME_URL =
  process.env.JASON_RUNTIME_URL ??
  "http://jason-runtime:8080/v1/openclaw/teams/conversation";
const KEY_ID = process.env.JASON_INGRESS_KEY_ID ?? "openclaw-gateway-2";
const PRIVATE_KEY_PATH =
  process.env.JASON_INGRESS_PRIVATE_KEY_PATH ?? "/run/jason/ingress.pem";
const REQUEST_TIMEOUT_MS = Number(
  process.env.JASON_TEAMS_REQUEST_TIMEOUT_MS ?? 150000,
);
const SAFE_FAILURE_TEXT =
  "Jason could not safely process that request. No action was taken.";

function nonBlank(value) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function loadOptionalOpenClawTeamsConfig() {
  if (!existsSync(OPENCLAW_CONFIG_PATH)) {
    return {};
  }
  const raw = readFileSync(OPENCLAW_CONFIG_PATH, "utf8");
  const cfg = JSON5.parse(raw);
  return cfg?.channels?.msteams ?? {};
}

function resolveEnvSecretRef(value) {
  if (
    value &&
    typeof value === "object" &&
    value.source === "env" &&
    typeof value.id === "string"
  ) {
    return nonBlank(process.env[value.id]);
  }
  return undefined;
}

function resolveCredential(value, fallbackEnvName) {
  return (
    nonBlank(process.env[fallbackEnvName]) ??
    nonBlank(value) ??
    resolveEnvSecretRef(value)
  );
}

function loadTeamsAuth() {
  // The direct Jason gateway owns its Microsoft credential through MSTEAMS_*.
  // OpenClaw config is fallback-only for transitional pilots and is not needed
  // by the production direct gateway.
  const envClientId = nonBlank(process.env.MSTEAMS_APP_ID);
  const envClientSecret = nonBlank(process.env.MSTEAMS_APP_PASSWORD);
  const envTenantId = nonBlank(process.env.MSTEAMS_TENANT_ID);

  let clientId = envClientId;
  let clientSecret = envClientSecret;
  let tenantId = envTenantId;

  if (!clientId || !clientSecret || !tenantId) {
    const teams = loadOptionalOpenClawTeamsConfig();
    clientId = clientId ?? resolveCredential(teams.appId, "MSTEAMS_APP_ID");
    clientSecret =
      clientSecret ??
      resolveCredential(teams.appPassword, "MSTEAMS_APP_PASSWORD");
    tenantId = tenantId ?? resolveCredential(teams.tenantId, "MSTEAMS_TENANT_ID");
  }

  if (!clientId || !clientSecret || !tenantId) {
    throw new Error(
      "Jason Teams gateway could not resolve Microsoft Teams credentials",
    );
  }
  if (!isUuid(clientId) || !isUuid(tenantId)) {
    throw new Error("Jason Teams gateway Microsoft identity configuration is invalid");
  }

  return { clientId, clientSecret, tenantId };
}

function cleanTeamsText(activity) {
  const raw = String(activity?.text ?? "");
  return raw.replace(/<at>.*?<\/at>\s*/gi, "").trim();
}

function activityTenantId(activity) {
  return nonBlank(activity?.channelData?.tenant?.id);
}

function activityAadObjectId(activity) {
  return nonBlank(activity?.from?.aadObjectId);
}

function logRuntimeFailure(result, { conversationId, messageId }) {
  if (Number(result?.httpStatus ?? 0) < 400) {
    return;
  }
  const payload = result?.payload ?? {};
  console.error(
    JSON.stringify({
      event: "jason_teams_runtime_failure",
      status: payload.status ?? "unknown",
      httpStatus: result.httpStatus,
      errorCode: payload.error_code ?? null,
      requestId: payload.request_id ?? null,
      correlationId: payload.correlation_id ?? null,
      conversationId,
      messageId,
    }),
  );
}

const auth = loadTeamsAuth();
const authConfiguration = {
  clientId: auth.clientId,
  clientSecret: auth.clientSecret,
  tenantId: auth.tenantId,
};

const adapter = new CloudAdapter(authConfiguration);
const storage = new MemoryStorage();
const agent = new AgentApplication({
  storage,
  adapter,
  agentAppId: auth.clientId,
});

agent.onActivity("message", async (context) => {
  const activity = context.activity;
  const text = cleanTeamsText(activity);
  const aadObjectId = activityAadObjectId(activity);
  const conversationId = nonBlank(activity?.conversation?.id);
  const messageId = nonBlank(activity?.id);
  const tenantId = activityTenantId(activity) ?? auth.tenantId;

  if (!tenantId || tenantId.toLowerCase() !== auth.tenantId.toLowerCase()) {
    await context.sendActivity(
      "Jason rejected this request because the Microsoft tenant identity could not be validated.",
    );
    return;
  }

  if (!text) {
    await context.sendActivity(
      "Jason currently requires a text request for this governed conversation path.",
    );
    return;
  }
  if (!aadObjectId || !isUuid(aadObjectId)) {
    await context.sendActivity(
      "Jason could not validate your Microsoft identity for this request.",
    );
    return;
  }
  if (!conversationId || !messageId) {
    await context.sendActivity(
      "Jason could not validate the conversation context for this request.",
    );
    return;
  }

  try {
    const envelope = buildConversationEnvelope({
      text,
      microsoftTenantId: auth.tenantId,
      microsoftObjectId: aadObjectId,
      conversationId,
      messageId,
      keyId: KEY_ID,
    });
    const signed = loadAndSignConversationEnvelope(
      envelope,
      PRIVATE_KEY_PATH,
    );
    const result = await postConversationEnvelope({
      runtimeUrl: RUNTIME_URL,
      envelope: signed,
      timeoutMs: REQUEST_TIMEOUT_MS,
    });

    logRuntimeFailure(result, { conversationId, messageId });
    await context.sendActivity(replyForRuntimeResult(result));

    console.log(
      JSON.stringify({
        event: "jason_teams_turn_completed",
        status: result.payload?.status ?? "unknown",
        httpStatus: result.httpStatus,
        conversationId,
        messageId,
      }),
    );
  } catch (error) {
    console.error(
      JSON.stringify({
        event: "jason_teams_turn_failed_closed",
        error: String(error?.message ?? error),
        conversationId,
        messageId,
      }),
    );
    await context.sendActivity(SAFE_FAILURE_TEXT);
  }
});

const server = express();
server.disable("x-powered-by");
server.use(express.json({ limit: "2mb" }));
server.get("/healthz", (_req, res) => {
  res.json({
    status: "ok",
    service: "jason-teams-gateway",
    runtime: RUNTIME_URL,
  });
});
server.post(
  "/api/messages",
  createAgentRequestHandler(agent, authConfiguration),
);

server.listen(PORT, "0.0.0.0", () => {
  console.log(
    JSON.stringify({
      event: "jason_teams_gateway_started",
      port: PORT,
      tenantId: auth.tenantId,
      clientId: auth.clientId,
    }),
  );
});
