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
