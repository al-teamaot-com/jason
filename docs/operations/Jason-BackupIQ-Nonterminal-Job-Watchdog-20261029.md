# BackupIQ autonomous reinstall: bounded nonterminal job observation

## Live evidence: October 29, 2026

On AOT's Jason worker, ticket T20261029.0016 (Atomic Plumbing,
APD-50399) was in the durable phase backupiq_reinstall_wait after a single
standing-safe Endpoint Backup reinstall. The exact Datto RMM job
86e9e790-2eab-46a9-a269-b199197b6729 was still returned as active
roughly 2.5 hours after dispatch. The worker returned immediately for
active/running/queued/pending/scheduled status with no time budget, so the
case could remain in that phase without technician attention or a
bounded end condition.

## Corrective state transition

During every active job poll, use the original persisted, trusted
backupiq_reinstall_started_at timestamp. An existing provider-reported
nonterminal job younger than two hours remains in normal wait and is not
redispatched. At two hours of continued nonterminal state, record a
sanitized internal technician note with the existing exact job ID,
component, endpoint, observed provider state and elapsed time, then
make the **existing verified** Help Desk I / Human Review handoff.

Do not report provider failure, do not cancel or rerun the job, do not
reboot or restart a device, do not close the ticket, and do not clear the
original job UID or component UID. The handoff remains subject to
Autotask readback verification of queue and status. If the original
dispatch timestamp is missing, require human review rather than guess
how long the provider has been working.

A successful-terminal job continues the existing independent provider
backup verification workflow; this change is only a bound on endless
nonterminal polling, not a new approval or resolution rule.

## Acceptance

- Stale nonterminal provider job at ~150 minutes records a technician
  evidence note, verified Help Desk I / Human Review, and preserves
  the original job identity and one-reinstall attempt count.
- A recent 30-minute running job remains in its original waiting phase
  without new Autotask or Datto changes.
- Missing baseline timestamp is handed off without fabricating job age.
- Existing successful reinstall, provider backup verification, waiting
  device, and no-duplicate-dispatch tests must remain green.
- Production release requires the exact current protected-main SHA,
  verified release scope and rollback and Owner approval before deployment.
  Live acceptance additionally confirms no indefinite waiting slot after
  the restored worker processes T20261029.0016 or an equivalent case.
