# Jason Engineering Standards Registry

Status: Owner-approved standards. CI/Production Manager enforcement pending.
Authority: Project owner. Standards remain in force until explicitly superseded.
Scope: Jason engineering, AI-assisted development, reviews, tests, and releases.

## Standard lifecycle
When the owner establishes a standard, record its scope, rationale, examples, approval and verification method. Never report a standard as implemented unless committed and verified. Every change to a standard must preserve the prior decision and identify its explicit successor. Enforce machine-checkable standards with CI where feasible; otherwise require evidence-backed review.

## JES-001 — Development command formatting
- Interactive Linux shell command examples for Jason development begin with `clear` and `cd` into the verified working tree.
- Verify working tree, branch and source revision before changes. Do not blindly assume a worktree directory.
- Shell commands do not belong inside JSON files; JSON must remain valid JSON.
- Clearly separate commands from actual observed output, errors, and conclusions. Keep output concise and legible.
- In Datto RMM Windows jobs, default to PowerShell 5.1, SYSTEM, noninteractive. Do not prompt, reboot, reset networks, or interrupt services without explicit action-specific approval.
- Enforcement: documented; automated check pending.

## JES-002 — Build, prove, secure, retest, release
1. Implement the smallest working capability in an isolated, approved development environment.
2. Prove it through repeatable tests and provider-backed evidence where applicable.
3. Apply permissions, approval gates, security hardening, audit, and fail-closed behavior.
4. Retest functionality and security; regressions block advancement.
5. Prepare release with full scope, exact SHA, foundational checks, rollback readiness and required production authorization.
- Existing access controls remain in force from the start. Never bypass security or treat production as an ungoverned test environment.
- Passing unit tests alone does not demonstrate provider-backed functionality.
- Enforcement: documented; automated process gate pending.

## JES-003 — Mandatory explicit next step
Every work stoppage must report:
- Status: evidence-backed completion percentage, distinguishing planned, written, tested, merged, deployed and operational.
- Next step: one clear, executable action.
- Responsibility: assistant, Jason, or user.
- Approval: state whether new owner authorization is needed.
Proceed with work that has already been authorized; do not demand redundant approval. Never imply a proposed change has been completed.

## Conflict and priority
These standards do not replace existing human-governance, production-freeze, non-disruptive-operation or security requirements. More restrictive safeguards remain in force.

## Enforcement backlog
1. Add checkable documentation/standards validation in CI without weakening existing protected-branch checks.
2. Integrate review evidence into Production Manager before considering release.
3. Recover additional conventions from authoritative historical decisions; mark uncertain recollections as candidates, not facts.
