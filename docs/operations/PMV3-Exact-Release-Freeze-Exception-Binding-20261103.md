# PMV3: exact release freeze-exception binding (2026-11-03)

## Why this release candidate exists

An earlier protected-main candidate, `e330dc0e229a02e15f77f620ebc2a5c01d4a70d9`, passed preproduction and obtained an authenticated Teams release approval. Its existing prepared release record and manifest nevertheless omitted the already-declared `one_transaction_freeze_exception`. The native promotion correctly denied production because the distinct Owner-ordered `production-deployment-freeze` marker remained active. **No production mutation occurred.** A signed deploy approval alone cannot repair an approved record's missing freeze-exception binding.

## Governed disposition

The source's existing `config/production-deployment-freeze-exception.json` is renewed here to a short, finite expiry to allow **a new immutable candidate and fresh exact-SHA decision**. The declaration authorizes no action on its own. The exact candidate's release record and immutable manifest must BOTH include the source declaration before any Teams approval is solicited. The Owner approval must bind that exact purpose, SHA, rollback and reviewed scope. The native one-transaction freeze exception is permitted only through the approved `provider_identity_and_authority_recovery` profile and only when every required runtime/MCP/host/CCC/root/rollback control passes. The original freeze marker must be byte-identically restored after the deployment transaction, whether it succeeds or fails.

The frozen predecessor's already signed `e330...` record remains immutable and cannot be reused, reset, patched, or re-labeled. The global `unfreeze-release` workflow is a separate Owner decision; do not use it as a substitute for the source-bound, auto-restored one-transaction exception. Do not rewrite Owner approval sources or directly unlink the freeze marker.

## Acceptance requirements

1. The new source SHA descends from protected main, and protected CI passes.
2. Use the **exact new candidate** controller for fresh preparation, not the older installed LKG Release Manager; confirm `record.one_transaction_freeze_exception` and `release_manifest.one_transaction_freeze_exception` both equal the source declaration.
3. Repeat immutable preproduction, full impact/parallel-work review, and exact LKG rollback readiness.
4. Publish a **new** nonexecuting Teams Owner approval offer whose purpose includes the freeze exception. Explicitly authorized production deployment is a separate future action; no approval is implied here.
5. Native PMV3 promotion must independently enforce the one-time freeze exception, preserve source/Owner/CCC bindings, and restore the freeze marker. Do not deploy if the exception expires or any protected check fails.
6. Afterward, verify host, runtime, MCP, root drift, LKG, ticket/provider canaries, and frozen-state restoration. Only then return to PMV3 integration PR #2280 and KFS PR #2282.

## 2026-11-04 follow-up: distinct direct Owner unfreeze after an earlier Teams release approval

An earlier exact-SHA signed Teams **deployment** approval and a later direct
Owner **global unfreeze** decision are separate governance events. Previously,
`unfreeze-release` accepted only a release record with
`owner_approval.source=explicit_owner_instruction`, so an already-approved
candidate with a signed Teams source could not be unfrozen without overwriting
or falsely relabeling the signed record. Never do that.

The source-only release-manager correction introduces the optional exact scope
and rollback inputs to `unfreeze-release`:

- `--explicit-unfreeze-scope-sha256` — the current **64-digit hex** native
  `manual_scope_review.scope_sha256` that the Owner explicitly approved.
- `--explicit-unfreeze-rollback-sha` — the current exact 40-character rollback
  commit approved in the same instruction.

The original signed Owner release approval is preserved byte-for-byte in the
record. The distinct CLI Owner decision is only admitted when the signed source
matches the authenticated mobile Teams receipt format; the candidate is
already `production_eligible`; current protected `main`, native scope review,
last-known-good live alignment, freeze marker and exact candidate identity are
verified; and both explicit unfreeze inputs exactly match the **current**
recorded scope and rollback. Other approval sources are denied. The written
separate unfreeze receipt retains `prior_release_approval_source`,
`owner_approval_source=explicit_owner_instruction`, and the exact release/
scope/rollback/freeze identities; no standing deployment or provider authority
is granted. After a mismatched or missing distinct instruction, the freeze
marker remains untouched.

This is a **source-only change** until separately merged and admitted through
PMV3. It is not permission to execute an edited release controller against an
older pinned production candidate or to rewrite frozen production records.
If open PRs or parallel development change the current scope digest after the
Owner named it, the new SHA/digest must be reviewed and explicitly approved;
no prior approval may be silently rebound.

### Concurrent code-review coordination

Before integrating this correction, compare the separate release-manager PRs #2279 (approval-only reconciliation), #2158 and #2153 (deployment and host-unit verification), and #2156 (production freeze, root admission, and rollback). Their current patches do not touch the new `owner_unfreeze_release` decision branch directly, but their shared release-manager surfaces require fresh integration and frozen-production regression checks. Recording this coordination does not approve or merge those PRs.

### 2026-11-04 production-safety correction: the direct unfreeze is one transaction only

The distinct direct Owner `unfreeze-release` step **records an authorized-pending
receipt without deleting or altering the active production freeze marker**. This
changes the earlier proposed behavior because leaving production unfrozen after
a stand-alone CLI operation violates the Governance Handbook's completion
standard. The receipt is bound to the exact candidate SHA, current native
scope digest, verified rollback SHA, original signed Teams deployment source,
and byte identity of the existing freeze marker. It has a fifteen-minute
acceptance window; expired, missing, mismatched, malformed, already consumed,
symlinked or changed receipts fail closed.

The **native production transaction** remains the sole place where the marker
may be temporarily removed. While holding the existing production transaction
lock, PMV3 revalidates all existing protected-main, host, rollback, scope and
admission checks; requires the normal circuit breaker to be CLOSED (no
unreviewed open-breaker bypass), checks the exact pending receipt digest again,
and uses the existing one-transaction freeze-backup and journal flow. The
transaction restores the original marker byte-for-byte and then marks the
explicit receipt consumed. The existing interrupted-transaction restoration
path now recognizes the distinct explicit Owner receipt as well, so a crash
cannot leave the marker removed or grant standing authority. Repeat or retry
requires a new exact Owner decision and new eligible release identity; no
silent token reuse.

Successful local source tests prove pending-state preservation, source and
freeze digest integrity, scope/rollback mismatch rejection, stale evidence
rejection, protected transaction restore, receipt consumption and stranded
transaction recovery. Those tests are preproduction evidence only. This change
must still be separately admitted and merged via protected PMV3 integration,
validated at an immutable new source SHA, authorized for that exact revision
and scope, deployed and verified. Do not execute a worktree controller script
against the existing production freeze or ticket runtime.
