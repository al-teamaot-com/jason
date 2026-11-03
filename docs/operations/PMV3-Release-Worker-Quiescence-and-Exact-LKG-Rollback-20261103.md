# PMV3: release/worker quiescence and exact-LKG rollback recovery

**Status:** source-only engineering candidate. Not deployed and not an Owner production authorization. Incident: [#1974](https://github.com/al-teamaot-com/jason/issues/1974).

## Observed operational failure

On November 3, 2026, signed production candidate `3e06627de85ace598f959cda12e257000668864d` advanced runtime/MCP but failed in root-owned `user_worker_reconciliation`. The operator had paused the five-minute engineering timer through a temporary override and stopped the worker, but the native self-heal watchdog independently issued `systemctl --user start --no-block jason-support-repair-worker.service`. The host script's 180-second wait timed out. Rollback restored runtime and MCP to root LKG `1b28ddc9863aee563755cb57599cf211ee82ac19` but the root host helper denied LKG health recovery: its special path required an already-OPEN breaker, whereas the Release Manager only opens the breaker *after* attempting the rollback. The host remained unverified on candidate source and the final breaker opened. The original Owner freeze and engineering timer were restored.

## Correction / responsibility boundaries

- `pmv3_worker_release_gate.py` is a read-only systemd `ExecCondition` which **skips** (does not fail) a worker start whenever the exclusive `production-transaction.lock` is held, missing, or untrusted. The service installer and production host reconciler verify the installed source matches the exact SHA.
- Native Release Manager creates a runtime-only `ExecCondition` drop-in **under its existing exclusive production lock**, before it evaluates engineering quiescence or makes the first production mutation. The temporary gate protects the *previously installed* worker from timer and direct `systemctl start` calls during the whole release, failure rollback and Owner-freeze restoration. It is removed with `daemon-reload` in unconditional cleanup; no permanent timer policy changes. Deployment still stops if the existing worker has not actually exited.
- The native self-heal watchdog holds a nonblocking shared production lock around its worker-start calls and bounded local Docker recovery. When the exclusive release lock is active, self-heal persists the incident, defers intervention, and retries through existing cadence. No provider bypass or suppressed detector.
- Root host reconciler retains its exact pinned 1b28 LKG integrity/health recovery. It accepts the rollback **before breaker opening** only when a real production transaction lock is held, root-protected LKG matches the exact requested SHA, the candidate is protected `origin/main`, release state is `production`, and the release's signed Owner approval, source-bound one-transaction freeze exception, immutable manifest, CCC material review, authenticated Teams approval receipt, successful pre-mutation baseline, and actual temporary freeze backup all agree. This does **not** admit ordinary/unauthorized host changes or substitute a different SHA.

## Source integration reconciliation evidence

- Isolated merge proof: repair PR #2293 head `8f0618e808019ad78fe8f5fb7420fb185ec5f1fc` plus PMV3 queue PR #2280 head `39061f70c522dd2c3dc4d2164c90a9f4fcc791f7` merged without Git conflicts in an **unpublished dry-run worktree**; merged-tree local host tests: **354 passed + five subtests**. No protected `main` merge, no status fabrication, no live runtime or host change.
- Additional active same-file branches **#2279** (superseded signed Teams approval queue) and **#2156** (manual release pinning after unrelated commits) were reviewed for ownership of distinct Release Manager functions. Preserve both decisions during subsequent source integration; neither transfers an old signature to new SHA nor bypasses protected-current-main checks.
- Protected CI's `Validate Production Manager V2`, `SEC-007 Security Regressions`, `Validate OpenClaw Operations`, `P0 Owner Autotask Production Read Acceptance`, and other checks passed on repair head `8f0618e80...`. `Validate Jason` implementation overlap requires the exact review of #2279/#2156 recorded on PR #2293, then a new full protected CI run. Documentation source and tests are not proof of production fitness.

## Required verification before any production deployment

1. Protected PR CI, unit/regression and source risk-classification checks pass. Confirm no unrelated worktree changes and reviewer approval of the root/Release Manager/installer changes.
2. Validate a representative **isolated user-systemd** release race: active worker -> normal quiescence rejection; idle worker -> temporary gate installed; timer and direct self-heal start attempts during transaction -> `inactive`/skipped without service failure; release completion/failure -> temporary drop-in deleted and original timer unchanged. Unit tests alone do not prove the live systemd race.
3. Validate the exact-LKG *partial-host failure* in a nonproduction, privileged integration environment. Verify MCP rollback occurs before root host restore and the root helper can prove signed release/rollback, read-only CCC/Teams receipt and active transaction; verify unrelated SHA, missing receipt, expired/absent authority, forged manifest, missing lock, or mismatched freeze backup fails closed.
4. Check the repair candidate's complete release inventory and health. A separate authenticated **exact-SHA production approval** is required by the governance handbook. The failed 3e066 release approval cannot authorize this new SHA.
5. Deployment and rollback require native PMV3 with immutable evidence, rollback-readiness and LKG checks, exact Owner freeze scope and automatic freeze restoration. No direct Docker/root-policy bypass. Verify the final production host/runtime/MCP/Release Manager/CCC and all foundational provider canaries before completion.
6. Only after production is healthy, proceed through the protected PMV3 queue PR #2280 and KFS AOT-wide PR #2282, then demonstrate LaToshia's actual customer-grouped copier reports, latest meter timestamps and missing/stale-device exceptions without estimates.

## No false completion

A PASS in source-only unit tests is **not** live operational acceptance. The host/source divergence and open breaker from the last failed release require a separately governed recovery with exact root/protected evidence before another promotion. Report entire Jason/KFS objective progress rather than an intermediate step completion percentage.
