# J-CHANGE-002 — Autonomous Repair Release Standard

**Version:** 1.0  
**Status:** Active upon merge  
**Owner:** Jason Architecture Authority  
**Authority:** Jason Constitution; J-CHANGE-001; Jason Deployment System  
**Scope:** Production repair releases that restore previously approved Jason behavior without introducing new capability, authority, security, provider, dependency, schema, topology, client-scope, or disruptive-operational change  
**Canonical source:** Yes  
**Last reviewed:** 2026-09-28

## Purpose

Jason should not require a new human production approval merely to restore behavior that was already approved when the repair is narrow, deterministic, fully tested, reversible, and materially equivalent in authority and risk to the previously accepted behavior.

This standard defines a pre-authorized **Autonomous Repair Release** class.

The controlling rule is:

> Restoring previously approved behavior may be autonomous. Expanding or materially changing behavior may not.

## Repair versus change

A support fix is eligible to be considered a repair only when it restores an already approved and previously accepted behavior.

A repair SHALL NOT:

- create a new capability or workflow;
- add or broaden provider/API actions;
- add or broaden identity, permission, authority, approval, or execution scope;
- modify governance or security policy;
- alter secrets or credential handling;
- expand client/tenant scope;
- introduce a dependency or package;
- introduce a schema or migration;
- change infrastructure, deployment topology, or privileged host behavior;
- introduce disruptive operational behavior;
- bypass an existing gate, check, approval path, or evidence requirement.

If any statement above is false or uncertain, the change is not an Autonomous Repair Release and follows the normal human-approved production lane.

## Required evidence

An Autonomous Repair Release candidate SHALL reference one currently open `SUPPORT-*` item and include:

- the previously approved behavior being restored;
- the exact regression test added or changed for the defect;
- post-deploy verification proving the restored behavior;
- exact candidate SHA after merge;
- current known-good production SHA for rollback;
- protected validation results;
- production health evidence fresh enough for the configured policy.

The regression test must be part of the candidate change and must exercise the defect boundary materially enough to prevent a silent recurrence.

## Deterministic exclusion boundary

The autonomous-repair classifier fails closed when the change touches categories that require human review.

The initial protected exclusion set includes:

- GitHub workflow definitions;
- deployment and infrastructure artifacts;
- connector/provider implementation;
- governance, identity, security, authorization, authority, approval, permission, policy, secret, or credential paths;
- dependency manifests and lock files;
- migration artifacts;
- constitutional/release-control documents.

This exclusion set is intentionally conservative. A legitimate repair excluded by the classifier may still proceed through the normal human-approved release process.

## Size boundary

The initial autonomous class is bounded by the configured maximum changed-file and changed-line limits.

A change outside those limits is not presumed unsafe, but it is too broad for automatic repair classification and therefore requires the normal release path.

## Protected validation

The candidate must be merged into protected `main` and the exact merged SHA must pass the required post-merge checks.

Branch-local success alone is not sufficient production evidence. Universal protected checks must pass again on the merged SHA. Path-scoped or provider-specific checks that do not emit on an unrelated merge remain enforced by protected pull-request validation and are not treated as missing post-merge checks when their paths were not changed.

## Human approval rule

When all repair-eligibility criteria pass:

- the release class itself does **not** require a new human production approval;
- the previously approved behavior is the governing human authorization being restored;
- Jason may continue autonomously through the repair release lane.

When any repair-eligibility criterion fails or is uncertain:

- `human_approval_required=true`;
- the candidate falls back to the normal production release lane;
- no classifier output may be used to broaden authority.

## Production execution boundary

Autonomous repair classification is not arbitrary shell authority.

Production execution SHALL occur only through Jason's named governed deployment capability/runner using:

- the exact immutable merged SHA;
- the current known-good production SHA as rollback target;
- deterministic deployment artifacts;
- existing release/recovery checks;
- health verification;
- post-deploy acceptance specific to the support defect;
- evidence capture.

Until that named governed production execution path is enabled for this release class, an eligible repair is recorded as:

`autonomous_repair_authorized_blocked`

This state means **no additional human approval is required**, but execution is blocked by a missing technical execution path or another objective precondition.

## Production-side parent requirement

An autonomous repair release must not bundle unrelated protected-main changes.

The repair merge commit's first parent (the production-side main parent) SHALL equal the exact live production revision selected as rollback.

If production is behind any unrelated merged work, autonomous promotion stops. That work must first be reconciled through the normal release lane, or the repair must be rebuilt from the then-current production baseline.

## Production-state prerequisites

Autonomous execution fails closed when:

- current production is not reported healthy/aligned;
- production evidence is older than the configured freshness limit;
- the rollback revision is unknown;
- required protected checks are missing, pending, or failed;
- the exact merged candidate is not reachable from protected `main`;
- the repair merge's production-side parent does not equal the live rollback revision.

These are execution blockers, not requests for human approval.

## Rollback and failure

Any failed post-deploy verification SHALL:

1. preserve failure evidence;
2. stop further promotion activity;
3. invoke the governed rollback path to the recorded known-good revision when safe and supported;
4. verify restored production health;
5. keep the support item open or reopen it;
6. escalate the failed repair for human review.

A failed autonomous repair must never silently convert into an improvised second fix in production.

## Support-item closure

A support item is not resolved merely because source merged.

Closure requires:

- successful production execution;
- live post-deploy verification of the repaired behavior;
- production revision readback;
- no regression in required health/governance checks;
- recorded evidence linking the support item, PR, merge SHA, production SHA, and verification result.

## Initial rollout

The first rollout is intentionally limited to Jason's own software/service repairs.

Client endpoint actions, provider mutations, disruptive user actions, and other operational remediation retain their existing capability/playbook authority and approval rules. This standard governs **Jason software release approval**, not endpoint/provider operational authority.

## Related implementation

- `config/autonomous-repair-release-policy.json`
- `tools/autonomous_repair_release_gate.py`
- `.github/workflows/autonomous-repair-release.yml`
- `tools/tests/test_autonomous_repair_release_gate.py`
- `implementation/runtime_service/src/jason_runtime/autonomous_repair_deployment.py`
- `implementation/runtime_service/src/jason_runtime/autonomous_repair_maintenance.py`
- `tools/autonomous_repair_host_runner.py`
- `docs/operations/Autonomous-Repair-Deployment-Runner.md`
- J-CHANGE-001
- Jason Deployment System
- Development & Release Coordinator

## Revision notes

- 2026-09-28: Initial pre-authorized Autonomous Repair Release class established.
