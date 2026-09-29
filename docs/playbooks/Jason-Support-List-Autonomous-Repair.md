# Jason Playbook: Autonomous Support List Repair

## 1. Section Goal
Jason continuously processes approved open `SUPPORT-*` defects without requiring repeated owner prompts. Success means an item is claimed, diagnosed, repaired when safely possible, validated, released through the governed lane, production-verified, documented, and closed; or it is left in an explicit blocked/escalated state with the exact reason.

## 2. Trigger
Trigger on every open approved row in `SUPPORT.md` and its matching GitHub support issue. Reconcile hourly and on support/PR/CI/release state changes.

## 3. Scope and Boundaries
In scope: break/fix work that restores previously approved Jason behavior, including source fixes, regression tests, CI correction, documentation, release reconciliation, eligible autonomous repair deployment, production acceptance, and closure.
Out of scope: constitutional changes, authority expansion, secret exposure, unapproved disruptive actions, provider bypasses, client-scope expansion, or unrelated product/roadmap work.
Preserve Central Orchestrator authority, `direct_provider_access=false`, exact grants, provider/client isolation, approval controls, audit, and serialized production promotion.

## 4. Initial Identification
Resolve the exact support ID, GitHub issue, current status, acceptance criteria, related PRs/branches, production revision, and any overlapping active repair. Never create a duplicate repair workstream when one already exists.

## 5. Expected State
Each approved support item is in exactly one durable state and progresses without owner prompting until verified complete or genuinely blocked.

## 6. State Model
`identified -> claimed -> diagnosing -> implementing -> validating -> pr_active -> ci_repair -> merge_ready -> deployed -> production_verifying -> complete`
Alternate terminal/intermediate states: `blocked`, `escalated`, `waiting_external_dependency`.
No state named or equivalent to “waiting for owner to say proceed” is valid for already-approved support work.
## 7. Diagnostic Workflow
Use authoritative repository, CI, runtime, GitHub issue, and production evidence. Reproduce the defect where safe. Separate symptom, root cause, and acceptance proof. Prefer the smallest shared root cause that resolves multiple support items without broadening scope.

## 8. Decision Gates
Before implementation: exact support item and acceptance criteria known; no duplicate active repair; no unrelated file overlap that would make the change unsafe; repair remains within existing authority.
Before merge/deploy: required tests/checks pass; current main is reconciled; release metadata is complete; production parent/revision constraints pass.
Before closure: explicit production acceptance criteria pass.

## 9. Remediation
Create an isolated branch/worktree. Implement the smallest bounded fix. Add a regression test for the observed failure. Do not modify unrelated untracked files. CI-owned documentation/metadata defects caused by the repair are part of the repair and should be corrected automatically.

## 10. Retry Policy
At most two implementation/CI correction attempts for the same root cause before re-diagnosis. Do not repeat identical failed changes. Deployment retries remain governed by the autonomous repair release policy and rollback rules.

## 11. Periodic Rechecks
Reconcile at least hourly while open. Also continue immediately after meaningful PR, CI, merge, deployment, or production-verification state changes when the automation surface supports it. Suppress duplicate work and duplicate status noise.

## 12. Aging / Stale Condition
Any claimed support item with no meaningful progress across three scheduled reconciliations must be re-diagnosed. If the blocker is external, persist the dependency and continue other independent support items.

## 13. Dependency Handling
Confirm missing dependencies, avoid duplicate dependency issues, cross-reference them, and mark the support item `waiting_external_dependency`. Continue another independent eligible support item when capacity permits.

## 14. Documentation Requirements
Keep `SUPPORT.md`, the GitHub support issue, repair PR, CI evidence, release evidence, and production acceptance synchronized. Record implementation commit/PR, regression proof, deployment revision, rollback target, and production verification. Never record secrets.

## 15. Failure Handling
A failed read, test, check, merge, deployment, verification, or documentation gate is actionable repair evidence. If caused by the repair, diagnose and correct it automatically. Do not silently leave a failed gate awaiting manual continuation.
## 16. Escalation Criteria
Stop only when continuing would require a constitutional/governance change, broader authority or permission, secret exposure, provider bypass, client-scope expansion, an unapproved disruptive production action, unresolved identity/evidence ambiguity, or a capability that Jason does not possess. Persist the exact blocker and recommended next capability/action.

## 17. Verification
Use the support item's own acceptance criteria as authoritative verification. Code merge, CI success, or process completion alone is not resolution.

## 18. Completion Criteria
Complete only when the repair is on the intended production revision, runtime is healthy, the explicit production acceptance test passes, support documentation is synchronized, and the GitHub support issue can be closed truthfully.

## 19. Final Resolution Note
Record original defect, root cause, files/behavior changed, tests, PR/merge, production revision, production acceptance evidence, timestamp, and final disposition.

## 20. Required Capabilities
Required now: GitHub support/PR/check access; isolated repository worktree/branch operations; test execution; governed release/deployment evidence; production status/acceptance reads; support documentation updates; persisted automation state; and the native support-repair reasoning/host-worker boundary. The runtime model has no shell, GitHub credentials, or deployment authority. The host worker has no model credential and may apply only exact-text edits that pass J-CHANGE-002 path, size, test, and merge gates.

## 21. Acceptance Test
Use the current active support repair set as the acceptance case. Prove that an open support item is picked up without a new owner prompt, an active repair PR is continued instead of duplicated, repair-owned CI/documentation failures are corrected, eligible release proceeds through the existing governed lane, production acceptance is required before closure, and a true governance/capability blocker stops safely.

## 22. Section Goal Closure
Close this Section Goal only after one support item completes end-to-end through the native Jason support-repair worker from autonomous pickup through production-verified closure without an owner “proceed” prompt.

## 23. Autonomous Execution Eligibility and Owner Review
`autonomous_allowed: exact bounded support-repair workflow`.
This owner instruction approves continuous processing of approved Support List defects under the existing governance boundaries. It does not grant new provider authority, constitutional authority, disruptive-action authority, secret access, or permission to bypass release gates. Material changes to those boundaries require separate owner review.
