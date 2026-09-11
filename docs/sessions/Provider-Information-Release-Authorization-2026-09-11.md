# Provider Information Release Authorization — 2026-09-11

## Purpose

Jason provider credentials are execution credentials, not requester disclosure authority. A provider read may therefore be technically fetchable while still being unavailable for use, processing, or release to the authenticated human.

This workstream adds a fail-closed information-authorization boundary between provider execution and evidence release. Production MCP remains intentionally stopped while provider-specific requester authorization is incomplete.

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

The runtime provider-read composition can resolve the authenticated Jason principal through the same durable Microsoft identity-binding database used by conversational ingress (`JASON_TEAMS_IDENTITY_BINDINGS_DB`).

`SQLiteMicrosoftIdentityBindingStore.find_active_by_jason_identity()` returns a binding only when exactly one active Microsoft binding exists for the Jason identity. Zero or multiple matches fail closed. The provider information authorizer prefers this trusted binding and does not allow a request-supplied email address to override it.

Focused tests prove:

- one active binding resolves;
- ambiguous active bindings fail closed;
- trusted binding identity wins over a conflicting request attribute; and
- a missing trusted binding denies release even when an untrusted request attribute would otherwise match provider ACL data.

## IT Glue status

### Document search

The organization document-list API returns document metadata and may return body content. Jason strips body-bearing fields before any potential release. Search results remain non-releasable because per-record requester authorization has not been positively established.

Current handling: `SERVICE_ONLY` / `REQUEST_ACCESS`.

### Exact document read

The documented `GET /documents/:id` API retrieves the complete document. The IT Glue documentation does not document `authorized_users`, `user_resource_accesses`, or `group_resource_accesses` as supported `include` values for this endpoint. An earlier source assumption that requested those includes was removed rather than depending on an undocumented authorization surface.

The authorizer has an ACL-mirroring adapter capable of evaluating explicit authorized-user relationship evidence when such evidence is supplied by a verified source. Normal exact document reads do not currently have a documented per-resource ACL read source, so they fail closed when that relationship evidence is absent.

IT Glue documents state that restricted resources use user/group resource-access whitelists and that administrators have global resource access. The public Resource Accesses API surface documents create/update/delete operations, but no read operation was established for retrieving a particular resource's whitelist. `GET /users/:id?check_authorization=Document` exposes authorization at the requested resource-type level; it does not establish authorization to one particular restricted document. Jason therefore does not treat it as per-document disclosure authority.

Current handling for normal provider-backed exact document reads: fail closed pending a positively verified per-resource authorization source or an explicitly approved Jason-managed authorization model.

## Autotask status

Autotask provider reads currently remain service-only and non-releasable under the new information boundary.

Autotask documents `ImpersonationResourceId` for supported REST operations and describes impersonated security-level requirements, but this workstream has not established that adding the header to every GET/query is a trustworthy enforcement of the impersonated user's read visibility for every entity Jason may query. Jason therefore does not infer requester disclosure authority from the API-only integration user's access or from the existence of impersonation support.

Current handling: `SERVICE_ONLY` / `REQUEST_ACCESS`.

## Sensitive evidence

The deterministic sensitivity layer identifies credential assignments, secret fields, private-key material, and recognizable token-like material without storing detected secret values in authorization decisions. When a source-authorized IT Glue document is sensitive, its handling class becomes `DERIVED_OUTPUT_ONLY`.

Source authorization and disclosure format are therefore separate decisions: permission to access a source does not automatically authorize verbatim release of secrets.

## Verification

Focused GitHub Actions workflow: `Validate Information Authorization Boundary`.

The focused workflow compiles and tests:

- information authorization contracts;
- information release boundary behavior;
- sensitivity classification;
- provider-read information authorization;
- trusted Microsoft/Jason binding behavior;
- IT Glue operation construction; and
- runtime provider-read identity-binding composition.

At commit `f05c8662df64488df7149c614c9a69ff826faed6`, focused run `34598673402` completed successfully.

Broad repository workflows currently contain unrelated pre-existing Conversation Experience/runtime test failures. Those are not being repaired or masked by this security workstream.

## Production state

- Production MCP remains intentionally stopped.
- No provider write was performed.
- No authority grant was broadened.
- No provider credential was changed.
- No provider payload or secret was committed.
- No production activation was performed from this security branch.
- Earlier provider-read PR #171 remains draft and unmerged.

## Blocking decision before release

Jason needs a positive requester-authorization basis for each provider/resource class before those results may be released. For IT Glue restricted documents and Autotask reads, the currently verified provider APIs do not yet supply enough evidence to make that decision safely.

The acceptable next architecture must be one of:

1. a documented provider-enforced/delegated/impersonated authorization mechanism that can be proven to enforce the actual requester's read visibility; or
2. an explicitly governed Jason-managed authorization model designated as an authoritative disclosure policy, with scope, ownership, synchronization, exceptions, audit, and fail-closed behavior defined before activation.

Until one of those bases is established, Jason may fetch using its service identity only where execution authority permits, but it must not use/process/release that evidence to the requester.