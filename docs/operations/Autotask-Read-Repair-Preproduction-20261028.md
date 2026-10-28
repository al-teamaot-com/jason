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
