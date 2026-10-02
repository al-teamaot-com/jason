# Development & Release Coordinator

**Status:** Active  
**Owner:** Jason Architecture Authority  
**Authority:** `docs/engineering/Jason-Change-Integration-and-Release-Standard.md`  
**Scope:** Derived development/release visibility and advisory next-work recommendations  
**Canonical source:** Yes — operational procedure and behavior  
**Last reviewed:** 2026-10-02

## Purpose

The Development & Release Coordinator gives Project Jason one live view of parallel development without creating a second roadmap, source-control authority, production authority, or deployment mechanism.

It derives a control board from authoritative sources and publishes the current view to GitHub issue #526.

## Authoritative inputs

The coordinator reads:

- protected GitHub `main` and open pull requests;
- required GitHub check runs;
- implementation-sensitive changed files;
- `SUPPORT.md` for break/fix work;
- `docs/roadmaps/Jason-Roadmap-Status.json`;
- `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md`;
- `docs/control/AUTOMATED-CHANGE-STATE.json` for derived production-alignment evidence;
- `config/development-release-coordinator.json` for coordinator policy.

The board is derived evidence. None of these observations grant deployment, provider, roadmap, or execution authority.

## Development states

The coordinator uses the following states:

- **In development** — draft or not yet validated;
- **Validating** — current with main but required checks are still running;
- **Blocked** — a required check failed or is missing;
- **Needs revalidation** — the PR head does not contain current main;
- **CI-ready** — current with main and required checks pass, but no pre-production environment is configured;
- **Pre-prod ready** — reserved for a future configured pre-production environment.

CI-ready MUST NOT be represented as production-ready while pre-production is not configured.

## Parallel-work coordination

Parallel development is expected.

For recently active PRs, the coordinator compares implementation-sensitive changed files and reports overlaps. This is advisory visibility in addition to the fail-closed J-CHANGE-001 merge gate.

An overlap does not automatically prohibit parallel work. It means the workstreams need explicit reconciliation before merge.

## Recommendations

Recommendations are advisory only and intentionally separated into two questions:

- **Release attention** — recently active PRs that are stale or failing and therefore need reconciliation before promotion.
- **Recommended next development** — work that is useful to advance next, independent of release-lane housekeeping.

Development recommendation priority is:

1. open P0/P1 support defects in `SUPPORT.md`;
2. unblocked governed TODO items by priority.

The board shows recently active PRs and summarizes older open PRs rather than allowing historical branches to dominate the working view. Any older PR that resumes must still reconcile with current `main`.

Human roadmap authority remains controlling. The coordinator may recommend; it may not silently reorder or approve work.

## Autonomous Support List

Approved open `SUPPORT-*` defects are an owner-authorized break/fix work queue, not merely advisory recommendations. When `support_autonomy.enabled=true`, Jason must reconcile the list continuously and may carry an eligible defect through diagnosis, bounded implementation, regression testing, repair PR creation, CI correction, J-CHANGE-002 eligibility, governed autonomous deployment, production acceptance, documentation, and closure without waiting for another owner `proceed` message.

The native implementation boundary is split deliberately:

- the Jason runtime performs bounded structured repair reasoning and has no shell, GitHub credential, or deployment authority;
- the rootless host support-repair worker owns isolated worktree/GitHub mechanics but has no model credential and may apply only exact-text edits that pass deterministic J-CHANGE-002 path, size, regression-test, and merge checks;
- `deployment.repair.apply` may prepare/status a repair candidate but has no standing Production execution authority; final promotion must use the J-CHANGE-003 `jason.deployment.apply` lane;
- support closure requires the item's explicit production acceptance criteria. CI success, merge, deployment, or generic health alone do not prove resolution.

A support item stops automatically only for a genuine governance/capability blocker: constitutional change, broader authority/permission, secret exposure, provider bypass, client-scope expansion, unapproved disruptive behavior, ambiguous evidence, denied repair path, bounded retry exhaustion, or missing acceptance evidence. A blocked item does not consume an active implementation slot; Jason continues other independent support items within the configured active-work limit.

The canonical operational logic is `docs/playbooks/Jason-Support-List-Autonomous-Repair.md`.

## Production boundary

Production remains governed by J-CHANGE-001 and the existing J-900/J-901 release pipeline.

The coordinator does not deploy.

Production promotion remains serialized and requires an exact merged main SHA.

J-CHANGE-002 may autonomously classify, validate, package, and prepare an eligible repair through READY FOR PRODUCTION. It does not waive Production approval.\n\nJ-CHANGE-003 is the controlling Production authority: every material Production promotion requires explicit Owner approval bound to the exact promotion plan, followed by a signed single-use host permit and the named `jason.deployment.apply` lane. Classification, CI success, merge, or prior approval of the repaired behavior is not Production deployment authority.

## Automation

`.github/workflows/development-release-control-board.yml` refreshes the board:

- after pushes to main;
- after meaningful pull-request lifecycle changes;
- after `Validate Jason` completes;
- hourly as a reconciliation backstop;
- on manual dispatch.

The workflow checks out trusted `main` even for pull-request-triggered refreshes. It never executes code from an unmerged PR with issue-write permission.

### Governed PR source integration

The evidence-only control board remains read-only. A separate rootless user-level source-integration service, `jason-pr-integration-reconciler.timer`, runs every five minutes under the existing authenticated `al` GitHub identity. It is intentionally installed in the `al` user systemd manager so source reconciliation does not require root or production-runtime deployment authority.

A PR is eligible only when it is open, non-draft, from the same repository, authored by an OWNER/MEMBER/COLLABORATOR, and contains the exact opt-in line `Integration automation: enabled`.

For an eligible PR:

1. if it is behind `main`, the host runs GitHub's native `gh pr update-branch` and performs no merge in that cycle;
2. the native update produces the normal PR synchronize event, so protected CI runs in the PR context GitHub requires;
3. a later cycle reads `gh pr checks --required` and separately requires configured additional security checks;
4. immediately before merge, the host rechecks that the PR still contains current `main`;
5. only then may it run `gh pr merge --merge`.

Conflicts, failed/missing/pending checks, ambiguous identity/scope, and infrastructure errors fail closed. One blocked PR does not authorize bypass and does not prevent independent eligible PRs from being evaluated.

The host reconciler is source-control automation only. It does not deploy production or grant runtime/provider authority.

## Failure behavior

If authoritative evidence cannot be retrieved, the refresh fails rather than publishing invented state.

If production evidence is stale, the board displays the recorded observation instead of treating it as live production proof.

A failed board refresh must not affect runtime, provider access, deployment state, or open development branches.

## Future increments

After this first evidence-only version proves reliable, future controlled increments may add:

- a real pre-production environment;
- exact candidate promotion into pre-production;
- pre-production acceptance evidence;
- richer dependency declarations between workstreams;
- dashboard/Teams presentation;
- explicit release-candidate designation.

Those increments must preserve the authority boundary above.
