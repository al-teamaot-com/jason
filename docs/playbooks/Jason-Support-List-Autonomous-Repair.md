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


### 4A. GitHub Issue Identity and Admission Collision Policy

The canonical SUPPORT identifier names an approved repair workstream; each GitHub issue number is a separate authoritative issue identity. Intake must retain **all** issue numbers that map to a support ID and report the real open-issue count. It must never silently overwrite one GitHub issue with another.

- When unrelated manual GitHub issues share one SUPPORT ID, classify the ID as an **identity conflict**, record the exact issue numbers and block automated admission/closure of that ambiguous workstream. Assign distinct canonical IDs in a separately reviewed source-and-issue migration before resuming. Do not infer that one issue supersedes another.
- When multiple SUPPORT-AUTO issues share the same fingerprinted ID, retain them as one logical diagnostic workstream and preserve **all** GitHub issue-number references. The existence of duplicate reports does not prove identical incident evidence or authorize automatic closure. Closure must remain fail-closed while more than one matching open issue exists.
- The admission audit records logical-ID count, open issue count, duplicate issue numbers, and manual identity conflicts. P0 collisions are explicit admission blockers; repeated auto incidents are reported as one deduplicated operational alert, not silently discarded.

This policy does not add provider write authority, change the maximum active-repair count, or relax the existing production-verification and release gates.


### 4B. Bounded read-only search request recovery

A model-generated \`search_source\` request must not specify a source \`path\`; that argument is reserved for independently authorized \`read_source\` calls. A rejected search does **not** grant implicit authorization to search arbitrary files, expand the source scope, reset the evidence budget, or retry an editing request without proof.

For an exact P0 \`EvidenceToolError: invalid source search\` blocker, the host worker may perform **one** new read-only evidence turn, only after a reviewed worker source upgrade and all of these preconditions:

- The original model response, its parent request and preceding successful evidence turn match the canonical support ID and content-addressed ancestry.
- The original branch remains clean and pinned to its recorded revision, the new recovery branch is independently clean and pinned to fetched authoritative \`origin/main\`, and the approved worker source blob has changed.
- Every request has a bounded, non-command query and known tool schema. A legacy **advisory** path on \`search_source\` is recorded as discarded and is never used for file selection, path authorization, or an executable command. All source results still pass normal Git-tracked, scoped and J-CHANGE-002 authorization checks.
- There is available native support-worker capacity, a remaining policy evidence-turn budget, no external-authority blocker, and no prior recovery marker. The original request and response remain immutable.

The recovery creates a fresh content-addressed reasoning request with authenticated lineage and read-only tool receipts. The worker cannot self-approve edits, bypass CI, mutate providers, deploy production, or close a support item based on this recovery. If evidence or authority is incomplete, the original blocked state remains and the worker must report the actual reason.

## 5. Expected State
Each approved support item is in exactly one durable state and progresses without owner prompting until verified complete or genuinely blocked.

## 6. State Model
`identified -> claimed -> diagnosing -> implementing -> validating -> pr_active -> ci_repair -> merge_ready -> deployed -> production_verifying -> complete`
Alternate terminal/intermediate states: `blocked`, `escalated`, `waiting_external_dependency`.
No state named or equivalent to “waiting for owner to say proceed” is valid for already-approved support work.
Owner-notification state is durable and duplicate-suppressed: record whether `repair_started`, `blocked_owner_action`, and `production_verified_complete` were successfully delivered/readback-verified for the current support workstream.
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
Keep `SUPPORT.md`, the GitHub support issue, repair PR, CI evidence, release evidence, and production acceptance synchronized. Record implementation commit/PR, regression proof, deployment revision, rollback target, production verification, and owner-notification correlation/message evidence. Never record secrets.

## 14A. Owner Teams Lifecycle Notifications
When an eligible support item is first claimed for repair, send Al one governed Teams **Repair Started** message containing the support ID, concise defect summary, and bounded repair scope. Do not resend it on every reconciliation.

If work becomes genuinely blocked on owner action or authority, send one **Blocked / Owner Action Required** message containing the support ID, exact blocker, evidence already gathered, and the smallest action or decision needed from the owner. Use the standardized Owner Action Request structure where applicable.

After the repair is deployed and the support item's explicit production acceptance criteria pass, send one **Production-Verified Complete** message containing the support ID, repaired behavior, merged/deployed revision, and concise acceptance evidence. CI success, merge success, or deployment alone is not sufficient for this completion message.

All support lifecycle messages use the canonical governed Teams owner path. Delivery is not complete until the exact destination plus durable message/correlation identity are captured and provider/readback verification proves the intended message exists. Apply bounded retry and duplicate suppression. Persistent unverified delivery becomes a support/health condition and must not silently mark the owner as notified.

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
Use the current active support repair set as the acceptance case. Prove that an open support item is picked up without a new owner prompt; exactly one Repair Started Teams message is delivered and readback-verified; an active repair PR is continued instead of duplicated; repair-owned CI/documentation failures are corrected; a controlled owner-action blocker produces exactly one Blocked / Owner Action Required message; eligible release proceeds through the existing governed lane; production acceptance is required before closure; exactly one Production-Verified Complete message is delivered and readback-verified only after acceptance succeeds; and a true governance/capability blocker stops safely.

## 22. Section Goal Closure
Close this Section Goal only after one support item completes end-to-end through the native Jason support-repair worker from autonomous pickup through production-verified closure without an owner “proceed” prompt.

## 23. Autonomous Execution Eligibility and Owner Review
`autonomous_allowed: exact bounded support-repair workflow`.
This owner instruction approves continuous processing of approved Support List defects under the existing governance boundaries. It does not grant new provider authority, constitutional authority, disruptive-action authority, secret access, or permission to bypass release gates. Material changes to those boundaries require separate owner review.


## Execution cadence

The native host worker runs every five minutes, 24x7. Operators may manually start `jason-support-repair-worker.service` at any time for an immediate support-list reconciliation; the continuous timer is the normal autonomous cadence.
