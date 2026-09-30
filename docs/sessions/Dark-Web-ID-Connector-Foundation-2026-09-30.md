# Dark Web ID Connector Foundation — 2026-09-30

## Purpose

Establish the governed Dark Web ID provider credential and the first production-shaped read connector for Project Jason without exposing or enabling Dark Web ID mutations.

## Provider and authentication contract

- Provider: Kaseya Dark Web ID.
- API base: `https://secure.darkwebid.com/`.
- Authentication: HTTP Basic Authentication with a Dark Web ID-specific partner-user password.
- Dedicated AOT integration identity: `jason@teamaot.com`.
- API prerequisites confirmed by AOT before provisioning: partner API user, `Permit access to web services`, Dark Web ID-specific password, and Jason's static public IPv4 on the user's allowlist.
- Jason's observed egress IPv4 during acceptance: `216.54.107.150`.
- Kaseya documentation confirms that API access also requires IP allowlisting and that KaseyaOne authentication does not replace the Dark Web ID-specific API password.

## Governed secret contract

Lifecycle provider key: `darkwebid`

Logical secret: `darkwebid.runtime`

OpenBao KV v2 path: `secret/data/connectors/darkwebid/production/runtime`

Durable fields:

- `username`
- `password`

Runtime identity:

- policy: `jason-darkwebid-secret-read`
- AppRole: `jason-darkwebid-secret-read`
- host artifacts: `/var/lib/jason/runtime-secrets/openbao/darkwebid-approle/`
- container role path: `/run/jason-secrets/openbao/darkwebid/role_id`
- container secret path: `/run/jason-secrets/openbao/darkwebid/secret_id`

The canonical lifecycle `create darkwebid` completed successfully with KV version 1. The temporary OpenBao administrative token was revoked. Runtime resolution through the dedicated AppRole proved both required fields were present without printing either value.

## Vendor API evidence

Current Kaseya documentation exposes the following organization operations:

- `GET /services/organization.json` — list organizations available to the current API user.
- `GET /services/organization/{uuid}.json` — retrieve one organization.
- `GET /services/v2/organization` — list directly managed organizations using the v2 contract.
- `POST /services/v2/organization` — create an organization.
- `DELETE /services/v2/organization/{id}` — delete an organization.
- `PATCH /services/v2/organization/{id}` — update an organization.
- `PATCH /services/v2/organization/notification/{id}` — upsert organization notification preferences.
- `PATCH /services/v2/organization/reporting-preferences/{id}` — upsert reporting preferences.

Kaseya's current Organization Provisioning Tool also uses provider-supported organization, monitored-domain, user, user-preference, and reporting operations. These mutation surfaces are evidence that the provider credential is not inherently read-only; they do not grant Jason mutation authority.

The v1 organization-list contract is zero-based: `page=0` is the first page and `limit` is bounded to 200. An early acceptance probe incorrectly used `page=1`; because the account currently has a single page of organizations, the provider returned 404. The connector was corrected to the documented zero-based paging contract rather than adding an indiscriminate 404 retry.

## Live connector acceptance

The completed `DarkWebIdConnector` was executed through the canonical OpenBao resolver using the dedicated runtime AppRole and the provider's documented HTTP Basic authentication pattern.

Acceptance request:

- provider capability: `darkwebid.organization.search`
- method: `GET`
- endpoint: `/services/organization.json`
- page: `0`
- limit: `200`
- execution mode: `observe`

Acceptance result:

- status: pass
- records returned: 15
- audit events: 2 (`connector.requested`, `connector.completed`)
- secret values printed: false
- provider mutation attempted: false
- provider response top-level fields: `first`, `last`, `list`, `self`

The acceptance output intentionally recorded schema/field names and counts only. It did not print organization names, monitored domains, email addresses, exposed credentials, or the API username/password.

## Initial Jason capability boundary

Provider capabilities implemented:

- `darkwebid.organization.search`
- `darkwebid.organization.read`

Canonical capabilities registered:

- `credential.exposure.organization.search`
- `credential.exposure.organization.read`

The initial connector is restricted to:

- AOT organization scope only;
- no caller-supplied client scope;
- `observe` mode only;
- allowlisted GET paths only;
- exact UUID validation for single-organization reads;
- zero-based paging with provider-documented limits.

No Dark Web ID create, update, delete, monitor, user, notification, reporting, or other mutation is exposed by the connector or Central Orchestrator.

## Runtime wiring

Runtime settings now declare:

- `JASON_DARKWEBID_ENABLED`
- `JASON_DARKWEBID_OPENBAO_ROLE_ID_PATH`
- `JASON_DARKWEBID_OPENBAO_SECRET_ID_PATH`

The runtime container declaration mounts the dedicated Dark Web ID AppRole artifacts read-only. The enablement flag defaults to `false` until governed deployment activates the provider.

The connector catalog records Dark Web ID as a governed-read-first provider and maps the two canonical organization inventory capabilities to the two provider read capabilities.

## Validation completed

At the point this record was written:

- Dark Web ID connector/client tests pass.
- Dark Web ID capability catalog tests pass.
- Provider-secret lifecycle tests pass.
- OpenBao secret-resolver tests pass.
- runtime composition tests pass.
- live provider-backed connector acceptance passes.

## Production activation closure

Production activation completed on 2026-09-30.

### Durable authority

Before adding Dark Web ID read authority, the production authority database was backed up with SQLite's online backup API:

`/var/lib/jason/authority/authority.sqlite3.backup-darkwebid-read-20260930T154920Z`

The backup passed `PRAGMA integrity_check` and was mode `0600`. Exactly one durable grant was then added through `tools/identity_authority_admin.py`:

- grant ID: `grant-aot-darkwebid-provider-read-observe`;
- subject: `organization:aot`;
- capability: `provider-read:darkwebid`;
- organization: `aot`;
- client: none;
- permission: `observe`;
- approval required: false;
- status: active.

The production authority grant count changed exactly from 163 to 164. The provider-read matcher constrains this grant to active registered read-only capabilities advertised by `darkwebid`; it does not grant Dark Web ID mutation authority.

### Production runtime deployment

The Dark Web ID connector merged through PR #650. The production runtime was activated with:

- `JASON_DARKWEBID_ENABLED=true`;
- role-id path `/run/jason-secrets/openbao/darkwebid/role_id`;
- secret-id path `/run/jason-secrets/openbao/darkwebid/secret_id`;
- both AppRole artifacts mounted read-only from `/var/lib/jason/runtime-secrets/openbao/darkwebid-approle/`.

The hardened runtime deployment passed health verification and retained rollback state. A subsequent normal production refresh advanced the final running source to `d266912382e65e3061c43c87c88f254738ccb4ac`, which is a descendant of the Dark Web ID merge `aa6720bb3c5facdfe3386312e4a5761c61789464`. The Dark Web ID enablement and read-only mounts remained present after that refresh.

### Central Orchestrator production acceptance

A production authority context was issued for `person-al` under `grant-aot-darkwebid-provider-read-observe`, then the live runtime Central Orchestrator executed:

`credential.exposure.organization.search`

with `page=0`, `limit=200`, and `permission_mode=observe`.

Result:

- authority outcome: `allowed`;
- provider selected: `darkwebid`;
- orchestration status: `succeeded`;
- reason: `capability_completed`;
- provider attempts: 1;
- records returned: 15;
- secret values printed: false;
- provider mutation attempted: false.

### MCP production activation and external acceptance

Because Jason MCP composes its own governed runtime application, `jason-mcp-pilot` was separately activated with the same Dark Web ID enablement flag and read-only AppRole mounts. Hardened deployment health passed and `MCP_GOVERNANCE_POSTCHECK=PASS` confirmed Central Orchestrator governance remained active with direct provider access disabled.

The externally connected Jason MCP then discovered the active canonical capabilities `credential.exposure.organization.search` and `credential.exposure.organization.read`. A live `execute_read_capability` call for `credential.exposure.organization.search` completed successfully with:

- provider: `darkwebid`;
- reason: `capability_completed`;
- records returned: 15;
- evidence warnings: 0.

Only status, provider, record count, schema shape, and warnings count were recorded during acceptance. Organization names, domains, email addresses, and credentials were not printed.

## Current operational boundary

Dark Web ID is now a verified production read provider for governed organization inventory. Jason may autonomously use the two registered read-only organization capabilities within their AOT-internal scope and existing authority model. No Dark Web ID create, update, delete, monitored-domain, user, notification, reporting, or other mutation capability is registered or authorized by this activation.

## Next stage

1. Add credential-exposure/live-search resources only from exact vendor-documented endpoints and with client-boundary controls.
2. Correlate Dark Web ID organizations/domains to Autotask companies through the canonical entity-correlation model before exposing client-scoped compromise evidence.
3. Treat all provider-supported writes as separate governed capabilities with exact execution-plan binding, authorization, idempotency where applicable, post-action readback, and explicit rollback/recovery rules.
