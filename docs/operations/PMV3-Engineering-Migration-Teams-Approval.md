# PMV3 Independent Engineering Migration — Signed Teams Approval

**Classification:** HIGH RISK. **Status:** SOURCE-ONLY, NOT ACTIVATED, NOT APPROVED.
Tracking: Issue #2300, source draft PR #2391. This is not a production change authorization.

## Objective

Move Project Jason engineering work from the currently paused monolithic PMV3 worker to the independent support, TODO intake, development and supervisor lanes without overlapping providers, losing ticket intake, violating the release lock, or weakening signed approval requirements.

## Existing signed Teams flow (reuse, not replace)

The migration request capability `engineering.migration.activate` is currently **BUILDING** and *not registered in production*. An exact-scope source-only adapter delegates to Jason's canonical `UniversalPlanIssuer` for authenticated Teams requesters or separately registered workload identities. This issuer already checks live identity/authority, original signed Teams gateway challenge, recipient bindings, retention and replay policy. No new approval ledger or simulated decision is permitted.

Required immutable request arguments: `candidate_sha`, `rollback_sha`, `reviewed_scope_sha256`, `continuity_evidence_sha256`, and the exact phase `independent_engineering_lanes`. The source adapter requires AOT organization only, no client, deterministic execute mode, one exact 900-second approval window, and neither `authority_allowed` nor `approval_present` asserted by callers.

An issued Teams card is **not** an approved release; only the provider-authenticated original signed callback bound to the exact issued card and the native PMV3 Release Manager's independent admission can authorize the final transaction.

## Verified live blockers on November 9, 2026

1. The Owner pause receipt remains present at `/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json`. The old monolithic service was inactive with `ConditionResult=no`.
2. Independent engineering service units and `/home/al/.local/lib/jason/independent_governed_lane.py` were **not installed**. Source templates and unit tests are not installed runtime.
3. The existing `jason-release-approval-only.timer` is running, but its release service reports `RELEASE_APPROVAL_ONLY=SAFETY_GATE_BLOCKED`; it cannot issue an unreviewed engineering migration request.
4. The regular AOT Teams identity is `al@teamaot.com` (Entra object `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`). The privileged admin is separate: `al_admin@teamaot.com` (object `c848022d-e13b-4457-84b0-e2f5c00dcaf6`). **Do not substitute** either for the other. A Microsoft Teams connector call from the current authenticated account returned a 403 licensing failure; account licensing/receipt must be independently verified before relying on a privileged Teams card.
5. Production control/drift records are protected from the ordinary host user, correctly preventing unattended baseline assertions.
6. Live signed Teams migration approval and exact production-eligible release candidate **do not exist** as of this checkpoint.

## Exact safe progression

1. Reconcile source PR and overlapping protected-main work without bypassing code review or branch policy. Run new migration-approval CI and native PMV3 regressions.
2. Native Release Manager independently establishes protected-main baseline, exact candidate/rollback SHAs, complete scope digest, production drift/circuit-breaker health, preproduction and rollback acceptance.
3. Install and register the approval capability through an **authorized** release stage before attempting to request it. Existing universal plan issuance must be independently configured with approved requester workload/human identity and eligible, licensed privileged approver; never impersonate an admin.
4. Issue one exact reviewed migration card through the **existing signed Teams gateway**, verify a non-synthetic provider delivery receipt, and require the intended authorized human to sign Approve/Deny in Teams. Preserve original signed decision evidence. No chat reply or ordinary notification grants permission.
5. After native Release Manager independently validates the signed decision and exact immutable release, install disabled independent services and all required companion source atomically. Preserve production freeze and old pause guard; confirm all services initially inactive.
6. Before any independent worker is activated, obtain governed and fresh real-ticket continuity evidence (controlled XYZ test, notes/queue/device association, worker claim idempotency, BackupIQ, VulScan, EDR and notification routing as in exact scope). Do not fabricate test receipts.
7. Activate only the authorized bounded migration phase through the native release transaction. Verify two independent post-cutover cycles, no ticket loss/duplicate claims, unchanged provider rights, and expected service scheduling.
8. If any acceptance fails, perform the authorized exact rollback and verify the original freeze/hold and worker state. Retain automation promotion hold.

**Mandatory stop:** Missing production candidate, privileged signed Teams approver, ticket-continuity evidence or Release Manager approval prevents a live migration. Removing the pause file, manually enabling systemd units, treating a delivery log as signed approval, or changing admin licensing without authorization is prohibited.

## Source-only tests

`PYTHONPATH=implementation:implementation/runtime_service/src python3 -m pytest -q implementation/runtime_service/tests/test_engineering_migration_approval.py implementation/orchestrator/tests/test_engineering_migration_capability.py tools/tests/test_independent_governed_lane.py tools/tests/test_isolated_service_units.py tools/tests/test_pmv3_worker_release_gate.py tools/tests/test_ticket_continuity_evidence_review.py`

Passing source tests means only that code contracts pass. It never proves signed Teams card delivery, release eligibility, runtime installation, live ticket continuity or completed migration.
