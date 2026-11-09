const GRAPH_BASE = "https://graph.microsoft.com/v1.0";
const TOKEN_SCOPE = "https://graph.microsoft.com/.default";

export class TeamsBootstrapError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "TeamsBootstrapError";
    this.code = code;
  }
}

function nonBlank(value) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

async function getGraphToken({ tenantId, clientId, clientSecret, fetchImpl }) {
  const body = new URLSearchParams({
    client_id: clientId,
    client_secret: clientSecret,
    scope: TOKEN_SCOPE,
    grant_type: "client_credentials",
  });
  const response = await fetchImpl(
    `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`,
    {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body,
    },
  );
  if (!response.ok) {
    throw new TeamsBootstrapError(
      "graph_auth_failed",
      `Microsoft Graph token request failed with HTTP ${response.status}`,
    );
  }
  const payload = await readJson(response);
  const accessToken = nonBlank(payload.access_token);
  if (!accessToken) {
    throw new TeamsBootstrapError(
      "graph_auth_failed",
      "Microsoft Graph token response did not contain an access token",
    );
  }
  return accessToken;
}

async function graphRequest({ accessToken, path, fetchImpl, method = "GET", body }) {
  const response = await fetchImpl(`${GRAPH_BASE}${path}`, {
    method,
    headers: {
      authorization: `Bearer ${accessToken}`,
      ...(body ? { "content-type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  return { response, payload: await readJson(response) };
}

async function assertEnabledAotMember({ aadObjectId, accessToken, fetchImpl }) {
  const { response, payload } = await graphRequest({
    accessToken,
    path: `/users/${encodeURIComponent(aadObjectId)}?$select=id,accountEnabled,userType`,
    fetchImpl,
  });
  if (response.status === 404) {
    throw new TeamsBootstrapError("identity_not_found", "Target user was not found in the AOT tenant");
  }
  if (!response.ok) {
    throw new TeamsBootstrapError(
      "identity_not_authorized",
      `Target-user validation failed with HTTP ${response.status}`,
    );
  }
  if (String(payload.id ?? "").toLowerCase() !== aadObjectId.toLowerCase()) {
    throw new TeamsBootstrapError("identity_not_authorized", "Target-user identity binding did not match");
  }
  if (payload.accountEnabled !== true) {
    throw new TeamsBootstrapError("identity_not_authorized", "Target user is disabled");
  }
  if (String(payload.userType ?? "").toLowerCase() !== "member") {
    throw new TeamsBootstrapError("identity_not_authorized", "Target user is not an AOT member account");
  }
}

async function appInstalled({ aadObjectId, acceptedCatalogAppIds, accessToken, fetchImpl }) {
  let path = `/users/${encodeURIComponent(aadObjectId)}/teamwork/installedApps?$expand=teamsAppDefinition`;
  while (path) {
    const { response, payload } = await graphRequest({ accessToken, path, fetchImpl });
    if (!response.ok) {
      throw new TeamsBootstrapError(
        "graph_permission_denied",
        `Teams app-install lookup failed with HTTP ${response.status}`,
      );
    }
    const found = (payload.value ?? []).some((item) => {
      const definition = item?.teamsAppDefinition ?? {};
      const candidates = [
        definition.teamsAppId,
        definition.id,
        item?.teamsAppId,
      ].map((value) => String(value ?? "").toLowerCase());
      return acceptedCatalogAppIds.some((appId) => candidates.includes(appId.toLowerCase()));
    });
    if (found) return true;

    const nextLink = nonBlank(payload["@odata.nextLink"]);
    if (!nextLink) return false;
    if (!nextLink.startsWith(GRAPH_BASE)) {
      throw new TeamsBootstrapError("graph_permission_denied", "Unexpected Graph pagination target");
    }
    path = nextLink.slice(GRAPH_BASE.length);
  }
  return false;
}

async function installApp({ aadObjectId, catalogAppId, accessToken, fetchImpl }) {
  const { response, payload } = await graphRequest({
    accessToken,
    path: `/users/${encodeURIComponent(aadObjectId)}/teamwork/installedApps`,
    fetchImpl,
    method: "POST",
    body: {
      "teamsApp@odata.bind": `${GRAPH_BASE}/appCatalogs/teamsApps/${catalogAppId}`,
    },
  });
  if (response.status === 201 || response.status === 204 || response.status === 409) {
    return;
  }
  throw new TeamsBootstrapError(
    "app_install_failed",
    `Jason Teams app installation failed with HTTP ${response.status}: ${String(payload?.error?.code ?? "unknown")}`,
  );
}

export async function ensureTeamsUserBootstrap({
  aadObjectId,
  tenantId,
  clientId,
  clientSecret,
  catalogAppId,
  acceptedCatalogAppIds = [catalogAppId],
  fetchImpl = fetch,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  pollAttempts = 8,
  pollIntervalMs = 1500,
}) {
  if (!aadObjectId || !tenantId || !clientId || !clientSecret || !catalogAppId || !Array.isArray(acceptedCatalogAppIds) || acceptedCatalogAppIds.length === 0) {
    throw new TeamsBootstrapError("invalid_request", "Teams bootstrap configuration is incomplete");
  }

  const accessToken = await getGraphToken({ tenantId, clientId, clientSecret, fetchImpl });
  await assertEnabledAotMember({ aadObjectId, accessToken, fetchImpl });

  if (await appInstalled({ aadObjectId, acceptedCatalogAppIds, accessToken, fetchImpl })) {
    return { appInstallation: "existing" };
  }

  await installApp({ aadObjectId, catalogAppId, accessToken, fetchImpl });

  for (let attempt = 1; attempt <= pollAttempts; attempt += 1) {
    if (await appInstalled({ aadObjectId, acceptedCatalogAppIds, accessToken, fetchImpl })) {
      return { appInstallation: "created" };
    }
    if (attempt < pollAttempts) {
      await sleep(pollIntervalMs);
    }
  }

  throw new TeamsBootstrapError(
    "conversation_pending",
    "Jason Teams app installation has not become visible within the bounded bootstrap window",
  );
}


// Read-only tenant-authoritative eligibility for a PRIVILEGED release approver.
// The normal Teams bootstrap only verifies membership and app installation;
// neither proves that an unlicensed administrative identity can act on a card.
export async function verifyReleaseApproverTeamsEligibility({
  aadObjectId, tenantId, clientId, clientSecret, fetchImpl = fetch,
}) {
  if (![aadObjectId, tenantId, clientId, clientSecret].every(nonBlank)) {
    throw new TeamsBootstrapError("invalid_request", "Release approver identity or Graph credentials missing");
  }
  const token = await getGraphToken({ tenantId, clientId, clientSecret, fetchImpl });
  // Graph licenseDetails does not support the gateway's app-only token.
  // AssignedPlans is a user resource property exposed by the existing
  // Graph-backed identity read. This is the published TEAMS1 plan UUID.
  const { response, payload } = await graphRequest({
    accessToken: token,
    path: `/users/${encodeURIComponent(aadObjectId)}?$select=id,accountEnabled,userType,assignedPlans`,
    fetchImpl,
  });
  if (!response.ok) {
    throw new TeamsBootstrapError(
      "license_verification_unavailable",
      `Microsoft Graph assignedPlans read failed with HTTP ${response.status}`,
    );
  }
  if (String(payload?.id ?? "").toLowerCase() !== aadObjectId.toLowerCase() ||
      payload?.accountEnabled !== true ||
      String(payload?.userType ?? "").toLowerCase() !== "member") {
    throw new TeamsBootstrapError("identity_not_authorized", "Exact enabled tenant member is required");
  }
  if (!Array.isArray(payload?.assignedPlans)) {
    throw new TeamsBootstrapError(
      "license_verification_unavailable", "Microsoft Graph assignedPlans property missing",
    );
  }
  const TEAMS1 = "57ff2da0-773e-42df-b2af-ffb7a2317929";
  const enabled = payload.assignedPlans.some((plan) =>
    String(plan?.servicePlanId ?? "").toLowerCase() === TEAMS1 &&
    String(plan?.capabilityStatus ?? "").toLowerCase() === "enabled"
  );
  if (!enabled) {
    throw new TeamsBootstrapError(
      "teams_license_unavailable", "Configured approver lacks active verified Teams entitlement",
    );
  }
  return { status: "eligible", tenantId, aadObjectId };
}
