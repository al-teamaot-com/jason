# Requester-authorized read parity for Autotask

**Status:** Design and unactivated implementation in progress (2026-10-27).
**Owner directive:** Jason should discover all legitimate read-only data paths and answer any authenticated technician to the extent their **source-portal** permissions permit. Missing a prebuilt read capability is an engineering defect to investigate, not a reason to declare the data unavailable.

## Boundaries

1. **FETCH and RELEASE are different:** an Autotask API-only integration account may fetch more than an ordinary technician. Its permission to query an entity does not prove the requesting person may view it.
2. Resolve the requester from verified Microsoft tenant/object identity and Jason's active binding. Map to exactly one active Autotask Resource; unknown, disabled or ambiguous mappings fail closed.
3. Prefer provider-native delegated/impersonated **read** enforcement only after a positive/negative controlled test proves it applies to the exact query, including company, resource, billing, protected fields and nonbillable time. An impersonation header alone is not evidence of read authorization.
4. Where reliable source ACL/restriction evidence is returned, evaluate it before information release. An explicit denial always wins; missing or unverifiable ACL evidence fails closed for protected records.
5. If a source offers no reliable read delegation/ACL interface, build and certify a requester-specific read path (for example, security-level-matched API-only credential with continuous drift checks, or a properly authenticated delegated UI read). Neither approach may broaden a person's source permissions. Do not use unrestricted service-account query output as a substitute.
6. Do not expose provider secrets, customer-protected information, credentials, personally sensitive fields, internal cost fields, or restricted time entry details to unauthorized users. Preserve traceable resource and field authorization decisions.
7. All reads must use registered provider-neutral capabilities via Central Orchestrator; no direct agent/provider bypass, independent grants, new write capabilities, destructive actions or approval-rule weakening.

## Capability discovery

After source admission, Jason's integration should discover documented queryable entity families from a versioned provider metadata/specification catalog rather than manually inventing a one-off tool per question. Map source entities to canonical resource types and permitted selectors. Only allow read-only methods with bounded paging and query-field validation. Child records require verified parent/tenant/company scope. If a resource is unknown to the catalog, validate it under the normal provider onboarding and security process rather than guessing raw API URLs.

## Missing-read behavior

When an authorized user asks for accessible data that Jason cannot return, Jason should:
1. Search the active governed catalog and alternate equivalent read sources.
2. Determine whether the problem is identity binding, provider capability registration, query construction, unsupported vendor API, permissions, or a technical failure.
3. Retry only safe bounded read attempts, never fallback to an unrestricted API token or silently omit pages.
4. Persist an engineering defect with exact missing object and authorization evidence, alert the proper technical owner, and give the requester the actual cause/status. Never claim that unavailable or unverified data was checked.

This policy does **not** promise to return data for which no authorized read mechanism exists, nor does it allow privileged service credentials to bypass native portal access limitations.

## Current Autotask technical facts

Autotask's documented REST API requires an API-only user account. The default API-only security level grants broad administrator-like API access; custom copies can narrow it. Autotask documents ImpersonationResourceId primarily for operations performed on behalf of another user, not as a blanket guarantee that every GET/query is filtered to the impersonated technician's view. AOT's earlier read-impersonation probes returned HTTP 500. The accepted ADR-011 implementation therefore uses a Jason-managed information-release boundary for existing registered reads.

The first requested gap is canonical `service.ticket.time.entry.search`, which searches the documented `TimeEntries/query` endpoint with exact ticketID and a verified ticket-to-company preflight. The draft also checks returned row ticketID before release. **Production may not expose this labor capability until the technician-specific read authorization proof is completed.** Existing service-account-backed `jason_managed` must fail closed for labor reads. The additional runtime gate `JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN=verified` defaults to DENY and must only be set after positive and negative live Autotask permission tests. A configured flag is evidence of operator attestation, not itself proof of the provider's authorization behavior.

Canonical `service.entity.describe`, `service.entity.fields.describe` and `service.entity.udf.fields.describe` expose **schema metadata only** for syntactically valid entity names. They do not extend record-query permissions. Metadata returned is associated with the API integration account and cannot be used as the technician's own `userAccessForQuery` proof. Entity paths are validated to avoid URL or query injection.

## Production acceptance

- Positive Autotask read test under a technician who is allowed to view ticket time.
- Negative test under an active technician denied that company's ticket; confirm **zero records** released.
- Negative test under a technician who cannot view nonbillable entries; confirm no nonbillable content released, even if an API user could retrieve it.
- Cross-client and wrong parent-ID attempt denied before releasing content; no pagination gaps, duplicate rows, or unauthorized field leaks.
- Assert status/authority and read-only behavior on all exposed capabilities.
- Register and test the provider catalog, record exact source revision, run governed release/readback and verify production, including T20261026.0027.
- Verify no time entry, ticket, or other provider record is modified; no privileged credentials or ACL metadata are exposed.

## Source references

- [ADR-011 — Provider Read Requester Authorization](../decisions/ADR-011-Provider-Read-Requester-Authorization.md)
- [J-405 — Platform Integrity and Boundary Enforcement](../standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md)
- [Autotask REST security and authentication](https://www.autotask.net/help/DeveloperHelp/Content/APIs/REST/General_Topics/REST_Security_Auth.htm)
- [Autotask TimeEntries REST entity](https://www.autotask.net/help/DeveloperHelp/Content/APIs/REST/Entities/TimeEntriesEntity.htm)
- GitHub issues [#2059](https://github.com/al-teamaot-com/jason/issues/2059), [#2060](https://github.com/al-teamaot-com/jason/issues/2060).
