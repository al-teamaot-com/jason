# Autotask Read Repair — Preproduction (2026-10-28)

## Scope
These changes are NOT production approved. Use the Production Manager for any promotion.

- Company-name selector uses bounded provider-native contains matching; resource IDs remain exact, with bounded pagination.
- Actively bound AOT technician identities can derive a short-lived exact company read context for contract search/read only when an exact observe grant is already allowed and the company is verified through governed read. Existing Owner access remains valid. Unbound, client-bound, or non-AOT identities cannot select arbitrary companies.
- Other sensitive read families retain their existing Owner-only policy.
- Time-entry capability stays fail-closed until provider-native requester authorization is demonstrably verified.

## Preproduction acceptance gates
1. Focused contract-context, company selector, labor-read and negative authorization tests.
2. Provider read, security and documentation CI workflows.
3. Demonstrate partial company-name search and pagination on preproduction.
4. Demonstrate contract search/read for approved AOT staff and reject wrong-company or unbound access.
5. Prove permitted TimeEntries requester impersonation on a populated ticket, with scoped row verification.
6. Require PM-controlled release, source pin, rollback and post-release readback.

## Known limitations
- Unit tests do not constitute live preproduction provider acceptance.
- Broad cross-customer contract enumeration remains unavailable without an explicit scope model.
- Time-entry provider-backed read remains blocked pending permission evidence.

## Live metadata evidence — 2026-10-28
Using governed service.entity.describe against live Autotask:
- TimeEntries: canQuery=true, userAccessForQuery=All, create/update/delete=Restricted.
- Contracts: canQuery=true, userAccessForQuery=All, create/update/delete=None.

These describe responses demonstrate entity query visibility for the current API metadata context, **not** that requester-specific native impersonation has been verified. The explicit labor read gate remains DENY. Preproduction must prove the native requester header and provider enforcement (including a denied unauthorized requester) before activating the labor read. No production environment flags should be changed as a substitute for proof.

## Isolated host acceptance — 2026-10-28
- Isolated Git worktree: /home/al/jason-worktrees/autotask-read-preprod-20261028; source pin f74a704eec200550c94eae20af9d71c327f73b3c prior to this documentation addition.
- Ran 74 automated tests successfully across contract context, provider read foundation, native-labor connector simulations, company adapter, and requester information authorizer.
- All tests used local source with mock/fake provider transport where applicable; no production container, environment configuration, or database was modified.
- Latest pre-documentation commit CI: nine workflows successful.
- A separately deployed preproduction MCP with isolated authority stores and independently authorized Autotask credentials has NOT been provisioned; do not claim live preproduction acceptance.
- Native technician time-entry query permission is NOT yet proven against a real provider requester; keep the permission gate disabled until authorized positive and negative provider-backed tests are available.
