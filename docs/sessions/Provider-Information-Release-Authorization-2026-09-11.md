# Provider Information Release Authorization — 2026-09-11

## Purpose

Jason provider credentials are execution credentials, not requester disclosure authority. A provider read may therefore be technically fetchable while still being unavailable for use, processing, or release to the authenticated human.

This workstream adds a fail-closed information-authorization boundary between provider execution and evidence release. Production activation and provider-specific requester authorization are separate concerns; current production claims must be established from fresh operational evidence rather than this narrative record alone.

## Invariants

- ChatGPT reasons; Jason authenticates, authorizes, governs, executes, audits, and releases only authorized evidence.
- Provider service/API credentials never imply that the requesting human may see everything those credentials can fetch.
- Information authorization is distinct from capability execution authority.
- Authorization is evaluated for FETCH, USE, PROCESS, and RELEASE.
- Missing or indeterminate requester authorization fails closed.
- A denial releases no provider evidence and produces bounded remediation such as `REQUEST_ACCESS` or `REQUEST_APPROVAL`.
- Caller-supplied identity attributes cannot override a trusted Microsoft-to-Jason identity binding.
- Sensitive authorized evidence may be constrained to derived-output-only handling rather than raw disclosure.
- Unknown provider/resource authorization adapters remain service-only by default.

## Trusted requester identity

The runtime provider-read composition resolves an authenticated Jason principal through the same durable Microsoft identity-binding database used by conversational ingress (`JASON_TEAMS_IDENTITY_BINDINGS_DB`).

`SQLiteMicrosoftIdentityBindingStore.find_active_by_jason_identity()` returns a binding only when exactly one active Microsoft binding exists for the Jason identity. Zero or multiple matches fail closed. Provider information authorization prefers this trusted binding and does not allow a request-supplied email address to override it.

Focused tests prove one-active-binding resolution, ambiguous-binding denial, trusted-binding precedence over conflicting request attributes, and denial when a trusted binding is absent.

## IT Glue status

### Document search

The organization document-list API returns document metadata and may return body content. Jason strips body-bearing fields before any potential release. Search results remain non-releasable because per-record requester authorization has not been positively established.

Current handling: `SERVICE_ONLY` / `REQUEST_ACCESS`.

### Exact document read

The documented `GET /documents/:id` API retrieves the complete document. The IT Glue documentation does not document `authorized_users`, `user_resource_accesses`, or `group_resource_accesses` as supported `include` values for this endpoint. An earlier source assumption that requested those includes was removed rather than depending on an undocumented authorization surface.

The authorizer has an ACL-mirroring adapter capable of evaluating explicit authorized-user relationship evidence when such evidence is supplied by a verified source. Normal exact document reads do not currently have a documented per-resource ACL read source, so they fail closed when that relationship evidence is absent.

IT Glue documents that restricted resources use user/group resource-access whitelists and that administrators have global resource access. The public Resource Accesses API surface does not establish a documented read operation for retrieving one document's effective whitelist. `GET /users/:id?check_authorization=Document` is resource-type authorization and is not treated as proof of access to one specific restricted document.

Current handling for normal provider-backed exact document reads: fail closed pending a positively verified per-resource authorization source or an explicitly approved Jason-managed authorization model.

## Autotask status

Autotask has a documented provider-native resource impersonation mechanism using the `ImpersonationResourceId` request header. Autotask's REST entity overview explicitly lists supported impersonation entities and allows querying for supported entities; Company and Ticket are included. Autotask Resources represent user accounts whose access is governed by assigned license/security level.

Jason now has a narrow source implementation for provider-enforced requester impersonation:

1. Resolve the already-authenticated Jason principal through the durable Microsoft/Jason binding.
2. Use only that trusted binding's email address to query Autotask `Resources` internally.
3. Require exactly one active matching Autotask Resource; zero or multiple matches fail before the target read.
4. For the initial approved set only, add that Resource ID as `ImpersonationResourceId` to the target Autotask request.
5. Upgrade the information-authorization envelope from service-only only after the impersonated provider request succeeds.

Initial canonical set:

- `service.company.read`
- `service.company.search`
- `service.ticket.read`
- `service.ticket.search`

The provider operations corresponding to that set are `autotask.company.get`, `autotask.company.search`, `autotask.ticket.get`, and `autotask.ticket.search`. Contacts, configurations, ticket notes, schema description, and all other Autotask capabilities remain service-only until independently proven.

### Provider-backed acceptance result

Bounded production diagnostics on 2026-09-11 established that the trusted requester maps uniquely to one active Autotask Resource and that Jason constructs the documented `ImpersonationResourceId` header path. A service-account control query succeeded without requester impersonation, while requester-impersonated Ticket and Company reads returned provider HTTP 500.

Because the failure occurs across both Company and Ticket while the same underlying service-account query path is functional, the remaining blocker is classified as Autotask requester-impersonation configuration/enforcement rather than a ticket-specific lookup problem. No provider payload, resource identifier, or credential value is retained in this record.

The approved least-privilege remediation is limited to:

- allowing the authenticated requester's normal Autotask security level to be impersonated; and
- allowing Jason's API-only integration security level to impersonate only the required Company/Ticket read/query operations.

This approval does **not** authorize Add/Edit/Delete permissions, unrelated entities, provider writes, or a service-account disclosure fallback. If Autotask cannot express the required read/query-only impersonation scope without materially broader rights, stop before broadening authority and obtain a separate decision.

After configuration is changed, acceptance must be repeated through the governed Jason path. Success requires the provider request to succeed under requester impersonation and the information-release boundary to remain authoritative. A successful service-account read alone is not acceptance.

## Sensitive evidence

The deterministic sensitivity layer identifies credential assignments, secret fields, private-key material, and recognizable token-like material without storing detected secret values in authorization decisions. Sensitive source-authorized evidence is classified `DERIVED_OUTPUT_ONLY` instead of raw releasable evidence.

Source authorization and disclosure format are therefore separate decisions: permission to access a source does not automatically authorize verbatim release of secrets.

## Verification

Focused GitHub Actions workflow: `Validate Information Authorization Boundary`.

The focused workflow compiles and tests information authorization contracts, release-boundary behavior, sensitivity classification, provider-read authorization, trusted Microsoft/Jason binding behavior, IT Glue operation construction, Autotask impersonation identity mapping/fail-closed behavior, Autotask information-envelope upgrades, and runtime provider-read composition.

At commit `92bdbd32a07153107f892dbbf0079f9755205048`, focused run `34599450212` completed successfully.

Broad repository workflows contain unrelated pre-existing Conversation Experience/runtime test failures. Those are not being repaired or masked by this security workstream.

### MCP capability-discovery correction

A separate model-facing discovery defect was identified during the Autotask investigation. `discover_capabilities` treated the requested operation as an exact registry metadata filter, so a conversational request interpreted as `ticket/read` could return zero exact matches even though active `service.ticket.search` was the supported exact-ticket lookup path.

Source commit `b36d39ff044ea9eec4b371b0d0010ef00264ca9e` adds fail-closed same-resource alternative guidance without activating a new capability or bypassing execution authorization. Exact operation matching remains exact; alternatives are discovery guidance only.

This discovery correction does not resolve the Autotask provider HTTP 500. The provider impersonation acceptance gate remains independent.

## Production observation — 2026-09-11

Fresh read-only host inspection observed the MCP service running as container `jason-mcp-pilot` from image `jason-mcp:information-auth-568a9b984ad7`. The container had restart policy `no` and no Docker healthcheck. Its Docker labels exposed a Compose project/service name but no Compose working-directory or Compose-file path. The separate `jason-runtime` container was healthy and Compose-managed from a deployment snapshot under `/home/al/jason-deployments/`.

The protected primary worktree `/home/al/projects/jason` was dirty and is not an approved deployment source. An isolated worktree contained the MCP discovery source commit. Existing rollback MCP containers/images remained preserved.

These are point-in-time observations, not permanent topology authority. Future deployment must re-derive current state. The operational reconstruction/recovery rules are documented in `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md`.

At this observation point:

- provider writes: none;
- direct provider disclosure fallback: none;
- authority broadening by Jason source: none;
- IT Glue restricted-document release: still fail closed;
- Autotask Company/Ticket requester impersonation: blocked by provider HTTP 500 pending least-privilege Autotask security configuration;
- MCP capability-discovery fix at `b36d39ff044ea9eec4b371b0d0010ef00264ca9e`: source-durable but not yet proven as the running production MCP image.

## Remaining release gates

Jason needs a positive requester-authorization basis for every provider/resource class before those results may be released.

For the initial Autotask Company/Ticket set, the source architecture now has a documented provider-enforced impersonation basis, but production acceptance still requires successful requester-impersonated reads after the approved least-privilege Autotask configuration is applied.

For IT Glue restricted documents, no positively verified per-document requester-authorization read source has been established.

An IT Glue release path therefore still requires either a documented provider-enforced/delegated authorization mechanism that can be proven against the actual requester, or an explicitly governed Jason-managed authorization model designated as authoritative disclosure policy with scope, ownership, synchronization, exceptions, audit, and fail-closed behavior defined before activation.

Until those gates are satisfied, Jason may fetch using its service identity only where execution authority permits, but the information-release boundary prevents unverified evidence from being used, processed, or released to the requester.
