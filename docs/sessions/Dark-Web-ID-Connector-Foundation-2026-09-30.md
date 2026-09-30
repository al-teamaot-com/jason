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

## Current operational boundary

The provider credential and provider-backed connector behavior are verified on the Jason host. The feature branch has not yet been merged/deployed into the production runtime container at the time of this record. Therefore the Dark Web ID runtime provider must remain configured/pending deployment verification in the System Registry until a post-deployment Central Orchestrator read succeeds.

## Next stage

After governed merge/deployment:

1. enable `JASON_DARKWEBID_ENABLED=true` with the new read-only AppRole mounts;
2. verify the runtime execution-provider registry selects Dark Web ID for the canonical organization-search capability;
3. execute a post-deployment Central Orchestrator read and record production evidence;
4. promote the System Registry provider lifecycle to verified;
5. add credential-exposure/live-search resources only from exact vendor-documented endpoints and with client-boundary controls;
6. treat all provider-supported writes as separate governed capabilities with exact execution-plan binding, authorization, idempotency where applicable, post-action readback, and explicit rollback/recovery rules.
