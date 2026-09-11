# Provider Information Release Authorization — 2026-09-11

## Purpose

Jason provider credentials are execution credentials, not requester disclosure authority. A provider read may therefore be technically fetchable while still being unavailable for use, processing, or release to the authenticated human.

This workstream adds a fail-closed information-authorization boundary between provider execution and evidence release. Production MCP remains intentionally stopped while provider-specific requester authorization is completed and provider-backed acceptance is performed.

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

This is still source-only authorization. Before production release, bounded provider-backed acceptance must prove that the AOT Autotask API-only security level permits resource impersonation for the selected query operations and that the trusted Jason principal maps uniquely to an active Autotask Resource. Jason will not change Autotask security-level configuration as part of acceptance.

## Sensitive evidence

The deterministic sensitivity layer identifies credential assignments, secret fields, private-key material, and recognizable token-like material without storing detected secret values in authorization decisions. Sensitive source-authorized evidence is classified `DERIVED_OUTPUT_ONLY` instead of raw releasable evidence.

Source authorization and disclosure format are therefore separate decisions: permission to access a source does not automatically authorize verbatim release of secrets.

## Verification

Focused GitHub Actions workflow: `Validate Information Authorization Boundary`.

The focused workflow compiles and tests information authorization contracts, release-boundary behavior, sensitivity classification, provider-read authorization, trusted Microsoft/Jason binding behavior, IT Glue operation construction, Autotask impersonation identity mapping/fail-closed behavior, Autotask information-envelope upgrades, and runtime provider-read composition.

At commit `92bdbd32a07153107f892dbbf0079f9755205048`, focused run `34599450212` completed successfully.

Broad repository workflows contain unrelated pre-existing Conversation Experience/runtime test failures. Those are not being repaired or masked by this security workstream.

## Production state

- Production MCP remains intentionally stopped.
- No provider write was performed.
- No authority grant was broadened.
- No provider credential was changed.
- No provider payload or secret was committed.
- No production activation was performed from this security branch.
- Provider-read PR #171 remains draft and unmerged.
- Information-release PR #174 remains draft and unmerged.

## Remaining release gates

Jason needs a positive requester-authorization basis for every provider/resource class before those results may be released.

For the initial Autotask Company/Ticket set, the source architecture now has a documented provider-enforced impersonation basis, but production acceptance is still required. For IT Glue restricted documents, no positively verified per-document requester-authorization read source has been established.

An IT Glue release path therefore still requires either a documented provider-enforced/delegated authorization mechanism that can be proven against the actual requester, or an explicitly governed Jason-managed authorization model designated as authoritative disclosure policy with scope, ownership, synchronization, exceptions, audit, and fail-closed behavior defined before activation.

Until those gates are satisfied, Jason may fetch using its service identity only where execution authority permits, but the information-release boundary prevents unverified evidence from being used, processed, or released to the requester.