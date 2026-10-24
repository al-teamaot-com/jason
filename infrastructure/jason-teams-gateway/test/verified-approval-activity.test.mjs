import test from "node:test";
import assert from "node:assert/strict";
import { isBoundTeamsApprovalActivity } from "../verified-approval-activity.mjs";

const TENANT = "11111111-2222-4333-8444-555555555555";
const USER = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
const makeActivity = () => ({
  channelId: "msteams",
  channelData: { tenant: { id: TENANT } },
  from: { aadObjectId: USER },
  conversation: { id: "a:verified-conversation" },
  id: "f:verified-card-submit",
});

test("a complete Teams-channel activity is eligible for independent approval validation", () => {
  assert.equal(isBoundTeamsApprovalActivity({activity:makeActivity(), expectedTenantId:TENANT.toUpperCase()}), true);
});

test("a different channel cannot assert a Teams approval identity", () => {
  for (const channelId of ["webchat", "directline", "", undefined]) {
    const activity = { ...makeActivity(), channelId };
    assert.equal(isBoundTeamsApprovalActivity({activity, expectedTenantId:TENANT}), false);
  }
});

test("approval tenant must be explicitly present and match configured tenant", () => {
  for (const channelData of [undefined, {}, { tenant: {} }, { tenant: { id:"not-a-uuid" } },
    { tenant: { id:"99999999-2222-3333-4444-555555555555" } }]) {
    assert.equal(isBoundTeamsApprovalActivity({
      activity:{...makeActivity(), channelData}, expectedTenantId:TENANT,
    }), false);
  }
});

test("absent or non-UUID Teams actor never creates approval evidence", () => {
  for (const from of [undefined, {}, {aadObjectId:"not-uuid"}]) {
    assert.equal(isBoundTeamsApprovalActivity({
      activity:{...makeActivity(),from}, expectedTenantId:TENANT,
    }), false);
  }
});

test("missing conversation or message binding fails closed", () => {
  for (const change of [{conversation:undefined},{conversation:{id:" "}},{id:""},{id:null}]) {
    assert.equal(isBoundTeamsApprovalActivity({
      activity:{...makeActivity(),...change}, expectedTenantId:TENANT,
    }), false);
  }
});

test("missing or malformed configured tenant denies approval", () => {
  for (const tenantId of [undefined, "", "not-uuid"]) {
    assert.equal(isBoundTeamsApprovalActivity({activity:makeActivity(), expectedTenantId:tenantId}), false);
  }
});
