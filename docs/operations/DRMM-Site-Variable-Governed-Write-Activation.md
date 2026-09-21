# DRMM Site Variable Governed Write Activation

## Purpose

Activate Jason's existing governed Datto RMM site-variable create/update runtime without broadening provider authority or exposing site-variable values.

## Preconditions

- Production source includes `management.site.variable.create` and `management.site.variable.update`.
- The master-registry/onboarding playbook is approved.
- A dedicated Datto RMM API identity exists with only the provider permission required to list and manage site variables.
- Do not reuse the Datto read-only or component-execution API identity.
- AOT Owner/Administrator approval is required for mutation.
- Delete remains disabled.

## 1. Provision the Datto identity

Create a dedicated Datto RMM API user/integration identity for Jason site-variable management.

Required provider behavior:

- authenticate to the Datto RMM v2 API;
- read `/api/v2/site/{siteUid}/variables`;
- create a site variable through `/api/v2/site/{siteUid}/variable`;
- update a site variable when separately authorized;
- no broader device/component/reboot authority should be granted solely for this function.

Record the API key and API secret only in the interactive provisioning step. Do not place them in Git, tickets, shell history, Teams, or documentation.

## 2. Provision OpenBao

From the production source tree, run as root:

```bash
python3 deploy/openbao/scripts/provision-datto-rmm-site-variables.py
```

The utility:

- installs `jason-datto-rmm-site-variables` policy;
- creates `secret/data/connectors/datto-rmm/production/site-variables`;
- creates a dedicated AppRole;
- proves the AppRole can read only the site-variable credential and is denied the normal read-only record;
- creates protected bootstrap RoleID/SecretID files;
- does not activate provider writes.

Expected bootstrap source directory:

`/opt/jason/bootstrap/secrets/openbao/datto-rmm-site-variables-approle`

## 3. Stage runtime credentials

Mount/copy the protected bootstrap credentials into the runtime credential staging mechanism so the container receives:

- `/run/jason-secrets/openbao/datto-rmm-site-variables/role_id`
- `/run/jason-secrets/openbao/datto-rmm-site-variables/secret_id`

Do not print either value.

Verify only file presence, ownership, and mode.

## 4. Enable the activation profile

Set:

`JASON_DATTO_SITE_VARIABLE_MCP_PROFILE=owner-site-variable-v1`

for the Jason runtime process/container.

Activation is intentionally profile-gated. Without the exact profile, the capabilities remain BUILDING and the provider remains unavailable.

## 5. Rebuild/redeploy from the pinned production source

Rebuild the Jason runtime/MCP using the accepted production source revision containing the site-variable runtime plus this activation work.

Do not mix unrelated branch changes into the deployment.

## 6. Verify capability state

Verify:

- `jason_mcp_status` reports `management.site.variable.create` and `management.site.variable.update`;
- `discover_capabilities(resource_type="management_site_variable")` returns list/create/update;
- create/update remain modifying actions subject to exact requester authority;
- values are not emitted in action results, logs, or notes;
- delete is absent.

## 7. Controlled acceptance test

Use a clearly controlled non-client/test DRMM site.

Before mutation:

1. read the target site;
2. read its variables;
3. verify the test name does not exist;
4. record the pre-state without values.

Create exactly one approved blank variable:

- name: a pre-approved persistent test/standard name;
- value: blank string;
- masked: true.

After mutation:

1. require provider terminal result;
2. re-read the target site's variables;
3. verify the exact name exists once;
4. verify the action result exposes no value;
5. record correlation/evidence identifiers.

Because delete is deliberately disabled, do not create a disposable variable that would require an autonomous cleanup operation.

## 8. Onboarding activation

Only after the controlled test succeeds may the onboarding playbook use the create action.

The onboarding automation must:

- refresh the all-site registry;
- use only human-approved Standard variable names;
- re-read the new site immediately before creation;
- create only names that are absent;
- leave values blank;
- never overwrite an existing variable;
- stop on naming collisions or incomplete scans.

## Rollback / fail closed

If provisioning, activation, provider authorization, or readback verification fails:

- unset the site-variable activation profile;
- redeploy/restart without the profile;
- preserve audit evidence;
- do not fall back to direct Datto API calls;
- do not reuse another provider credential as a shortcut.
