import assert from "node:assert/strict";
import test from "node:test";
import {
  verifyReleaseApproverTeamsEligibility,
  TeamsBootstrapError,
} from "../teams-user-bootstrap.mjs";

const tenantId = "f7054323-d52b-4863-8c2f-1898f0b6077c";
const userId = "c848022d-e13b-4457-84b0-e2f5c00dcaf6";
const teams = "57ff2da0-773e-42df-b2af-ffb7a2317929";
function response(status, payload = {}) {
  return { status, ok: status >= 200 && status < 300,
    async json() { return payload; } };
}
async function check(payload, options = {}) {
  const calls = [];
  const fetchImpl = async (url, args = {}) => {
    calls.push({ url: String(url), method: args.method ?? "GET" });
    if (String(url).includes("/oauth2/v2.0/token"))
      return response(200, { access_token: "opaque-test-token" });
    if (String(url).includes("/users/"))
      return response(options.code ?? 200, payload);
    throw new Error("unreviewed Graph endpoint");
  };
  const query = verifyReleaseApproverTeamsEligibility({
    aadObjectId: userId, tenantId, clientId: "registered-app",
    clientSecret: "nonsecret-test", fetchImpl,
  });
  return { query, calls };
}
const base = () => ({
  id: userId, accountEnabled: true, userType: "Member",
  assignedPlans: [{ servicePlanId: teams, capabilityStatus: "Enabled", service: "teamspaceapi" }],
});
test("enabled exact Teams entitlement permits SAME Entra actor", async () => {
  const {query, calls} = await check(base());
  const data = await query;
  assert.deepEqual(data, {status: "eligible", tenantId, aadObjectId: userId});
  assert.equal(calls.length, 2);
  assert.ok(calls[1].url.includes("assignedPlans"));
  assert.equal(calls[1].method, "GET");
});
for(const [label, mutate, reason] of [
  ["unlicensed admin", data => data.assignedPlans = [], "teams_license_unavailable"],
  ["other product license only", data => data.assignedPlans = [{servicePlanId:"00000000-0000-0000-0000-000000000001", capabilityStatus:"Enabled"}], "teams_license_unavailable"],
  ["Teams entitlement suspended", data => data.assignedPlans[0].capabilityStatus="Suspended", "teams_license_unavailable"],
  ["Teams entitlement warning", data => data.assignedPlans[0].capabilityStatus="Warning", "teams_license_unavailable"],
  ["Teams account disabled", data => data.accountEnabled=false, "identity_not_authorized"],
  ["guest user", data => data.userType="Guest", "identity_not_authorized"],
  ["different actor", data => data.id="00000000-0000-0000-0000-000000000002", "identity_not_authorized"],
  ["Graph response omits assignedPlans", data => delete data.assignedPlans, "license_verification_unavailable"],
]) {
  test(label + " blocks with no Teams provisioning or send", async () => {
    const data = base(); mutate(data);
    const {query,calls} = await check(data);
    await assert.rejects(query, error => error instanceof TeamsBootstrapError && error.code === reason);
    assert.equal(calls.filter(c=>c.url.includes("/teamwork/") || c.method === "POST" && !c.url.includes("oauth")).length, 0);
  });
}
test("Graph permissions failure blocks, never assumes Teams readiness", async () => {
  const {query} = await check({error: {code:"Authorization_RequestDenied"}}, {code:403});
  await assert.rejects(query, e=>e instanceof TeamsBootstrapError && e.code==="license_verification_unavailable");
});
