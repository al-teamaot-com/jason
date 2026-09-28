# J-CHANGE-001 — Change Integration and Production Release Standard

**Version:** 1.0  
**Status:** Active  
**Owner:** Jason Architecture Authority  
**Authority:** Jason Constitution; `CONTRIBUTING.md`; protected `main` branch validation  
**Scope:** Concurrent source development, pull-request integration, release-candidate selection, and production source promotion  
**Canonical source:** Yes  
**Supersedes:** None  
**Superseded by:** None  
**Last reviewed:** 2026-09-28  
**Review interval:** On material change to source-control, CI, deployment, or production reconciliation  
**Evidence references:** GitHub protected-branch checks; `tools/change_integration_gate.py`; `.github/workflows/production-release-preflight.yml`  
**Security / data handling:** No secrets or provider payloads are required by this control.

## Purpose

Jason frequently has multiple upgrades, fixes, documentation changes, and operational workstreams in progress at the same time. This standard prevents a valid change from overwriting, bypassing, or unintentionally invalidating another valid change.

The controlling principle is:

> Parallel development is allowed. Integration and production promotion are serialized against an exact authoritative source state.

## Governing context

This standard is subordinate to the Jason Constitution, canonical architecture, authority controls, and documentation-governance rules. It does not grant deployment or provider authority. It governs how approved source changes are reconciled before merge and how a production source revision is selected.

## Authoritative statements

### 1. Isolated development

Every material change SHALL be developed on an isolated branch or worktree created from an identified `main` revision.

A workstream SHALL NOT modify production source directly and SHALL NOT use another active workstream's mutable working tree as its development baseline.

### 2. Current-main reconciliation before merge

A pull request SHALL be reconciled with the current protected `main` branch before merge.

A PR whose head is behind current `main` SHALL fail the change-integration gate. The workstream must update/rebase/merge current `main`, re-run validation, and resolve any resulting conflicts before merge.

Passing tests against the branch's original base is not sufficient.

### 3. Active-work overlap detection

The change-integration gate SHALL compare implementation-sensitive files changed by the current PR with other open PRs targeting the same base branch.

Implementation-sensitive paths include:

- `.github/workflows/`
- `implementation/`
- `infrastructure/`
- `deploy/`
- `config/`
- `scripts/`
- `tools/`
- root engineering-control files such as `CONTRIBUTING.md` and the PR template

Documentation-only overlap is advisory unless the overlapping document itself governs source integration or production state.

If another recently active PR changes the same implementation-sensitive file, the current PR SHALL explicitly identify that PR and confirm the overlap was reviewed. Unacknowledged overlap SHALL fail closed.

Older open PRs are still reported for awareness but do not permanently block unrelated current work. If an older PR resumes, its own integration gate must reconcile it against current `main`.

### 4. Exact immutable release candidate

Production SHALL be promoted from an exact commit SHA that already exists on protected `main`.

Production deployment SHALL NOT use a moving branch reference, an unmerged feature branch, or an instruction equivalent to "deploy/pull whatever is latest now."

The selected release SHA is immutable for that release attempt even if additional work merges into `main` while validation or deployment is in progress.

### 5. Serialized production release lane

Production source promotions SHALL use one logical release lane.

The GitHub production-release preflight uses the concurrency group `jason-production-release` with `cancel-in-progress: false`. A newer release request must wait for the current release preflight/promotion sequence rather than superseding it.

A production promotion must preserve:

- target release SHA;
- expected current production SHA when known;
- release summary;
- verification plan;
- rollback target.

### 6. Verification after promotion

A source promotion is not complete merely because files copied, containers rebuilt, or services restarted successfully.

Post-promotion verification SHALL confirm the live runtime is actually running the intended immutable source revision and that applicable health, governance, capability, activation-profile, and protected validation expectations still hold.

If production does not match the selected release SHA, the release is incomplete and must fail closed or roll back.

### 7. Rollback

Rollback SHALL target a known previously accepted immutable production revision. Rollback SHALL NOT be implemented as an uncontrolled reverse merge or by rebuilding from an unknown mutable branch state.

### 8. Documentation reconciliation is downstream evidence, not a competing source lane

Automated documentation reconciliation may create follow-up PRs after validated source changes. Those PRs remain normal workstreams and must not cause a production deployment process to change its already-selected release SHA.

## Integration decision procedure

Before merging a material PR:

1. Confirm the PR head contains current `main`.
2. Run protected validation.
3. Review active overlapping PRs reported by the integration gate.
4. Reconcile or explicitly coordinate any implementation-sensitive overlap.
5. Re-run validation after reconciliation.
6. Merge only the reconciled PR.
7. Select production release candidates only from merged `main`.

Before production promotion:

1. Select an exact merged `main` SHA.
2. Run the production release preflight for that SHA.
3. Confirm expected current production revision.
4. Promote only the selected SHA.
5. Verify live revision and health.
6. Record success or roll back to the known prior accepted revision.

## Boundaries and dependencies

This control does not replace:

- GitHub branch protection;
- capability/provider governance;
- production runtime verification;
- System Registry truth;
- approval requirements for disruptive or governed operational actions;
- documentation reconciliation.

It coordinates source state across those controls.

## Verification / evidence

Source integration evidence is produced by:

- the protected `repository-hygiene` validation job;
- `tools/change_integration_gate.py`;
- PR integration-coordination declarations;
- current GitHub base/head SHAs.

Release-candidate evidence is produced by:

- `.github/workflows/production-release-preflight.yml`;
- the exact target SHA;
- the generated release manifest artifact.

Live production acceptance still requires direct production verification; successful source validation alone is not production proof.

## Failure / drift handling

Fail closed when:

- the PR is behind current `main`;
- an active implementation-sensitive overlap exists and is not acknowledged;
- the requested release SHA is not reachable from protected `main`;
- the release SHA is ambiguous or moving;
- live production revision cannot be verified after promotion.

## Change / rollback / retirement

Changes to this standard require the normal protected PR path. If the overlap detector produces persistent false positives, adjust path classification or active-window logic with tests; do not disable the gate to bypass a specific conflict.

Retirement requires an equal or stronger mechanism that preserves exact-source reconciliation, active-work collision detection, immutable release selection, and serialized promotion.

## Related records

- `CONTRIBUTING.md`
- `.github/pull_request_template.md`
- `.github/workflows/validate.yml`
- `.github/workflows/production-release-preflight.yml`
- `docs/control/CURRENT.md`
- `docs/control/AUTOMATED-CHANGE-STATE.json`

## Revision notes

- 2026-09-28: Initial active standard created to prevent concurrent Project Jason workstreams from stepping on one another during merge and production promotion.
