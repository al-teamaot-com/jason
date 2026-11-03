# Open-breaker root-worker compatibility preflight — 2026-11-03

## Incident

Exact recovery release `526fcf17ba7f0800ea2a95388d39c0e0ee014a72` was fully reviewed, preproduction eligible, exact-SHA Owner approved and CCC reviewed. Runtime and MCP reached that exact candidate successfully, but the root-owned host reconciler installed from LKG `1b28ddc9863aee563755cb57599cf211ee82ac19` rejected the forward target before candidate host source could install the newer reconciler:

`HostReconcileError: active root policy migration does not belong to target SHA`

The release manager then restored runtime, MCP and manager source to the LKG. The freeze was restored byte-for-byte. Host rollback remained unverified because authority-health evidence was already degraded.

## Defect

The open-breaker recovery admission path proved candidate source policy, exact LKG, live runtime alignment, preproduction, scope review, CCC and signed Owner authority, but it did not prove that the *currently installed root reconciler* understood the separately reviewed forward-recovery contract. Therefore a candidate could pass every user-space recovery gate and still fail only after runtime/MCP production mutation.

## Correction

While the protected circuit breaker is open, the release manager now fails closed unless `/usr/local/lib/jason/release_host_reconcile_worker.py` is a securely root-owned regular file and contains the reviewed forward-recovery contract markers:

- `_forward_recovery_release_authorized`
- `PREVIOUS_MIGRATION_FORWARD_DESCENDANT_VERIFIED`
- authenticated mobile Teams exact-release binding
- `provider_identity_and_authority_recovery`

This is a compatibility preflight only. It grants no authority and does not replace the root worker's independent exact-release, root-policy, Git-lineage or Owner checks. When the breaker is independently closed, ordinary descendant reconciliation remains unchanged.

## Recovery order

The current LKG must first regain a valid full-integrity proof and clean host/drift evidence. Root revalidation may then close the breaker. A fresh candidate/release and fresh exact-SHA Owner approval are required for any subsequent production retry; the consumed `526fcf...` approval is not reusable.
