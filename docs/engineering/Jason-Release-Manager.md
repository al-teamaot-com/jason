# Jason Release Manager

**Version:** 1.0  
**Status:** Production candidate  
**Owner:** Jason Architecture Authority  
**Authority:** Jason Constitution; J-CHANGE-001; J-CHANGE-002; Jason Deployment System  
**Target:** Project Jason software releases

## 1. Section Goal

**Goal:** Jason must manage an evidence-gated software release from development through immutable candidate creation, isolated pre-production validation, Production Eligible classification, serialized production promotion, authoritative verification, and rollback.

**Success means:**
- no lifecycle stage can be skipped;
- the exact image tested in pre-production is the image promoted to production;
- pre-production cannot write production state or activate provider mutations;
- Support List impact is checked before Production Eligible;
- unattended promotion runs only during the approved production window: weekdays 17:00-05:00 America/New_York and continuously on weekends;
- protected-core releases require owner approval bound to the exact candidate SHA;
- production success requires live SHA, image identity, and health verification;
- failed verification rolls back to the recorded known-good revision.

## 2. Trigger

The Release Manager applies when a protected-main software revision is nominated for production promotion.

The automatic production window is weekdays 17:00-05:00 America/New_York and continuously from Friday 17:00 through Monday 05:00. During the window, the Release Manager reconciles eligible releases every five minutes. The schedule is only a promotion trigger; it never creates Production Eligible status. Explicit owner-driven promotion remains available outside the unattended window.

## 3. Scope and Boundaries

### In scope
- `jason-runtime` software image build, pre-production validation, promotion, verification, and rollback;
- release records and immutable artifact evidence;
- Support List priority/release impact;
- rootless host execution through the existing Docker-capable `al` account.

### Out of scope
- direct provider mutation during pre-production;
- arbitrary shell commands requested by a caller;
- client endpoint deployment;
- untracked images or symbolic refs such as `main`;
- changing governance merely to make a release pass.

Preserve Central Orchestrator authority, `direct_provider_access=false`, provider/client isolation, approval requirements, disruption controls, and auditable bounded execution.

## 4. Initial Identification

Before a release is admitted:
1. resolve exact candidate SHA;
2. resolve exact current healthy production SHA as rollback SHA;
3. verify candidate is reachable from protected `origin/main`;
4. verify required protected GitHub checks;
5. record changed files;
6. classify protected-core impact;
7. record Support List impact;
8. bind any required owner approval to the exact candidate SHA.

## 5. Expected State

Healthy release state means the current release record, exact source SHA, exact local Docker image ID, pre-production evidence, production state, and rollback state agree.

## 6. State Model

`requested -> development -> dev_verified -> release_candidate -> preproduction -> preprod_verified -> production_eligible -> production -> production_verified -> closed`

Failure branches:

`blocked | failed | rolled_back`

State is persisted under `/var/lib/jason/openclaw/release-manager/records`.

## 7. Diagnostic Workflow

### Step 1: Protected source verification
**Evidence:** local Git + GitHub check-runs.  
**Expected:** exact SHA is on protected main and all configured checks are green.

### Step 2: Production baseline
**Evidence:** Docker inspect of `jason-runtime`.  
**Expected:** health `healthy`; exact source revision label; exact rollback image available.

### Step 3: Candidate identity
**Evidence:** content-addressed Docker image ID.  
**Expected:** one image built from the exact candidate SHA.

### Step 4: Pre-production
**Evidence:** isolated candidate container health, source labels, environment mutation guards, and production deployment preflight.  
**Expected:** candidate healthy, production writable state cloned rather than shared, provider mutation profiles disabled.

### Step 5: Production
**Evidence:** canonical `infrastructure/jason-runtime/production-deploy.sh` output plus independent Docker readback.  
**Expected:** exact candidate SHA, exact candidate image ID, healthy runtime.

## 8. Decision Gates

Promotion fails closed when:
- candidate is not an exact SHA;
- candidate is not on protected main;
- required checks are missing, pending, or failing;
- rollback SHA differs from live production;
- artifact identity changes after build;
- pre-production state is not isolated;
- provider mutation guards are not active in pre-production;
- relevant Support blockers remain;
- protected-core owner approval is absent or bound to another SHA;
- production verification does not match the pre-production artifact.

## 9. Remediation

Release Manager remediation is limited to release mechanics.

**Production action:** canonical production deployment script.  
**Approval classification:** modifying/disruptive production operation.  
**Verification:** exact live source SHA + image ID + health.

Protected-core releases remain approval-bound. Ordinary releases may auto-promote only after all evidence gates classify them Production Eligible.

## 10. Retry Policy

No blind deployment retries.

- Candidate build: one bounded attempt per release invocation.
- Pre-production: one bounded acceptance attempt; fix/rebuild produces new evidence.
- Production: one promotion attempt.
- Failed post-cutover verification: one deterministic rollback attempt.
- Rollback verification failure: stop and require human review.

## 11. Periodic Rechecks

The production-window timer invokes `promote-eligible` every five minutes while the approved window is open. The host runner independently enforces the same window so a stale/persistent timer cannot promote outside it.

It:
- scans durable release records;
- selects at most one Production Eligible record;
- performs no action when none is eligible.

## 12. Aging / Stale Condition

A candidate becomes stale if:
- artifact identity changes;
- protected main or relevant release-control contracts materially change after evidence collection;
- current production revision no longer equals the release rollback SHA;
- owner approval no longer matches the exact protected-core candidate.

A stale candidate returns to development/revalidation.

## 13. Dependency Handling

Required dependencies:
- protected GitHub main/check evidence;
- Docker;
- healthy current `jason-runtime`;
- `jason-runtime:rollback-current` image alias;
- writable host release-state directory;
- production deployment script.

Missing dependencies block promotion; no substitutes are invented.

## 14. Documentation Requirements

Each record preserves:
- state history;
- exact source/candidate/rollback SHAs;
- changed files;
- required-check evidence;
- artifact image and image ID;
- pre-production acceptance;
- Support impact;
- owner approval when required;
- production/rollback result;
- final verification timestamp.

Secrets are never stored in release records.

## 15. Failure Handling

Failures preserve evidence and stop forward movement.

Production failure triggers deterministic rollback using `jason-runtime:rollback-current` and the exact recorded rollback SHA. Rollback must itself be verified.

## 16. Escalation Criteria

Human review is required for:
- protected-core release without exact owner approval;
- ambiguous current production identity;
- missing rollback artifact;
- contradictory evidence;
- failed rollback verification;
- requested authority expansion;
- any unexpected host/deployment condition outside the deterministic contract.

## 17. Verification

A deployment command returning zero is insufficient.

Production verification requires:
- live container health `healthy`;
- `com.teamaot.jason.source_revision` equals candidate SHA;
- `jason-runtime:production` image ID equals the pre-production artifact ID;
- deployment script reported `DEPLOYMENT=PASS`.

## 18. Completion Criteria

A release closes only after `production_verified`.

Merge, CI pass, image build, pre-production pass, or deployment command success alone do not close the release.

## 19. Final Resolution Note

The durable release record is the authoritative release resolution package and contains original candidate, rollback baseline, evidence, promotion, verification, and rollback information.

## 20. Required Capabilities

The initial host implementation reuses:
- protected Git source/check evidence;
- Docker image build/inspect;
- isolated candidate execution;
- canonical production deployment script;
- production health/source readback;
- deterministic rollback.

Future conversational/runtime callers should request these operations through the canonical deployment capability boundary rather than duplicate host/provider plumbing.

## 21. Acceptance Test

For the initial production activation:
1. merge exact Release Manager source through protected main;
2. verify all required checks;
3. install the rootless Release Manager service/timer;
4. create a protected-core release record for that exact merged SHA, bound to the owner explicit approval;
5. build one exact candidate image;
6. run isolated pre-production using cloned writable state and disabled provider mutations;
7. verify production deployment preflight;
8. classify Production Eligible;
9. promote that same image;
10. verify exact live SHA/image/health;
11. confirm the weekday 17:00-05:00 and weekend-continuous production-window timer is enabled;
12. confirm no release can skip gates;
13. preserve rollback-current artifact.

## 22. Section Goal Closure

Close only after the production acceptance above passes and the live release record reaches `closed`.

Any uncovered defect becomes a Support List item and is handled before ordinary feature work.

## 23. Autonomous Execution Eligibility and Owner Review

Normal non-protected releases may automatically promote after reaching Production Eligible.

Protected-core paths are defined in `config/release-manager-policy.json` and require explicit owner approval bound to the exact candidate SHA. The Release Manager itself is protected-core.

The owner instruction on 2026-10-02 to prioritize, complete, and push the deployment-management system to production authorizes the initial protected-core Release Manager production candidate only after all required gates pass. It does not waive future protected-core approval requirements.
