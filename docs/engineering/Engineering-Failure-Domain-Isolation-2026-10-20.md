# Project Jason: Engineering failure-domain isolation and preproduction containment

## Incident and original failure cascade

On 2026-10-20 the GitHub SUPPORT issue listing transiently repeated numeric issue #1344. The support discovery worker correctly rejected inconsistent issue identity, but the entire scheduled engineering coordinator returned exit code 1. The resulting failed `jason-support-repair-worker.service` was classified as `failed_user_unit` by the independent desired-state watchdog. The watchdog opened the protected release circuit breaker, which did not automatically close on subsequently clean drift; the native root revalidation attempts were rejected and the bounded attempt budget was exhausted.

A separate 2026-10-20 preproduction rehearsal briefly exposed `jason-runtime-preprod-<revision>` as an undeclared running container to the same watchdog. That was an authentic observation of an ephemeral test container, not proof that the production runtime had been replaced.

These issues form one *failure-domain isolation* problem. Work-item data errors and authorized transient preproduction assets should not masquerade as unauthorized production changes. In contrast, failed release-control execution, genuine unknown containers, unauthorized paths, source mismatches and root authority violations must continue to stop promotion.

## 1. Isolate known work-item failures without hiding degraded operation

The engineering coordinator executes support repair, TODO admission and previously approved development as a work-item lane. Their **completed** stages may produce nonzero exits for a rejected GitHub response, exhausted model evidence, or a work-specific error. When all required stage results are durably recorded, the pipeline returns systemd success for those completed work-stage failures only.

The coordinator still records `status=degraded`, each exact failed or dependency-skipped stage, and the classified `failed_work_stages`, `failed_control_stages` and `failure_domain` in its 0600 state. Existing engineering-supervisor observations, priority rules, durable work-item blockers, and lifecycle escalation remain active. There is no claim that failed work succeeded or that approved commitments advanced.

The following conditions still return a failed systemd status: stage process launch errors, timeouts, signaled child termination, missing/inconsistent completion records, failed release bridge, failed independent supervisor, and failed root-breaker recovery manager. A fatal inability to persist the coordinator state is unchanged. Failed work never bypasses admission, CI, ticket/provider rights, release gates or approver policy.

## 2. Serialize preproduction against the real production watchdog

Only the installed Release Manager's `run_preproduction` acquires the existing serialized production-transaction lock while an ephemeral isolated candidate container exists. It holds the lock through the container's successful or failed acceptance, preflight and cleanup. The independent watchdog already checks this lock and records a bounded `deferred / production_transaction_active` result without changing production drift or circuit-breaker state. Upon release, the watchdog resumes its standard full evaluation.

The lock is acquired only **after** the candidate image and MCP digest match their immutable expected artifacts. The lock is always released, including health check failures and container cleanup errors. This does not add a container name allowlist, weaken root-owned desired-state policy, or trust model-generated file paths. The lock also prevents an overlapping production promotion.

Genuine undeclared containers seen without a verified active release transaction, failed essential services, forbidden developer paths, root-managed mismatch and any unauthorized production mutation continue to trigger drift and the protected breaker.

## Acceptance before production

1. Protected GitHub CI passes for exact candidate code, regression tests for engineering stage-domain isolation and release serialization, and full review of overlapping PRs.
2. Isolated negative tests confirm that a failed GitHub discovery step degrades the work-item pipeline without marking the systemd worker failed, while failure of the supervisor, release bridge, recovery process, script launch or execution timeout still returns nonzero.
3. Preproduction tests confirm the lock is held before `docker start`, until after `docker rm -f`, and released after both successful acceptance and failure. Independent watchdog deferral remains tested without allowing any unknown container when unlocked.
4. Separate governed candidate preparation, CCC approval, exact-SHA owner authorization, preserved rollback and protected post-deployment verification succeed. The current open release breaker and historical rejected recovery attempts **are not cleared by this source change**.
5. After authorized deployment, observe multiple successful worker cycles with truthful degraded state for injected work-data failures, no spurious `failed_user_unit` breaker opening, successful preproduction with no undecided ephemeral-container drift, and independent CCC drift checks for genuine violations.

## Out-of-scope

This is **not** a root-breaker reset, attempt-ledger rewrite, material-review authorization, owner approval, provider API write, operational backlog closure, or production deployment. The independently root-owned transition process and the unresolved historical root rejection require a separate operator-reviewed recovery and exact-revision acceptance.

Related evidence and work: PR #1617 (support identity), #1619 (canonical IDs), #1620 (one-shot source search), #1621 (independent GitHub issue snapshots), #1622 (safe root-denial classification), SUPPORT-OPS-059 through 061, and active release-governance issues.
