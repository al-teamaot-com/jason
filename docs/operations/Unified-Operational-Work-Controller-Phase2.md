# Unified Operational Work Controller - Phase 2 admission gates

Governing issue: #1196. The authoritative controller remains the existing
owner-approved development worker and TODO release bridge; this change does
not create another queue or scheduled worker.

## Governing declarations
An issue may declare `Governing release dependencies` and/or
`Governing operational dependencies`. Both declarations, when present,
must match the live TODO ledger exactly. At least one nonempty declaration
is required for dependency-based automatic readmission. Arbitrary,
malformed, or missing declarations do not confer execution authority.

## Evidence and resumption
Release prerequisites require an exact closed, verified Release Manager
record. Operational prerequisites require a trusted, issue-scoped,
unexpired, non-revoked Ed25519 receipt from the protected operational
acceptance location. For combined gates, every declared release and
operational prerequisite must pass.

The worker re-reads protected evidence immediately before a bounded
readmission. Existing issue-level holds, support-first capacity limits,
source pinning and owner-approved development boundaries still apply.
The persistent exactly-once fingerprint includes declared release IDs
and verified operational evidence references. Re-running the same proof
does not admit an item twice.

## Verification boundary
Regression tests with ephemeral signed receipts demonstrate valid
operational-only admission and fail-closed behavior with missing or
revoked evidence. These are synthetic tests, **not** owner operational
acceptance for any actual client or TODO item.

Phase 2 is not operationally complete until a genuine issue-scoped
acceptance receipt and real previously blocked item pass the live
controller and audit readback. Production deployment requires the
existing exact-commit owner approval and governed Release Manager.
