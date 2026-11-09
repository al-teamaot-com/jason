# Autotask conditional contract reads - engineering candidate #2385

Status: source-only. Not merged, activated or deployed. Production freeze remains.

## Evidence
On 2026-11-09 the governed Autotask entity information returned Restricted query access for ContractServices, ContractServiceUnits, ContractServiceBundles and ContractServiceBundleUnits. Owner verified the read-only API security level shows Contracts View=All and Contract Visibility=Full. The existing dynamic reader intentionally denied Restricted.

## Proposed bounded behavior
Only the four contract-scoped service, service-unit, bundle and bundle-unit entities may use a conditional path. Require exact positive contractID equality, preserving contractID under projection. On every read verify provider entity/field metadata; query the exact Contracts parent using the same read-only credential and require a unique match with positive companyID. The native provider still authorizes the child query. Deny any result outside the requested parent or with malformed values. All other Restricted entities remain denied. Existing Jason identity, requester authorization, Central Orchestrator, JKD-001 and information-release gates remain in force. No provider writes.

## Remaining acceptance
- Security review of company/requester binding, parent-child and disclosure boundaries.
- Live positive and negative Autotask contract read acceptance, including pagination and unauthorized parent, with no permission bypass.
- Governed release evidence, exact candidate and rollback SHA, Teams Owner approval before any activation or production deployment, and subsequent operational verification.
- Complete Phase 1 service-to-contract dependency audit after successful authorized reads.

Synthetic tests are not evidence that the live Restricted provider records are queryable.

## Authorization review (2026-11-09)

**Scope:** An explicit source-policy expansion from `All`-only reads to narrowly
filtered `Restricted` reads for four contract-child collections. This is not
a permission grant to the provider API account. Autotask's native query still
makes its own record-access decision. It does not enable mutations.

**Requester gate:** The v13 generic schema reader requires an authenticated
`person-` principal, AOT organization, an unbound customer client, observe mode,
`jason_managed` authorization, registered provider read capability, and
Central Orchestrator/JKD-001 authorization. The post-provider information-release
authorizer independently denies customer-bound identities. These existing
controls are NOT changed by this candidate.

**Provider gate:** EntityInformation must prove `canQuery=true`, with
`userAccessForQuery=Restricted` or `All`. Only the four named collections accept
Restricted, and only with one exact positive integer contractID equality filter.
The same read-only credential queries the exact parent Contracts record with
bounded MaxRecords=2; exactly one positive companyID and matching contract ID
are required. The provider child query may still return 401/403/404 or a
filtered subset; there is no retry under write credentials and no alternate
provider transport. Unexpected child contract IDs fail closed.

**Financial/PII exposure:** Child records may carry cost, price, unit quantity,
and invoice descriptors. AOT-wide requester read grants must be expressly
reviewed; do not assume contract-parent readability grants all technicians
financial-disclosure authority. Before release, require a reviewer to confirm
whether existing JKD-001 `service.entity.search`/read grants and information
sensitivity classification are sufficient. If not, add a governed
field-minimization/Owner-only guard and rerun regressions rather than promoting.

**Residual risks:** Provider `Restricted` meaning may differ by entity and
may still deny actual record queries. The parent proof does not make the
provider's conditional rights unconditional. Real provider outcomes,
client-disclosure refusals, pagination and completeness remain unverified.
No live/production acceptability claim is made from synthetic transport tests.

**Acceptance disposition:** CONDITIONAL / NOT APPROVED FOR PRODUCTION until
independent code/security review, live provider record proof through a governed
preproduction environment, exact immutable release candidate, signed Teams
Owner decision, current breaker remediation and protected rollback evidence.
