import assert from "node:assert/strict";
import test from "node:test";

import {
  ensureTeamsUserBootstrap,
  TeamsBootstrapError,
} from "../teams-user-bootstrap.mjs";

const tenantId = "f7054323-d52b-4863-8c2f-1898f0b6077c";
const clientId = "c94301b7-7194-46ab-aab7-94f9366f51a9";
const userId = "0a102414-3fe7-463f-9568-60dd716eb894";
const catalogAppId = "1b24025a-201f-439d-a4ef-e308c7f3d853";
const legacyCatalogAppId = "686aa9d3-e41b-4af2-9fbf-74f83a7ffc32";

function response(status, payload = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    async json() {
      return payload;
    },
  };
}

function tokenResponse() {
  return response(200, { access_token: "opaque-test-token" });
}

function enabledMember() {
  return response(200, { id: userId, accountEnabled: true, userType: "Member" });
}

test("existing app install is reused without POST install", async () => {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url: String(url), method: options.method ?? "GET" });
    if (String(url).includes("/oauth2/v2.0/token")) return tokenResponse();
    if (String(url).includes(`/users/${userId}?`)) return enabledMember();
    if (String(url).includes("/teamwork/installedApps")) {
      return response(200, {
        value: [{ teamsAppDefinition: { teamsAppId: catalogAppId } }],
      });
    }
    throw new Error("unexpected request");
  };

  const result = await ensureTeamsUserBootstrap({
    aadObjectId: userId,
    tenantId,
    clientId,
    clientSecret: "opaque-secret",
    catalogAppId,
    fetchImpl,
    sleep: async () => {},
  });

  assert.deepEqual(result, { appInstallation: "existing" });
  assert.equal(calls.filter((call) => call.method === "POST" && call.url.includes("installedApps")).length, 0);
});

test("legacy working Jason package is accepted without duplicate install", async () => {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url: String(url), method: options.method ?? "GET" });
    if (String(url).includes("/oauth2/v2.0/token")) return tokenResponse();
    if (String(url).includes(`/users/${userId}?`)) return enabledMember();
    if (String(url).includes("/teamwork/installedApps")) {
      return response(200, {
        value: [{ teamsAppDefinition: { teamsAppId: legacyCatalogAppId } }],
      });
    }
    throw new Error("unexpected request");
  };

  const result = await ensureTeamsUserBootstrap({
    aadObjectId: userId,
    tenantId,
    clientId,
    clientSecret: "opaque-secret",
    catalogAppId,
    acceptedCatalogAppIds: [catalogAppId, legacyCatalogAppId],
    fetchImpl,
    sleep: async () => {},
  });

  assert.deepEqual(result, { appInstallation: "existing" });
  assert.equal(calls.filter((call) => call.method === "POST" && call.url.includes("installedApps")).length, 0);
});

test("missing app is installed once and becomes reusable", async () => {
  const calls = [];
  let installed = false;
  const fetchImpl = async (url, options = {}) => {
    const method = options.method ?? "GET";
    calls.push({ url: String(url), method });
    if (String(url).includes("/oauth2/v2.0/token")) return tokenResponse();
    if (String(url).includes(`/users/${userId}?`)) return enabledMember();
    if (String(url).includes("/teamwork/installedApps") && method === "POST") {
      installed = true;
      return response(201, {});
    }
    if (String(url).includes("/teamwork/installedApps")) {
      return response(200, {
        value: installed ? [{ teamsAppDefinition: { teamsAppId: catalogAppId } }] : [],
      });
    }
    throw new Error("unexpected request");
  };

  const result = await ensureTeamsUserBootstrap({
    aadObjectId: userId,
    tenantId,
    clientId,
    clientSecret: "opaque-secret",
    catalogAppId,
    fetchImpl,
    sleep: async () => {},
  });

  assert.deepEqual(result, { appInstallation: "created" });
  assert.equal(calls.filter((call) => call.method === "POST" && call.url.includes("installedApps")).length, 1);
});

for (const [label, userPayload] of [
  ["disabled", { id: userId, accountEnabled: false, userType: "Member" }],
  ["guest", { id: userId, accountEnabled: true, userType: "Guest" }],
]) {
  test(`${label} identities fail closed before Teams app lookup or install`, async () => {
    const calls = [];
    const fetchImpl = async (url, options = {}) => {
      calls.push({ url: String(url), method: options.method ?? "GET" });
      if (String(url).includes("/oauth2/v2.0/token")) return tokenResponse();
      if (String(url).includes(`/users/${userId}?`)) return response(200, userPayload);
      throw new Error("unexpected side effect after rejected identity");
    };

    await assert.rejects(
      ensureTeamsUserBootstrap({
        aadObjectId: userId,
        tenantId,
        clientId,
        clientSecret: "opaque-secret",
        catalogAppId,
        fetchImpl,
        sleep: async () => {},
      }),
      (error) => error instanceof TeamsBootstrapError && error.code === "identity_not_authorized",
    );
    assert.equal(calls.some((call) => call.url.includes("/teamwork/installedApps")), false);
  });
}

test("missing target identity is classified before install", async () => {
  const fetchImpl = async (url) => {
    if (String(url).includes("/oauth2/v2.0/token")) return tokenResponse();
    if (String(url).includes(`/users/${userId}?`)) return response(404, {});
    throw new Error("unexpected request");
  };

  await assert.rejects(
    ensureTeamsUserBootstrap({
      aadObjectId: userId,
      tenantId,
      clientId,
      clientSecret: "opaque-secret",
      catalogAppId,
      fetchImpl,
      sleep: async () => {},
    }),
    (error) => error instanceof TeamsBootstrapError && error.code === "identity_not_found",
  );
});
