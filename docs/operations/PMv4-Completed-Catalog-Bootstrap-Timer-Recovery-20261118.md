# PMv4 host recovery - completed catalog bootstrap timer

**November 18, 2026. Status: SOURCE ONLY. No production mutation or Owner approval.**

## Why this narrow recovery is required

The completed catalog root bootstrap installed its verified root bundle on
November 17. Its bootstrap-recovery timer remains enabled every 35 seconds.
The root code's completed-install branch unnecessarily asserts the exact
original runtime/MCP Docker container IDs and start times on every subsequent
invocation. An authorized subsequent runtime replacement changed one ID. The
timer now exits 1 with the error
CATALOG_NATIVE_BOOTSTRAP_UNRELATED_LIVE_PRODUCTION_CONTAINER_CHANGED.
The native drift watchdog correctly opens its breaker for
failed_system_unit=jason-catalog-root-bootstrap-recovery.service.

This is not a Ticket Core fault. Ticket Core remains supervised in embedded
mode, and provider-backed ticket scans continue.

## Exact Owner-authorized host-only corrective action

Source: tools/pmv4_bootstrap_timer_recovery_{builder,root}.py.
The protected-main builder writes a one-use, SHA-pinned packet.
The root-staged executor independently verifies:

- Current protected main, GitHub required CI, pinned root script and exact
  scope SHA, original installed root trust and accepted root-install audit
  including verified Owner identity and consumed approval evidence
- Original root policy and bootstrap code hash, approved freeze, deployed
  protected LKG source and protected Docker container identities/starts
- Exactly the completed bootstrap-recovery failed service, no unrelated drift
  problems, production breaker opened for failed system units
- The old bootstrap timer is active/enabled and the separate
  jason-catalog-scoped-recovery.timer is healthy and enabled
- Both original PMv3 production and PMv4 host mutation lock files

After interactive local sudo, fresh authenticated Entra Owner device login,
explicit exact-action confirmation and root audit before mutation, the
sole scoped mutations are:

1. Disable and stop only jason-catalog-root-bootstrap-recovery.timer
2. Reset failed status of the completed bootstrap service and native watchdog
3. Start the existing native drift watchdog once, require PASS with 0 problems
4. On failed postflight, re-enable only the original timer and preserve audit

No root policy, source file, provider credential, Docker container, Ticket
Core ledger, MCP process, production freeze, or root breaker state is modified.
The already installed catalog-scoped recovery timer stays enabled.
The native release-breaker recovery manager alone may close the breaker
after independent clean observations.

The original root-rebind transaction's preflight expects the old timer active.
After this narrow retirement, future catalog root rebind must recognize the
accepted supersession receipt, not reactivate the obsolete timer. This PMv4
repair does not authorize catalog image promotion or Autotask writes.

## Acceptance and boundaries

Security CI tests exact systemd scope, rejected unrelated drift/approval,
check-only nonmutation, required one-use Entra consent, unchanged protected
services, watchdog PASS and synthetic failure rollback. A fresh protected-main
SHA and baseline must match; stale packets are rejected.

Production completion requires root preflight, Owner intent receipt, single
timer transition, native drift PASS, native breaker revalidation, two fresh
Ticket Core scans and unchanged protected runtime/MCP. Stage C cutover,
Stage D runbook deployment and Stage E retirement remain independent gates.
