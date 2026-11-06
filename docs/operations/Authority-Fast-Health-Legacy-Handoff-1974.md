# P0 #1974 - Fast health handoff during in-flight legacy SQLite scan

**Status:** Source-only repair. No production deployment or privileged policy change authorized by this document.

## Verified production failure

The Owner/CCC-approved release 6740e955d8e48fd98356c9905bb5818c6195cded failed host reconciliation with rc=124 at system_service_activation for jason-openclaw-authority-health.service. The candidate script synchronously waits at most 45 seconds for systemctl start, but an already-running legacy five-minute oneshot performs a multi-minute full SQLite integrity/backup-restore scan. During the incident systemd showed the unit ACTIVATING with an existing Job and ExecMainPID, not a newly completed fast check. A representative legacy child spent multiple minutes waiting on disk I/O.

Native rollback returned the previous host/MCP. Historical release remains FAILED and historical rollback_verified=false. The runtime later became healthy; all ten protected LKG identities matched and the root-owned revalidation returned root_verified_revalidate. Breaker closed and drift PASS. None of this rewrites historical release evidence. Automatic promotion incident hold remains active.

## New bounded handoff

The root-owned immutable host script calls tools/release_authority_fast_health_handoff.py for this specific authority-health oneshot and rechecks fast evidence near service verification closeout.

1. Verify current immutable source SHA, byte-identical root-controlled canonical installed service file, no systemd DropInPaths, loaded ExecStart exactly points to the new fast-health program, and the frequent health timer is active.
2. When the new service is genuinely idle with no Job, run the REAL systemd oneshot with a finite 40-second bound; require fresh fast-health evidence.
3. When and ONLY when a still-activating job has the expected Job, ExecMainPID, owner al, and exact legacy health-snapshot Python argv, leave that old scan untouched and run the reviewed candidate fast-health script as unprivileged al with a 35-second subprocess bound. No stop, kill, forced restart, masking, timer disabling or bypass.
4. Require a newly written mode-0600 al-owned nonsymlink fast-health output, PASS, exact frequent-read-only mode, source exit zero, provider/contact false, no failure codes, and an independently proven prior full SQLite integrity/restore PASS no more than 30 hours old.
5. Recheck exact fast evidence before host service success. If old full-scan completion overwrites the fast result, the proof is stale/failed, systemd state unknown, or any command times out, fail closed. The native Release Manager remains responsible for independent CCC, protected LKG, all host/runtime/MCP checks, rollback and breaker.

The separate daily full-integrity/restore timer remains mandatory. A direct read-only fast probe does not claim the legacy systemd job has finished.

## Evidence and production boundary

In isolated worktree tests, the legitimate in-flight legacy PID/UID/argv/Job and loaded canonical systemd unit are distinguished from unrelated jobs and overrides. Fast proof, time freshness, source return code, missing/stale independent full proof, tampered evidence, and legacy overwrite all fail closed. Existing fast-health tests exercise real temporary SQLite read-only queries.

Against the live original production baseline, read-only execution of the new candidate check while the legacy oneshot remained ACTIVATING returned status=pass, check_mode=frequent_read_only_plus_recent_full_integrity, full_proof_status=pass, zero failures, no provider contact, and actual full proof about 4.9 hours old. No production service or policy was changed.

Passing unit tests and this read-only live check do not prove a completed promotion. Still require exact-head protected GitHub CI, a fresh exact-SHA native preproduction release, authenticated Owner approval and corresponding CCC material review, and the native governed release process. Earlier failed-release approvals cannot be reused; incident hold remains intact.

AOT confirmed no local human peer reviewer is available. Documenting an AI-assisted audit and independently running protected CI does not constitute or impersonate independent human review.
