# Jason PR Main Reconciliation Acceptance — 2026-09-29

This file is controlled acceptance evidence for issue #555.

The branch was intentionally created from pre-reconciler main revision
`55136e55324437e07044760746342f4c8666f9d7`, after the reconciler bootstrap
had already advanced protected `main`.

Acceptance succeeds only if the live repository automation:

1. detects that this opted-in same-repository PR is behind current `main`;
2. incorporates current `main` without a force update;
3. reruns the protected validation set and governed security regressions on the
   reconciled head;
4. verifies that the branch remains current while validation completes;
5. merges the PR only after every required check succeeds; and
6. performs no production deployment or runtime/provider authority promotion.

A conflict, failed/missing check, or inability to reconcile must fail closed.

## Operating cadence update — 2026-09-29

After production acceptance, the maintenance polling cadence was intentionally reduced from every five minutes to three scheduled runs per day: 07:00, 12:00, and 19:00 America/New_York. Manual/ad-hoc reconciliation remains available during active development. This changes polling frequency only; PR eligibility, reconciliation, validation, source-merge, and production-release governance are unchanged.

The repository timer file is the durable source of truth for this cadence; the live user-systemd timer must match it after reconciliation.
