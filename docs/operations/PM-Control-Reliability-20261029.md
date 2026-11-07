# Production Manager P0 reconciliation — 2026-10-29

## Authority and boundaries
This is a source-only, non-production engineering handoff for umbrella #1078. It does not authorize protected-main merge, production mutation, controller transition, circuit-breaker reset or privilege changes. Retain the production freeze. The authoritative comparison baseline is protected `main` SHA `73904298b17c4dcbce786e592b136160695b2fd8`, not a claim about the installed production revision.

## Verified observations
- A separate worktree was created at `/home/al/jason-worktrees/pm-control-reliability-20261029`, branch `fix/pm-control-reliability-20261029`, from exact SHA `73904298b17c4dcbce786e592b136160695b2fd8`.
- The primary checkout `/home/al/projects/jason` had unrelated uncommitted `procurement_teams_flow.py` changes and was not modified.
- `python3 -m unittest discover -s tools/tests -p test_release_manager_host_runner.py -q` passed 84 tests on the exact isolated main baseline. This is **not** provider-backed or production acceptance.
- On the connected host, `/opt/jason/current` resolved to release `6501a9f404f99933a49859c6c16e30effe2dfeff` at the time of inspection. This differs from GitHub main; the exact authorized release, complete running surface manifest, and convergence must be independently verified rather than inferred.

## Existing change coordination
- #1112 (open PR) already addresses #1104 and parts of #1101: release-specific scheduled-control validation, watchdog orphan removal, historical rollback regressions. **Do not duplicate or silently transplant its host-mutation logic.** Review it against current protected main and failure-injection tests before considering merge.
- #1103 (open): verify the root-owned protected control-state contract and governed root transition can read/preserve state; never chmod/delete or recreate the circuit breaker to clear a blocker.
- #1102 (open): stage controller N+1; active transaction stays pinned to controller N, with a durable handoff and subsequent N+1 transaction; no live swap mid-transaction.
- #2075 (open): the authenticated Autotask count, paginated search and exact-read canary must be a **mandatory** before/after release gate for all relevant production releases, not solely a conditional canary for changed catalog profiles.
- #2065 (open): the owner production checklist requires actual end-to-end autonomous ticket processing and provider readback before the feature/release can be declared completed.

## Required engineering sequence and exit checks
1. **Live read-only inventory**: capture exact installed controller code digest and revision, runtime/MCP image IDs, source SHA, root/user units and timers, release-specific manifest, circuit-breaker status, last-known-good SHA and evidence freshness. Mark unknown values unknown.
2. **Controller state**: reproduce #1103 in a disposable test with protected, immutable state; verify root worker preserves content and identity and non-root controller uses only governed transitions. Reject unauthorized state replacement.
3. **Versioned controller handoff**: add fault-injection coverage N to N+1 for new required evidence fields, active transaction immutability, checkpointing and second transaction acceptance; resolve #1102.
4. **Rollback manifest**: review #1112 and test N+1 adds watchdog while N has none, then forced postdeploy failure returns to N without orphan units. Test both old and new timer contract checks. Resolve #1101/#1104 only after live readback.
5. **Native functional canary**: require real user-authorized Autotask count/search pagination/exact read before promotion and after cutover, with receipt bound to SHA, scope, expiry and release ID; inject postflight mismatch and verify governed LKG rollback. Reuse the existing canonical read connector, not direct provider access or synthetic HTTP checks.
6. **End-to-end release**: verify full included scope and compatibility with other in-flight work, preproduction, mandatory CI, independent production readback, actual ticket-autonomy smoke, exact rollback identity and clean required system units. Report PASS/FAIL/BLOCKED with evidence, never just 'deployed'.

## Acceptance and hold
All relevant test artifacts and owner approval must bind the precise candidate SHA and rollback SHA. No production deployment, protected-main merge, enabling capabilities, timer/service restart, or circuit-breaker override was conducted in this workstream. Issues remain open until independently verified against production.
