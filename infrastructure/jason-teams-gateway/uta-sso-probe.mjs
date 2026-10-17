/** Disabled-by-default Teams SSO acquisition probe, not an approval route. */
export const UTA_SSO_PROBE_COMMAND = /^\/uta-sso-check$/i;
export const UTA_SSO_HANDLER_ID = "uta-human";

export function parseUtaSsoProbeConfig(env) {
  const raw = String(env.JASON_UTA_SSO_PROBE_ENABLED ?? "false").trim().toLowerCase();
  if (raw === "false" || raw === "0" || raw === "") return null;
  if (raw !== "true" && raw !== "1") throw new Error("UTA SSO probe activation flag is invalid");
  const connectionName = String(env.JASON_UTA_SSO_CONNECTION_NAME ?? "").trim();
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(connectionName)) {
    throw new Error("UTA SSO probe requires a bounded configured Azure Bot OAuth connection");
  }
  return {
    handlerId: UTA_SSO_HANDLER_ID,
    authorization: {
      [UTA_SSO_HANDLER_ID]: {
        type: "AzureBotUserAuthorization",
        azureBotOAuthConnectionName: connectionName,
        enableSso: true,
      },
    },
  };
}

export async function handleUtaSsoProbe({ context, authorization, handlerId }) {
  // SDK user authorization is route-scoped. Never log/store/forward the bearer.
  const response = await authorization.getToken(context, handlerId);
  const acquired = typeof response?.token === "string" && response.token.trim().length > 0;
  await context.sendActivity(acquired
    ? "UTA SSO user token acquisition succeeded. No approval was issued or executed."
    : "UTA SSO did not return a user token. No approval was issued or executed.");
  return acquired;
}
