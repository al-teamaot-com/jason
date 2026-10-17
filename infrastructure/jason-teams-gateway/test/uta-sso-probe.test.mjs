import test from "node:test";
import assert from "node:assert/strict";
import { parseUtaSsoProbeConfig, handleUtaSsoProbe, UTA_SSO_PROBE_COMMAND } from "../uta-sso-probe.mjs";

test("disabled default does not provision any SDK user auth handler", () => {
  assert.equal(parseUtaSsoProbeConfig({}), null);
  assert.equal(parseUtaSsoProbeConfig({JASON_UTA_SSO_PROBE_ENABLED:"false"}), null);
});

test("explicit SSO probe requires named Azure Bot OAuth connection", () => {
  assert.throws(() => parseUtaSsoProbeConfig({JASON_UTA_SSO_PROBE_ENABLED:"true"}));
  assert.throws(() => parseUtaSsoProbeConfig({JASON_UTA_SSO_PROBE_ENABLED:"true",JASON_UTA_SSO_CONNECTION_NAME:"../escape"}));
  assert.throws(() => parseUtaSsoProbeConfig({JASON_UTA_SSO_PROBE_ENABLED:"not-true"}));
  const config=parseUtaSsoProbeConfig({
    JASON_UTA_SSO_PROBE_ENABLED:"true",
    JASON_UTA_SSO_CONNECTION_NAME:"UTA_AOT_User",
  });
  assert.equal(config.handlerId, "uta-human");
  assert.deepEqual(config.authorization["uta-human"], {
    type:"AzureBotUserAuthorization",
    azureBotOAuthConnectionName:"UTA_AOT_User",
    enableSso:true,
  });
});

test("probe only recognizes the exact harmless command", () => {
  assert.equal(UTA_SSO_PROBE_COMMAND.test("/uta-sso-check"),true);
  for (const value of ["/approve","approve","/uta-sso-check force","/uta-sso-check\nfoo",""]) {
    assert.equal(UTA_SSO_PROBE_COMMAND.test(value),false);
  }
});

test("SDK token response never escapes in messages or result", async () => {
  const messages=[];
  const context={sendActivity: async text=>messages.push(text)};
  const authorization={getToken: async()=>({token:"very-secret-bearer-token"})};
  assert.equal(await handleUtaSsoProbe({context,authorization,handlerId:"uta-human"}),true);
  assert.equal(messages.length,1);
  assert.doesNotMatch(messages[0],/very-secret-bearer-token/);
  assert.match(messages[0],/No approval was issued or executed/);
});

test("missing user token fails closed with no approval",async()=>{
  const messages=[];
  assert.equal(await handleUtaSsoProbe({
    context:{sendActivity:async text=>messages.push(text)},
    authorization:{getToken:async()=>({token:null})},
    handlerId:"uta-human",
  }),false);
  assert.match(messages[0],/did not return a user token/);
});
