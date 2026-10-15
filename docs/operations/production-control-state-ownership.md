# Production control-state ownership — historical guidance (superseded)

**Status:** Superseded/historical. **Reviewed:** 2026-10-10.  
**Canonical decision:** [PR #1162](https://github.com/al-teamaot-com/jason/pull/1162), merged 2026-10-09.  
**Related incidents:** [SUPPORT-OPS-052 / #1095](https://github.com/al-teamaot-com/jason/issues/1095); rejected reversal [PR #1206](https://github.com/al-teamaot-com/jason/pull/1206).

## Current accepted boundary

The production drift watchdog **runs as root**. Protected release-control and drift-state files are preserved as **root-owned, mode `0600`** across atomic writes. The unprivileged Release Manager uses the authorized root-protected readback/transition mechanism and must not be given direct ownership/write access merely to bypass a blocked release. Do not weaken the circuit breaker or change the watchdog's execution principal. Verify current live bridge availability and protected evidence before drawing conclusions about a specific deployment failure.

## Retained historical statement (not current instructions)

The earlier proposal in this document called for replacing `production-control-state.json` using the release-manager state-directory owner and for a one-time ownership repair of root-owned files. This approach was superseded by PR #1162; it is **not** an authorized remediation instruction. PR #1206 attempted to reintroduce that approach on 2026-10-10 and was closed without merge.

The reason for retaining this record is to prevent future operators and automated repair agents from rediscovering or reapplying the rejected approach. Consult the controlling decision and current protected readback evidence before proposing any further change.
