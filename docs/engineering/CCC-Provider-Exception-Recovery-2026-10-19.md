# Project Jason: CCC provider-exception and rollback-worktree recovery

## Incident and authority

On 2026-10-19, release 98a71bb767d4e8d10800757ed14214c742c6e972
was correctly stopped by post-deployment CCC because two governed read-only
provider canaries, Datto EDR and DNSFilter, returned exceptions. Six other
provider canaries matched their approved positive or negative outcomes.
The release record is failed, with rollback_verified=false, because the
runtime rollback image/alias/health check did not pass within the transaction.
Protected LKG remains e6503eabb53d2f9b5fb9d388a7d43c49c784544a;
fresh read-only host checks observed matching runtime and MCP image IDs,
live revisions and no drift, but the root circuit breaker is OPEN and the
rollback-current aliases are stale. These independent observations do not
rewrite the failed release record or constitute verified rollback.

The same attempted deployment advanced P0 SUPPORT-OPS-054 to a new
evidence recovery branch. Restoring the earlier LKG worker made that newer
branch suffix unrecognizable to its worktree resolver; Jason persisted a
worktree-identity block instead of processing the existing read-only response.

## Fail-closed CCC exception recheck

The CCC checker now records only the bounded exception class for provider
canaries; original provider exception messages are not copied into durable
reports. The existing CCC checker and exact-run metadata remain authoritative.

The Release Manager grants at most two additional fresh complete postflight
CCC runs, at bounded delays, only when:

* The entire independent report has the exact expected source and runtime
  SHA, complete checks, a new run ID, current timestamp and a failing exit.
* The sole failed check is governed-provider-boundary-canaries.
* Its failure evidence consists of one or two actual exception results, each
  for the reviewed Datto EDR or DNSFilter read-only canary with an expected
  successful result. Missing results, failed/denied non-exception results,
  additional failed checks, other canaries, or mismatched expected authority
  never qualify.
* A following complete independent CCC report certifies PASS on every
  mandatory check before release closeout. Every failed check remains
  recorded by run ID, with retry counters in successful release evidence.

Normal preflight, exact owner approval, CCC postflight, release-core owner
review, rollback and immutable last-known-good controls are unchanged.
Permanent failures or malformed evidence always stop deployment. This is
not a substitute for fixing underlying provider health.

## Recovery of the interrupted support repair

The native Support Repair worker may attempt one more readmission only when
the approved P0 item has the exact historical rollback-branch error and its
existing content-addressed read-only request and completed response still
match canonical identity. A verified clean old worktree must have the pinned
original branch and source SHA; failed release state is not overwritten.
The worker obtains fresh authorized tracked source and regression-test excerpts
from protected main in a separate clean branch using the historically
supported -context- suffix, then queues one new bounded edit plan.

It preserves the old branch, response, consumed evidence turns, existing
approvals, governed handoff gates, current worker capacity and immutable
retry-once marker. It does not replay edits, arbitrarily reopen blocked tasks,
patch provider systems, reset counters or deploy production. An unverified
path, stale source, dirty worktree, tampered response or missing test fails
closed. Real completion still requires exact patch tests, protected CI and
production acceptance for the underlying support issue.

## Operator recovery and acceptance

A failed protected circuit breaker is not automatically closed by this PR.
A duly authorized operator must use Jason's existing root-governed baseline
revalidation workflow after verifying exact LKG alignment, root-owned drift,
runtime/MCP health, image and alias readiness. No direct writes to protected
control JSON or unreviewed Docker tags are authorized.

The acceptance sequence is: protected PR checks and exact-SHA release
approval; independent preproduction; root-controlled baseline revalidation;
release with full CCC PASS (including any retries); clean production and
rollback readback; one real SUPPORT-OPS-054 admission and verified patch,
existing-code fix, or actionable explicit terminal blocker. A successful
timer invocation or status change alone does not close the incident.
