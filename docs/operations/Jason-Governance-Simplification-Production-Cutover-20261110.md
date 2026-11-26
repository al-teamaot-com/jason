# Project Jason Governance Simplification — Production Cutover Runbook

**Date:** 2026-11-10
**Purpose:** Execute the already-reviewed simplification without reintroducing duplicate approvals or disrupting ticket processing.

## 1. Preconditions — do not start production mutation until all are true

1. The selected Teams Owner-approval repair is merged to protected main and reconciled with the one-decision release contract from PR #2399.
2. A real Owner approval request is deliverable to the licensed Teams identity and the authenticated decision path can produce root-consumable signed evidence for the exact release.
3. Protected main is the intended candidate; worktree/PR overlap inventory is current.
4. Current production LKG is healthy and rollback identity is verified.
5. Production circuit breaker is CLOSED, or a separately reviewed recovery path is explicitly in use.
6. No production transaction is active.
7. Targeted/security CI and production-equivalent preproduction are green.
8. Autonomous ticket processing is healthy before cutover; record current active/waiting counts and a representative provider-backed ticket read.
9. Root/storage headroom is sufficient for release and rollback. Do not consume the nearly-full primary filesystem for engineering worktrees.

## 2. First release — establish the one-Owner-decision release path

Candidate: protected main containing PR #2399 plus the selected Teams routing/authentication repair.

Owner experience must be exactly:

**Teams review → one exact Approve/Reject decision → Production Manager transaction → verification/result**

Do not request:
- a second unfreeze approval;
- CCC material-review approval;
- replacement-unfreeze approval;
- initial-unfreeze-renewal approval;
- another chat/SSH “proceed” for the same unchanged release.

The exact Owner approval must bind candidate SHA, reviewed scope SHA-256, rollback SHA, manifest fingerprint, authenticated identity, and replay/expiry evidence.

### Required release checks

- Production Manager holds the exclusive mutation lock.
- Technical engineering-worker quiescence is proven during mutation.
- The legacy freeze marker, if still installed, is opened/restored internally by the exact release transaction; it is not another human authorization.
- Runtime/MCP/host revision and immutable image identities match the candidate after deployment.
- Protected drift and complete production manifest pass.
- Ticket processing continuity passes before release close.
- Failure at any acceptance check invokes the pinned rollback and verifies rollback state before clearing the breaker.

## 3. Release-lock convergence

After the first release succeeds:
- verify production revision equals protected main;
- verify the PMV3 integration queue no longer reports main→production drift/release lock for normal work;
- verify no obsolete pending CCC-only/unfreeze/replacement/renewal offer was generated;
- preserve historical receipts as audit evidence; do not delete durable history merely because issuance is retired.

Only after this convergence should normal simplification follow-ups integrate.

## 4. Integrate normal follow-up PRs through the standard queue

Recommended order:

1. **PR #2400 — standing Engineering Owner Pause retirement**
   - source contract changes replacement engineering lanes from pause receipt/drop-in to technical quiescence;
   - preserve #2386 second-drive worktree placement when reconciled;
   - preserve #2391 service-separation topology, ticket-continuity evidence and rollback contract, while superseding its standing Owner-pause requirement;
   - do not activate replacement timers merely by merging source.

2. **PR #2401 — autonomy authority envelopes**
   - execution remains exact-version promoted;
   - existing legacy exact promotions remain exact-only;
   - first new Owner promotion seeds an envelope;
   - later version-only changes may inherit only when every non-version registry field is identical;
   - verify root revocation invalidates derived version promotion.

3. **PR #2402 — risk-based independent review**
   - policy/documentation activation only;
   - protected CI remains mandatory;
   - independent review applies only to the protected boundaries defined in the risk policy.

Do not mark #2400/#2401/#2402 as release-recovery merely to bypass the integration queue.

## 5. Engineering-controller migration — when replacement lanes are actually activated

This is separate from merging PR #2400.

Before enabling any replacement independent engineering lane:
1. stop/disable the legacy engineering timer through the governed migration transaction;
2. prove legacy `jason-support-repair-worker.service` is `inactive`;
3. prove legacy `jason-support-repair-worker.timer` is `inactive` and `disabled` or `masked`;
4. verify replacement installed worker bytes match protected source;
5. verify production transaction lock sharing and lane single-flight lock;
6. run support lane first;
7. require successful current-revision support evidence before TODO/development lanes;
8. run at least two independent post-cutover cycles;
9. verify Autotask ticket processing and normal autonomous worker continuity are unchanged;
10. only then retire the old pause receipt/drop-in as installed artifacts.

If the old service/timer is active or can restart, fail closed; do not run a replacement lane concurrently.

## 6. Post-release acceptance

A simplification release is not complete until all applicable checks pass:

- no duplicate Owner release/unfreeze/CCC prompt;
- exact release approval cannot authorize changed SHA/scope/rollback/manifest;
- forged/stale/replayed approval remains denied;
- no concurrent production mutation;
- ticket discovery/admission/worker/supervisor remain healthy;
- representative Autotask/Datto governed reads succeed;
- no provider authority expansion occurred;
- disruptive endpoint actions remain specifically approval-gated;
- rollback remains verified;
- production manifest and drift are clean.

For #2401 specifically:
- version-only test revision can inherit a seeded envelope and creates a new exact-version durable promotion;
- any trigger/gate/capability/remediation/source/review-status change produces a different envelope and requires Owner review;
- revoking the root envelope disables derived promotions.

## 7. Rollback / stop conditions

Rollback or stop immediately if:
- ticket processing degrades;
- production state cannot be authoritatively read back;
- release identity or manifest mismatches;
- breaker opens for a genuine health failure;
- concurrent controller/lane execution is observed;
- an approval is accepted for changed arguments/scope;
- client/tenant/provider authority broadens unexpectedly;
- legacy controller can restart while replacement lanes are active.

Do not roll back merely because an obsolete duplicate approval artifact is absent—that absence is an intended result of this project.

## 8. Completion definition

The project-level simplification is complete when:

- normal release UX requires one exact Owner decision;
- no routine CCC/unfreeze/replacement/renewal Owner ceremony remains;
- standing Engineering Owner Pause is not an authorization primitive;
- independent review is risk-triggered;
- playbook version-only revisions do not require repeated Owner promotion once their exact authority envelope is seeded;
- one normal release path and one bounded recovery path are operational;
- ticket processing and existing provider functionality are verified unchanged.
