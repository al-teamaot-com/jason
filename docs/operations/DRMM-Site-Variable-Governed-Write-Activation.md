# DRMM Site Variable Governed Write Activation

## Purpose

Activate Jason's governed Datto RMM site-variable create/update capability by reusing the **existing governed Datto RMM execution identity** already used for approved Datto actions.

This avoids introducing another Datto API identity while keeping site-variable authority separately bounded by Jason's capability policy.

## Preconditions

- Production source includes `management.site.variable.create` and `management.site.variable.update`.
- The master-registry/onboarding playbook is approved.
- The existing `datto-rmm-execution` AppRole and provider credential are healthy.
- The current Datto execution identity is authorized by Datto to read and manage site variables.
- AOT Owner/Administrator approval remains required for mutation unless a separately approved autonomous playbook grants that exact operation.
- Delete remains disabled.

## Credential boundary

Site-variable create/update uses the existing governed Datto execution credential:

- logical secret: `datto_rmm.execution`
- RoleID path: `/run/jason-secrets/openbao/datto-rmm-execution/role_id`
- SecretID path: `/run/jason-secrets/openbao/datto-rmm-execution/secret_id`

No new Datto API key, OpenBao secret, AppRole, or provider identity is required.

Reusing the credential does **not** merge the capabilities. Component execution and site-variable management remain separately registered, separately discoverable, separately approved, and separately auditable.

## 1. Verify existing execution identity

Verify without printing credentials:

- the existing execution AppRole files are mounted;
- `datto_rmm.execution` resolves through OpenBao;
- current governed Datto actions remain healthy.

Do not expose API key, API secret, RoleID, SecretID, or access token values.

## 2. Enable the site-variable activation profile

Set:

`JASON_DATTO_SITE_VARIABLE_MCP_PROFILE=owner-site-variable-v1`

for the Jason MCP/runtime composition that exposes governed actions.

The site-variable profile remains independent from the component-execution profile. Enabling it activates only the registered site-variable create/update capabilities.

## 3. Rebuild/redeploy from the pinned production source

Rebuild the Jason MCP/runtime from the accepted production source containing the shared-credential change.

Do not mix unrelated source changes into the deployment.

## 4. Verify capability state

Verify:

- `jason_mcp_status` reports `management.site.variable.create` and `management.site.variable.update`;
- `discover_capabilities(resource_type="management_site_variable")` returns list/create/update;
- create/update remain modifying actions subject to exact requester authority;
- values are not emitted in action results, logs, notes, or audit events;
- delete is absent;
- existing component-execution behavior is unchanged.

## 5. Provider permission proof

Before the first mutation, use the existing execution identity to perform the governed pre-read of a controlled site's variables.

If Datto denies the read or mutation because the current API identity lacks the required provider permission, stop and report that exact provider limitation. Do not create another API identity automatically and do not bypass Jason governance.

## 6. Controlled acceptance test

Use a clearly controlled non-client/test DRMM site.

Before mutation:

1. read the target site;
2. read its variables;
3. verify the approved test/standard name does not exist;
4. record the pre-state without values.

Create exactly one approved blank variable:

- name: a persistent approved test/standard name;
- value: blank string;
- masked: true.

After mutation:

1. require provider completion;
2. re-read the target site's variables;
3. verify the exact name exists once;
4. verify the action result exposes no value;
5. record correlation/evidence identifiers.

Because delete is deliberately disabled, do not create a disposable variable that requires automated cleanup.

## 7. Onboarding activation

Only after the controlled test succeeds may the onboarding playbook invoke site-variable creation.

The onboarding automation must:

- refresh the all-site registry;
- use only human-approved Standard variable names;
- re-read the new site immediately before creation;
- create only names that are absent;
- leave values blank;
- never overwrite an existing variable;
- stop on naming collisions or incomplete scans.

## Rollback / fail closed

If activation, provider authorization, or readback verification fails:

- unset `JASON_DATTO_SITE_VARIABLE_MCP_PROFILE`;
- redeploy/restart without the profile;
- preserve audit evidence;
- do not fall back to direct Datto API calls;
- do not broaden the existing Datto execution credential automatically.


## Production Acceptance Evidence — 2026-09-21

Live capability state:

- `management.site.variable.create`: ACTIVE and MCP action-enabled
- `management.site.variable.update`: ACTIVE and MCP action-enabled
- credential: existing `datto_rmm.execution` identity
- activation profile: `owner-site-variable-v1`
- delete capability: not exposed

Controlled target:

- Datto RMM site: `Managed`
- site UID: `59417980-b9eb-4c83-9080-f931cc210081`
- site had zero variables before the test

Acceptance sequence:

1. Pre-read completed successfully.
2. Create with an empty value was attempted once and failed closed with Datto HTTP 400.
3. Current Datto documentation confirms the create endpoint is `PUT /v2/site/{siteUid}/variable` and requires Sites > Sites: Manage; Datto's variable UX/import workflow treats variable value as required.
4. The onboarding convention was therefore changed from an empty value to the non-secret sentinel `__AOT_UNSET__` when a variable definition must exist before its real value is known.
5. `AOT_OnboardingVariableBaseline` was created with the sentinel through `execute_governed_capability` using one provider attempt.
6. Post-read verified the variable exists exactly once.
7. Jason returned the value masked and did not disclose it in the governed action result.

Evidence correlations:

- empty-value failed create: `corr_mcp_action_0c6433945a8e4092bf138184e0e8665a`
- successful sentinel create: `corr_mcp_action_ef267135898d491d82f730a09d476c09`
- post-read verification: `corr_mcp_3144aacabe974006bb5eed41f3598e3d`

### Standard placeholder rule

For onboarding-created Standard variables whose real value is not yet known:

- create with `__AOT_UNSET__`;
- default `masked=true` unless the approved registry explicitly requires otherwise;
- classify the variable as **present but not populated**;
- never treat the sentinel as a valid operational value;
- dependent components/playbooks must fail closed or defer when the sentinel is present;
- a later governed population/validation step must replace the sentinel with the approved value and verify readback;
- no ticket note, Grafana panel, audit event, or user-visible response may expose the populated secret value.

This replaces the earlier blank-value assumption because the live Datto API rejected an empty create request.
