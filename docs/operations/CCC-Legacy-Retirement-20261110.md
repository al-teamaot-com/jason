# Retirement of legacy Constitutional and Compliance Check (CCC) service

**Decision:** Owner-directed on 2026-11-10. CCC is being retired as a standing
separate production and approval dependency. Its historical evidence is retained.
This is not a permission to remove the independently enforced Owner, security,
rollback, tenant-isolation, drift or production-health controls.

**Status:** Source/preproduction prepared. Not deployed. Current live production
remains V2, frozen, with a protected open breaker.

## Exact bounded retirement

The CCC scheduler has two root-owned systemd units:
`jason-ccc.timer` and `jason-ccc.service`. They were installed from
`infrastructure/ccc/systemd/` and are *allowed* but not required in the
protected desired-state policy. The failed oneshot alone triggers
`failed_system_unit` drift, preventing recovery.

The next governed release removes those two units from the candidate
`allowed_system_units`, and extends the existing release-owned unit-delta
planner to recognize their **exact immutable bytes**. The root host reconciler
already:

1. requires a protected source SHA, live MCP/source alignment and a locked
   deployment transaction;
2. checks that only candidate-declared units absent from target source are
   selected and that each installed unit byte-matches the immutable previous
   release;
3. stops/disables timer before service, archives the exact installed files in
   its timestamped, root-owned rollback directory, removes only these
   validated unit files, and reloads systemd;
4. verifies the live candidate's independent desired-state drift check.

Unknown unit changes, symlinks, wrong ownership, missing prior release and
drift mismatch fail closed. If the candidate is rolled back, archived unit
definitions and preexisting production evidence are retained for review. The
retirement does not stop, restart or modify Jason runtime/MCP or tickets by
itself; the independently authorized release transaction governs those changes.

## Release authority and health after CCC retirement

For source policy `3.1`, replace the old
`independent_ccc_required` flag with
`independent_native_release_health_required`, preserving all of:

- exact authenticated, short-lived, one-use Owner approval bound to SHA,
  scope, manifest, rollback and freeze;
- preproduction functional and rollback-readiness checks;
- protected production source and root drift state;
- authority full SQLite integrity and backup/restore proof;
- independent runtime/MCP health and postdeploy functional smoke;
- protected release control, audit receipts, ticket-worker continuity;
- automatic rollback and freeze restoration on failed acceptance.

Legacy CCC report parsing, existing source revisions, historical evidence and
recovery records remain readable until no production rollback record needs
them. There must be no new CCC-only human card, failed CCC scheduler job or
routine CCC technical certification requirement for the new release.

## Operational prerequisites and boundaries

Before any live removal: a governed exact candidate SHA must be accepted; all
CI/regressions must pass; reviewed root policy and the new exact Owner
approval mechanism must be present and independently verified; the open
breaker requires a reviewable `retire_obsolete_ccc_scheduler` recovery
profile and matching health evidence; and the protected last-known-good
baseline must be correctly reconciled. An already-failed historical CCC
unit cannot simply be relabeled as healthy.

Do not delete archive `/var/lib/jason/ccc` or
`/home/al/Jason-Evidence/CCC` as part of this retirement. Do not disable
any independent integrity, audit or drift checks. Do not remove the installed
units via ad hoc shell commands outside the governed transaction.


## November 11 emergency host-migration follow-up (source-only)

The November 11 attempted rollout of candidate
`7000e725361d8bd0c5627cc839278eeff11ca9be` failed at the independent
root-owned host policy migration because the historical root helper still
demanded `/var/lib/jason/ccc/material-review.json`. The candidate already
retired that duplicate Owner review and removed only the exact obsolete
`jason-ccc.service` and `jason-ccc.timer` allowed declarations. This
mismatch, not missing Owner authorization, was the host-stage failure.

The replacement source permits exactly the two-unit CCC allowance removal,
keeps old protected policy bytes during staging, records a root-owned
hash-bound undo receipt, removes only the exact pair at final commit, and
restores the original bytes on rollback. A different/partial removal or
other desired-state change fails closed. For source-pinned V3.1 approval
policy, the root helper independently rechecks the native release Owner
binding to candidate, rollback, reviewed scope and manifest digest, with
no CCC-only attestation. Historical predecessor releases still use their
original CCC checks.

This engineering change is **not deployed or independently accepted** until
the native, frozen production transaction succeeds. The emergency attempt
also exposed a separate full-SQLite-integrity health bottleneck: the
full proof takes up to an hour and the root host reconciler synchronously
waits for it when the prior proof evidence is failed. Do not silently
replace the full integrity check with a quick scan or call it PASS.
Preserve the production freeze, rollback and drift controls until the
health and exact Owner-release gates are satisfied.

## Verified 24-hour full SQLite proof reuse

A full authority and audit SQLite integrity plus backup/restore proof is reusable
for 24 hours if the complete result passed, is ownership/mode-validated, and
contains the required evidence. The writer separately retains the most recent
successful full proof, so a later timeout does not erase that proof. A confirmed
later integrity failure is never ignored. If no valid recent success exists,
the existing full proof is required and a timeout remains a failure; no
unverified result is marked PASS. Owner-approved emergency recovery policy
would require a separate, explicit reviewed release change.

### Concurrent-change integration note

PR #2424 overlaps the full-proof snapshot writer and its tests with PRs
#2404, #2395 and #2390, which adjust timeout and temporary backup cleanup.
Combine scoped temporary cleanup with last-success proof retention when those
branches are subsequently integrated; neither supersedes the other. PR #2391
changes a separate later provider-shadow stage in host reconciliation and must
preserve the 24-hour full-proof reuse contract.

### Owner emergency: do not block release on SQL full scan

The full SQLite integrity scan is no longer a synchronous release gate. Its
existing failure evidence is retained, and the daily scanner remains separate.
The optional full-scan systemd failure is an advisory to the production drift
watchdog, not a reason to stop all releases. This does **not** waive native
Owner identity, exact scope authorization, rollback, or checks of runtime/MCP
health and required production units.

Reviewed overlapping development: PR #2404 changes production drift handling
for a masked release timer and does not intersect this optional full-scan
advisory branch. PR #2391 stages disabled provider-shadow units in a later
host reconcile stage; this does not supersede the full-proof skip. Both must
preserve these emergency changes when eventually integrated.

Integration coordination: #2424 #2404 #2391

## November 11 root receipt recovery and release reissue boundary

The exact Teams-free candidate `b16e1cbdf47c63058f3d5e95bb139fc826e3fa3b`
failed during root host reconciliation because an earlier interrupted
`35936e859a4eed7ccd700e03f401189726042a80` CCC-retirement transaction
left an audited root receipt in `rollback_prepared` while the installed V2
root helper did not recognize that removal-only plan. The native attempt
restored Runtime/MCP and its original production freeze but could not verify
host rollback. A failed release must not be recast as production-complete.

The Owner performed a **separate locally authenticated root-maintenance
action**, verifying the candidate-bound recorded receipt and full predecessor
chain, restoring the original protected policy bytes, archiving the old
receipt, and atomically installing the independently Git-verified CCC-aware
root helper. The helper bytes have SHA256
`d30e0bdcabb9d7e1aa9691465c1d52402a75253ffff737d4998d3b25df855828`.
The original freeze SHA256 remains
`bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`.
Native readback then confirmed V2 Runtime, MCP and host alignment, clean
production drift and a **closed** circuit breaker. No database deletion,
service restart, or additional provider grant was part of this repair.

Root migration regression coverage now reproduces the exact interrupted
`rollback_prepared` phase, verifies byte-exact archival and restoration, and
proves that a different reviewed source SHA can stage the same closed-world
CCC-removal delta without overwriting an existing audit receipt. A forged
or changed unit delta still fails before protected policy modification.

This is evidence of **recovered production baseline only**, not deployment of
the Teams-free candidate. A future exact release requires fresh preproduction,
updated scope review, newly authenticated Owner authorization and final
production acceptance. Never reuse an approval consumed by a failed release,
and never treat a missing full SQLite proof as successful.
