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
and invoice descriptors. The conditional Restricted path now projects only
contract relationship identifiers, unit counts, and start/end dates; cost,
price, invoice descriptions and internal currency fields are suppressed even
when the provider ignores field selection. An explicit sensitive-field
selection is rejected before a provider record query. AOT-wide requester
access is NOT implied by the parent query; existing JKD-001 observe grants
and internal-only information-release authorization remain mandatory.
A reviewer must verify actual production grants before promoting this
AOT-internal cross-client capability.

**Residual risks:** Provider `Restricted` meaning may differ by entity and
may still deny actual record queries. The parent proof does not make the
provider's conditional rights unconditional. Real provider outcomes,
client-disclosure refusals, pagination and completeness remain unverified.
No live/production acceptability claim is made from synthetic transport tests.

**Acceptance disposition:** CONDITIONAL / NOT APPROVED FOR PRODUCTION until
independent code/security review, live provider record proof through a governed
preproduction environment, exact immutable release candidate, signed Teams
Owner decision, current breaker remediation and protected rollback evidence.

## Verified production baseline / release boundaries

- Source candidate is NOT the current production release and is not a rollback.
- Protected origin/main at review: 65e2f18b051e3dda54c4cbb4411b9aae27831602.
- Live host `/opt/jason/current` on 2026-11-09: aa6fa38a29b803e11ada63afb3cf25d17b7daf44.
- Read-only protected control readback reports last-known-good release-aa6fa38a29b803e1; the true release rollback must be pinned and revalidated against the native manager's protected LKG and artifact digests before a release record is prepared.
- Production deployment freeze is active. On 2026-11-09 at 19:00 UTC the production drift watchdog opened the circuit breaker (`continuous_production_drift_detected`, problem_count=4). Native protected drift evidence is not accessible to the unprivileged reviewer; no bypass or blind reset is permitted.
- Nine CI workflows passed on the preceding candidate. The final amended SHA must rerun all required checks.
- An actual release candidate must be the immutable PROTECTED MAIN SHA (not the PR branch SHA), with pinned rollback, immutable runtime/MCP images, reviewed full merged scope, baseline, native preproduction, signed Teams approval and authorized one-transaction freeze exception.
- Teams Graph discovery via the connected account returns no teams and list_chats returned HTTP 403 (Microsoft reports missing Office 365 license). Do not confuse an ordinary Teams message with a signed Jason release approval.

## Audit acceptance plan

1. Use only the governed service.entity.search path under an authorized AOT human to query an exact test contractID for each of the four permitted relationship entities. No raw provider credentials, direct transport, or write identity.
2. Prove positive provider access or bounded denial on each; verify parent companyID and all child contractID values; resolve serviceID/serviceBundleID and paginate to a complete count.
3. Run negative cases: wrong company/requester, missing parent, malformed rows, mismatched contractID, unexpected prices in responses, repeated/omitted pages and loss of binding. Continue no mutation.
4. Verify prior runtime/host/MCP health, freeze restoration, approved release candidate vs immutable artifact, complete operational smoke and ticket continuity; rollback on failed gates.
