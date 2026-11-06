# P0 #1974 — documented technical review without a local AOT reviewer

**Review type:** AI-assisted source/security audit plus independently executing automated tests. **This is NOT an independent human code review.** The AOT Owner confirmed on October 23, 2026 that no local peer reviewer is available. Do not manufacture a reviewer, fake an approval or circumvent GitHub protection.

**Scope:** PR #1975, exact source branch fix/1974-root-drift-policy-gate-20261023. All checks must be repeated or verified on the final PR head. Owner exact-SHA production approval and CCC material review remain separate and mandatory.

## Boundaries actually examined

Immutable Git source identity and main ancestry, protected root-owned policy schema/mode and per-unit requirements, fixed four-unit delta, Owner/CCC authorization, audited original-byte ledger, bounded host reconciliation, full authority-health service execution, root LKG, circuit breaker, drift guard, incident hold and failed-release evidence.

## Concrete defects uncovered and source-corrected

1. Original PR denied the four missing declarations before the migration could be applied. Added read-only exact reviewed preview before the host script and independently verified final protected policy after it.
2. Preview read the candidate immutable host directory before it existed. Switched PREVIEW to exact Git objects with protected-main ancestry; actual APPLY still requires root-owned immutable release files.
3. New systemd units were installed before root-policy migration, producing an independent-drift race. Added early, stage-only root worker/rollback helper installation, an owner-reviewed ALLOWED-only policy state, and a separate REQUIRED timer commit after service activation.
4. Rollback originally removed root authorization before uninstalling candidate units. Changed to downgrade the new timer to ALLOWED first, execute and verify the old host reconciliation, check that all candidate-only unit files are absent, and restore exact original root-policy bytes last.
5. The historic legacy health budget was incorrectly described as 45 seconds; immutable source actually has 240 seconds and the failed start returned rc=124. Legacy compatibility is tied to the exact old SHA and full script SHA-256 and changes only that line to 300 seconds in a throwaway materialization, retaining the mandatory health scan, result checks and native 410/420/480-second boundaries.
6. Future releases after a legitimately advanced root LKG must recognize an already-committed migration only when exact LKG SHA, CLOSED breaker, verified ledger state and root policy digest all match.

## Assurance actually executed

- Isolated host pytest suites, including temporary-file real policy stage/commit/reverse and byte-for-byte restoration, simulated host health success and timeout, wrong authorization, malicious unit additions, root file mode and policy tampering.
- Static Python compilation, Bash parser check, Git diff whitespace checks.
- GitHub protected workflows: Validate Jason, SEC-007, Teams Gateway and Conversation Experience. All must be GREEN on the final exact SHA.

**Limitations:** These are real source and fixture tests but simulated systemd host outcomes. A full multi-minute root/systemd rollback through isolated preproduction has not been demonstrated. Do not claim a real production rollback based on fixture tests. The historical failed October 23 release remains failed, and its historical rollback_verified remains false.

## Review substitution / source-merge boundary

No local peer review will be an artificial source-development blocker. A documented AI-led code review plus protected CI and exact Owner production authorization are transparent compensating controls, **not a claim of independent human approval**. Obey actual GitHub branch protection. A normal protected PR merge is source-only; it is not permission to modify root policy, close the incident hold, or deploy. A new exact-SHA release still requires canonical Owner approval, CCC material review, native preproduction/rollback acceptance and root-governed promotion.
