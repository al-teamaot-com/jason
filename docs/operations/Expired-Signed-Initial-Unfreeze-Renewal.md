# Production Release — Expired Signed Initial Unfreeze Renewal

**High-risk governance:** This changes the production release authorization flow and
must be classified as `production_control_core` regardless of the original
candidate's file-based risk label. No direct production-host patch, approval
expiry edit, control-state edit, signed-evidence replay, or provider bypass is
authorized by this document.

## Incident and accepted state

On 2026-11-07, the exact candidate
`d6fa0d8d8c1524b9487258b0e7f71230a278906e` completed all isolated
preproduction checks, and a separate authenticated Teams Owner approval and
signed initial one-transaction unfreeze were recorded. The latter expired at
`2026-11-07T22:28:22.319460+00:00` before native promotion began.

The original release remained `production_eligible`, and production remained
frozen at LKG/rollback `75a4c5e3e6a27a563a59653e514db38ba69a11fa`.
The `approval-only-held` worker reported `NO_OWNER_ACTION_REQUIRED` because
the Owner and CCC approvals had already been accepted. An existing operator
renewal command covers **expired undecided requests only**; it deliberately
rejects a release with an approved signed decision and does not apply here.

## Supported renewal semantics

This implementation recognizes an **unused, expired** signed initial unfreeze
source only when all identity, receipt-hash, source-SHA, scope, rollback,
freeze-fingerprint, prior signed evidence, and production-state checks pass.
There must be no previous native transaction receipt, no consumed original
source, no altered receipt and no existing renewal pointer.

1. The approval-only worker publishes a distinct, nonexecuting
   `initial_unfreeze_renewal_only` Teams offer for the **same** existing
   protected-main release. The offer contains the original signed receipt's
   SHA256, original approval ID, scoped freeze fingerprint and the same
   immutable candidate, rollback and reviewed-scope digest.
2. Teams creates **one new card**, with a new challenge and approval ID. A
   fresh, authenticated human Owner signature is essential. The previous
   signature, approved release, original CCC review, and original unfreeze
   receipt are **not** reused as a new decision.
3. The independent host consumer rechecks the signed Teams envelope, Entra
   binding, original Owner approval and CCC evidence, challenge, full card
   reconstruction, exact main SHA, release record and predecessor lineage.
   The card alone cannot execute production or grant additional privileges.
4. Only after a new valid signed decision does Release Manager persist a new
   immutable `owner-signed-initial-unfreeze-renewals/<release-id>--<approval-id>.json`
   receipt and a SHA256-bound single-use pointer in the release record.
   The original expired signed receipt stays byte-for-byte unchanged.
5. Under the native exclusive production lock, Release Manager enforces the
   **new** receipt's 15-minute maximum expiry, exact current freeze SHA256,
   candidate/rollback/scope, active source, and unused status. One controlled
   transaction may then begin. Native restoration must return the original
   freeze byte-for-byte and consume only the new signed renewal receipt.
6. An interrupted/failed transaction must use the existing crash-recovery
   and rollback controls. A further card cannot be issued by silently resetting
   expiration, replaying evidence, or ignoring a prior native transaction.

This change intentionally allows no standing release authority and performs
no unattended production promotion.

## Acceptance / negative cases

- Original expired signed decision is **not** accepted for promotion.
- New Teams offer requires a fully approved original release/CCC and an
  intact, unused, expired original unfreeze with active original freeze.
- Already consumed, unexpired, altered, wrong Owner, wrong company or source
  scope, changed rollback/freeze, existing native transaction or duplicate
  renewal fails closed.
- Callback requires correct signed challenge and independently rechecks
  original signed CCC material review. One recorded renewal is idempotent
  only for the same exact new signed evidence, never an unrelated decision.
- Native transaction and freeze restoration preserve original signed receipt;
  the new receipt is consumed exactly once and cannot replay.
- Isolated tests cover both signed-callback/consumer and host freeze lifecycle.
  Live tests are still required after a separately authorized production
  release of the control change.

## Explicit release boundaries

This source must not be installed directly into `/opt/jason/current`. Follow
protected-branch CI, high-risk code review, immutable release SHA and rollback
verification, Owner-approved production-control release, signed freeze
authorization and postproduction checks. A bootstrapping problem remains:
the installed old release manager has no post-approval renewal path. No
preproduction test or user message implicitly authorizes a temporary bypass.

After a production release safely provides this behavior, the AOT Owner must
accept a **fresh signed Teams renewal card** for the original
`d6fa0d8d8c1524b9487258b0e7f71230a278906e` candidate, then the native
release must pass its current gates before any production mutation. Owner
identity binding recovery and XYZ client notification execution are **separate**
operations; neither is authorized by this renewal implementation.
