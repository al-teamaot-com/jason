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
- unattended promotion runs every five minutes, 24x7;
- protected-core releases require owner approval bound to the exact candidate SHA;
- production success requires live SHA, image identity, and health verification;
- failed verification rolls back to the recorded known-good revision.

## 2. Trigger

The Release Manager applies when a protected-main software revision is nominated for production promotion.

The automatic production window is continuous 24x7. The Release Manager reconciles eligible releases every five minutes. The schedule is only a promotion trigger; it never creates Production Eligible status.

## 3. Scope and Boundaries

### In scope
- exact-SHA `jason-runtime` and `jason-mcp-pilot` image build, pre-production validation, promotion, verification, and rollback;
- root-owned immutable `/opt/jason/current` host-release reconciliation through the bounded release-host worker;
- Release Manager self-install from the immutable host release, including timer activation and rollback restoration;
- release records and immutable artifact evidence;
- Support List priority/release impact;
- rootless orchestration through the existing Docker-capable `al` account, with only the narrowly bounded host-release reconciliation delegated to the root-owned worker.

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

Healthy release state means the release record, exact source SHA, runtime image, MCP image, immutable host release, installed Release Manager source, active Release Manager timer, pre-production evidence, production state, and rollback state all agree on one exact revision.

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
**Evidence:** independent readback of `jason-runtime`, `jason-mcp-pilot`, and `/opt/jason/current`.
**Expected:** all three surfaces resolve to the same exact rollback SHA before a new release record can be created. A divergent baseline blocks before candidate build or production mutation.

### Step 3: Candidate identity
**Evidence:** content-addressed runtime and MCP Docker image IDs.
**Expected:** both images are built from the exact candidate SHA; the MCP candidate records its established production base image digest.

### Step 4: Pre-production
**Evidence:** isolated runtime candidate health, source labels, environment mutation guards, runtime deployment preflight, MCP deployment preflight, and installed root-host reconciler readiness.
**Expected:** runtime candidate healthy, production writable state cloned rather than shared, provider mutation profiles disabled, both exact artifacts preflight cleanly, and the privileged host boundary exists before the release can become Production Eligible.

### Step 5: Production
**Evidence:** canonical runtime and MCP deployment output, root-host reconciliation receipt, immutable host release readback, Release Manager reinstall evidence, active timer readback, and independent final alignment.
**Expected sequence:** runtime candidate -> MCP candidate -> `/opt/jason/current` candidate -> Release Manager install from immutable current release -> exact alignment verification. Production closes only when all surfaces equal the candidate SHA and both Docker production aliases equal the pre-production artifact digests.

## 8. Decision Gates

Promotion fails closed when:
- candidate is not an exact SHA;
- candidate is not on protected main;
- required checks are missing, pending, or failing;
- rollback SHA differs from any live production surface;
- runtime or MCP artifact identity changes after build;
- runtime, MCP, and immutable host baseline are revision-divergent;
- root-owned host reconciliation worker/path unit is absent or unsafe;
- pre-production state is not isolated;
- provider mutation guards are not active in pre-production;
- relevant Support blockers remain;
- protected-core owner approval is absent or bound to another SHA;
- production verification does not match the pre-production artifact.

## 9. Remediation

Release Manager remediation is limited to release mechanics.

**Production actions:** canonical runtime deployment script, canonical MCP deployment script, bounded root-host reconciliation request, and Release Manager reinstall from the resulting immutable host release.
**Approval classification:** modifying/disruptive production operation.  
**Verification:** runtime SHA/digest + MCP SHA/digest + immutable host SHA + Release Manager SHA/timer + health/alignment.

Protected-core releases remain approval-bound. Ordinary releases may auto-promote only after all evidence gates classify them Production Eligible.

## 10. Retry Policy

No blind deployment retries.

- Candidate build: one bounded attempt per release invocation.
- Pre-production: one bounded acceptance attempt; fix/rebuild produces new evidence.
- Production: one serialized multi-surface promotion attempt.
- Failed post-cutover verification: one deterministic reverse-order rollback attempt across MCP, immutable host release, Release Manager installation, and runtime for the surfaces that were changed.
- Rollback verification requires runtime + MCP + host + Release Manager to resolve to the recorded rollback SHA; failure stops and requires human review.

## 11. Periodic Rechecks

The production timer invokes `promote-eligible` every five minutes, 24x7. The host runner retains the centralized production-window policy gate, which is currently continuously open under owner-approved policy.

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
- healthy, revision-aligned current `jason-runtime`, `jason-mcp-pilot`, and `/opt/jason/current`;
- `jason-runtime:rollback-current` and `jason-mcp:rollback-current` image aliases;
- writable Release Manager state directory;
- canonical runtime and MCP production deployment scripts;
- root-owned `jason-release-host-reconcile.path` boundary installed by `tools/install_release_host_reconciler.py`;
- immutable host reconciliation script under `/opt/jason/current/tools/reconcile_production_host_services.sh`;
- Release Manager installer under the immutable host release.

Missing dependencies block before production transition; no privilege bypass, Docker-root escalation, or mutable-worktree substitute is permitted.

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

Production failure triggers deterministic reverse-order rollback using the recorded rollback SHA and the actual pre-cutover Docker aliases. The MCP is restored first, then the immutable host release, then the Release Manager installation/timer, then the runtime. Final rollback verification again requires runtime, MCP, host, and Release Manager alignment.

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
- live runtime health `healthy`;
- runtime source revision equals candidate SHA;
- MCP source revision equals candidate SHA and MCP is running;
- `/opt/jason/current` resolves to `/opt/jason/releases/<candidate-sha>`;
- installed Release Manager source resolves to the same immutable release and its timer is active;
- `jason-runtime:production` image ID equals the pre-production runtime artifact ID;
- `jason-mcp:production` image ID equals the pre-production MCP artifact ID;
- runtime and MCP deployment scripts reported `DEPLOYMENT=PASS`;
- root-host reconciliation reported success;
- the policy gate accepts all required production evidence.

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
5. verify the existing production baseline is exactly aligned across runtime, MCP, and immutable host release;
6. build exact runtime and MCP candidate images from the same candidate SHA;
7. run isolated runtime pre-production using cloned writable state and disabled provider mutations;
8. preflight both canonical runtime and MCP deployment scripts and verify the root-host reconciler is installed;
9. classify Production Eligible;
10. promote the exact tested runtime and MCP images, reconcile the immutable host release, and reinstall Release Manager from `/opt/jason/current`;
11. verify runtime SHA/digest, MCP SHA/digest, host SHA, Release Manager SHA, health, and timer state;
12. force a controlled verification failure in test coverage and prove reverse-order rollback restores all changed surfaces;
13. confirm the 24x7 five-minute production timer is enabled from the immutable candidate release;
14. confirm no release can skip gates;
15. preserve rollback artifacts and exact rollback evidence.

## 22. Section Goal Closure

Close only after the production acceptance above passes and the live release record reaches `closed`.

Any uncovered defect becomes a Support List item and is handled before ordinary feature work.

## 23. Autonomous Execution Eligibility and Owner Review

Normal non-protected releases may automatically promote after reaching Production Eligible.

Protected-core paths are defined in `config/release-manager-policy.json` and require explicit owner approval bound to the exact candidate SHA. The Release Manager itself is protected-core.

The owner instruction on 2026-10-02 to prioritize, complete, and push the deployment-management system to production authorizes the initial protected-core Release Manager production candidate only after all required gates pass. It does not waive future protected-core approval requirements.
