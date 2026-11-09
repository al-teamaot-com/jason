# Autotask conditional contract reads - engineering candidate #2385

Status: source-only. Not merged, activated or deployed. Production freeze remains.

## Evidence
On 2026-11-09 the governed Autotask entity information returned Restricted query access for ContractServices, ContractServiceUnits, ContractServiceBundles and ContractServiceBundleUnits. Owner verified the read-only API security level shows Contracts View=All and Contract Visibility=Full. The existing dynamic reader intentionally denied Restricted.

## Proposed bounded behavior
Only ContractServices and ContractServiceBundles may use a conditional path. Require exact positive contractID equality, preserving contractID under projection. On every read verify provider entity/field metadata; query the exact Contracts parent using the same read-only credential and require a unique match with positive companyID. The native provider still authorizes the child query. Deny any result outside the requested parent or with malformed values. Other Restricted entities remain denied. Existing Jason identity, requester authorization, Central Orchestrator, JKD-001 and information-release gates remain in force. No provider writes.

## Remaining acceptance
- Security review of company/requester binding, parent-child and disclosure boundaries.
- Live positive and negative Autotask contract read acceptance, including pagination and unauthorized parent, with no permission bypass.
- Governed release evidence, exact candidate and rollback SHA, Teams Owner approval before any activation or production deployment, and subsequent operational verification.
- Complete Phase 1 service-to-contract dependency audit after successful authorized reads.

Synthetic tests are not evidence that the live Restricted provider records are queryable.
