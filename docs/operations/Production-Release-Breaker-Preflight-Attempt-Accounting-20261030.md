# Production Manager — Drift breaker preflight and recovery attempt accounting
**Date:** 2026-10-30
**Scope:** Read-only production diagnosis plus development-only recovery diagnostics. No root state mutation.
**Source branch:** feature/release-breaker-preflight-accounting-20261030

## Section Goal
Ensure Production Manager can distinguish a failing *unprivileged production health preflight* from an actual authorized root-governed revalidation request. Consume the root retry permit only after a fresh, exact-LKG read-only health preflight succeeds. Preserve all existing authority, retry limits, protected file ownership, source isolation and root post-verification.

## Trigger and observed incident
- 14:30:13 EDT: jason-grafana-assurance.service reported GRAFANA_ASSURANCE_STATUS=DRIFTED, failed with exit-code. The drift watchdog also failed its service at 14:30–14:34.
- 14:34:28 EDT: Protected release breaker opened for continuous_production_drift_detected (failed_system_unit).
- 14:35:14 EDT onward: Grafana assurance checks returned PASS. Subsequent root drift readback reports PASS, systemd is running and there are no failed systemd units.
- 14:46:21.178546 UTC and 14:56:14.933483 UTC: The automatic recovery ledger recorded two root_revalidation_rejected attempts, both type ReleaseManagerError, failure class unclassified_root_revalidation_failure. The first persisted failure message appeared at 14:46:21.308580 UTC, only ~130 ms after the attempt timestamp and before the root transition service's next scheduled 14:46:24.949274 UTC run. This strongly suggests a local preflight error, but the exact historical error message was not preserved; do not claim the root worker rejected the request.
- As of the investigation, protected LKG cb76e14f9f42ec4f914b10967db1d408c271c1aa matches the current read-only production manifest in **all 10** root fingerprint fields. Protected breaker remains **open** with automatic recovery action operator_review_recovery_attempt_budget_exhausted (two recorded attempts). Healthy state does not automatically grant release authority.

## Root-cause assessment
The unprivileged recovery manager previously persisted an attempt as awaiting_root_worker *before* calling native_root_transition(). That function itself runs local revalidate_circuit_breaker() prechecks before it can enqueue a root request. A failed local precheck could therefore consume one of the two strictly limited root permits and be mislabeled root_revalidation_rejected. The exact 2026-10-30 preflight exception cannot be recovered from the bounded ledger. Retrospectively reclassifying or deleting those attempts would be unauthorized.

## Narrow code correction (development only)
- native_revalidation_preflight(): Read-only, 90-second-fresh, trusted protected snapshot; exact LKG SHA; installed Release Manager's read-only capture_production_manifest(); all 10 immutable fingerprint equality checks. No direct provider calls or protected file writes.
- Failure returns a fixed, non-secret class (e.g. production_manifest_precheck_failed or protected_lkg_mismatch_runtime_revision) in an unprivileged, mode-0600 ledger entry. Raw exception text/paths/secrets are not persisted.
- A local preflight failure **does not append a root attempt**. It reports reconcile_read_only_preflight; no root request is sent. If the preflight succeeds, the original guarded sequence still persists authorization consumption BEFORE invoking the native root revalidation path.
- Past attempts are preserved, never refunded or reset; outstanding attempt budget remains exhausted. A changing or missing owner grant never converts to permission. The root worker still independently checks source, protected policy, fresh drift and LKG fingerprints.

## Acceptance and guardrails
- 40 bounded unit tests passed on an isolated development checkout, including independent ten-field comparison, expired protected snapshot, secret-safe failure handling, true governed attempt persistence, root rejection, result readback and exhausted legacy ledger.
- No changes to protected production state, retry limits, timers, containers, root requests, or production source.
- A fresh, separate protected CI run must pass on the *exact* eventual merged revision. CI alone does not close a protected circuit breaker.

## Genuine remaining external gate
The historical breaker has two exhausted attempts and cannot be automatically rearmed by this code. Root-authorized operator must review the immutable root response/audit and historic Grafana drift, verify current health and ten-field LKG alignment, and authorize a bounded root-governed revalidation/rearm under the established recovery policy. Do not run root-only recovery as an ungoverned shell shortcut, clear or overwrite the ledger, or close the breaker based solely on the user-visible PASS drift snapshot. No new production feature can be promoted until this gate is resolved.

## Section Goal closure
Code-level mitigation: preproduction tests passed; protected CI and production release still gated.
Current breaker: **not recovered**.
VulScan V2 PR #2178: remains draft with its own live Datto read acceptance and owner Teams delivery gates. Avoid conflating this infrastructure diagnostic change with its feature scope.


## Owner-approved manual recovery — verified result, 2026-10-30 20:48:55 UTC
- Explicit conversational Owner authorization applied to exactly ONE manual native Release Manager revalidation of protected LKG `cb76e14f9f42ec4f914b10967db1d408c271c1aa`. The normal automatic recovery budget was already exhausted and was **not reset**.
- Preflight passed: all 10 immutable LKG fields, fresh clean drift, systemd running/no failed units, no production transaction lock, no pending protected transitions, active root transition timer.
- The installed canonical `release_manager_host_runner.revalidate_circuit_breaker` submitted one request to the already installed independent root-owned transition worker. Process exited 0 after a verified root transition; no fallback CLI, direct protected write, sudo bypass or second attempt.
- Protected readback: `circuit_breaker.state=closed`, `reason=root_verified_revalidate`, `revalidated_revision=cb76e14f9f42ec4f914b10967db1d408c271c1aa`, `updated_at=2026-10-30T20:48:55.711952+00:00`. Current drift PASS/zero problems; no failed systemd units. GitHub issue #1078 records exact authorization and verification evidence.
- **Additional audit bug confirmed:** after the recovery completed, the still-installed scheduled recovery manager rewrote its closed-state ledger to `already_closed` and dropped `attempts` (now 0), retaining only `last_revalidation_attempt=root_revalidation_rejected`. The historical two-attempt provenance was recorded in issue #1078 *before* the scheduled compaction. The PR adds a closed-state path that retains all original attempts, validates shape and fails closed if corrupted; this is a future safeguard and was not deployed as part of the manual recovery. The current installed ledger is not manually restored or altered.
- Development-only tests: 63 isolated recovery/root/drift regressions passed at `8dc387ce1f7ee0bbd9107c275f639fbbbe7db8a5`. Protected CI must still be fully green at the eventual final head.
- **Production root-breaker incident recovered.** This does NOT lift the independently ordered global production freeze, authorize any feature release, prove VulScan V2 live Datto site/policy reads, or signify PR #2181 deployment. Exact-SHA approval is still required for later feature promotion.
