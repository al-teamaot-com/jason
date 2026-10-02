# Jason Release Manager — Non-Production Pilot

**Version:** 0.1  
**Status:** Non-production implementation / validation pilot  
**Owner:** Jason Architecture Authority  
**Authority:** Jason Constitution; J-CHANGE-001; J-CHANGE-002; Jason Deployment System  
**Scope:** Development admission, immutable release-candidate formation, pre-production verification, Production Eligible classification, and Support List priority  
**Production execution:** Explicitly disabled in this pilot

## 1. Section Goal

**Goal:** Establish a machine-enforced Jason-managed path from requested change through Development, immutable Release Candidate, Pre-Production verification, and Production Eligible classification without permitting production execution.

**Success means:**
- release states cannot be skipped;
- immutable candidate SHA and artifact identity survive pre-production unchanged;
- failed or missing evidence blocks forward movement;
- Support List work is scheduled ahead of TODO/feature work when Support repair capacity is available;
- Production Eligible requires a completed Support List impact check;
- no code path in the pilot can transition a release into Production.

## 2. Trigger

This pilot applies when Jason is asked to develop, repair, validate, or prepare a Project Jason source change for future production release.

## 3. Scope and Boundaries

### In scope
- Project Jason source development;
- release-state validation;
- Support List/TODO priority planning;
- immutable release candidate evidence;
- pre-production admission and verification evidence;
- Production Eligible classification.

### Out of scope
- production deployment;
- production rollback execution;
- new provider authority;
- direct provider access;
- weakening approval/governance boundaries.

Preserve Central Orchestrator authority, `direct_provider_access=false`, provider/client isolation, existing approvals, disruption protections, and auditability.

## 4. Initial Identification

Each release record identifies:
1. release/change ID;
2. change class (`support`, `todo`, `feature`, or other governed class);
3. associated Support/TODO record where applicable;
4. exact development source SHA;
5. exact immutable candidate SHA;
6. artifact digest;
7. pre-production evidence;
8. Support List impact result.

## 5. Expected State

A healthy release moves only through the declared states with all required evidence present. The same candidate SHA and artifact digest tested in pre-production must be the candidate classified Production Eligible.

## 6. State Model

`requested -> development -> dev_verified -> release_candidate -> preproduction -> preprod_verified -> production_eligible`

The full future lifecycle also defines `production -> production_verified -> closed`, plus `blocked`, `failed`, and `rolled_back`. In this pilot, transitions into Production are explicitly denied.

## 7. Diagnostic / Evidence Workflow

Development verification requires:
- exact source SHA;
- development tests passed;
- required protected checks passed.

Release Candidate formation requires:
- exact candidate SHA;
- immutable marker;
- artifact digest;
- candidate SHA equal to the dev-verified source SHA.

Pre-Production verification requires:
- exact deployed SHA;
- exact artifact digest;
- acceptance tests passed;
- failure-path tests passed;
- rollback-readiness test passed.

Production Eligible requires:
- exact candidate identity preserved through pre-production;
- pre-production acceptance passed;
- Support List impact check completed;
- no blocking Support items remain, excluding the release's own Support defect when that defect cannot close until later production verification.

## 8. Decision Gates

Forward movement fails closed on:
- illegal or skipped transition;
- missing required evidence;
- candidate SHA drift;
- artifact digest drift;
- pre-production environment unavailable;
- failed acceptance/failure-path/rollback-readiness tests;
- unresolved blocking Support impact;
- any attempted Production transition while the pilot is in non-production mode.

## 9. Remediation

Not applicable to production. Development fixes remain isolated source changes and must re-enter the state model at the appropriate earlier state after material modification.

## 10. Retry Policy

A failed gate is not retried blindly. Correct the missing/failed evidence, materially update the release record, and re-evaluate from the last valid state.

## 11. Periodic Rechecks

Not required for the initial source-only pilot. Future pre-production environment integration may add bounded environment-health rechecks.

## 12. Aging / Stale Condition

A release candidate becomes stale when protected `main`, required contracts, or relevant Support blockers materially change such that prior evidence no longer establishes safety. Stale candidates return to Development/revalidation.

## 13. Dependency Handling

Missing pre-production infrastructure is an explicit blocker. The gate does not pretend pre-production exists and does not substitute production as a test environment.

## 14. Documentation Requirements

Every state transition records:
- prior state;
- target state;
- candidate/source SHA;
- artifact digest when applicable;
- gate result;
- blockers;
- Support impact;
- verification evidence references.

## 15. Failure Handling

Failures stop promotion. No failed pre-production result can be overridden by prose such as "close enough" or by a deployment-success signal.

## 16. Escalation Criteria

Human review is required when governance/authority changes are proposed, evidence is contradictory, no safe rollback exists, or pre-production cannot represent the affected production boundary adequately.

## 17. Verification

The pilot verifies release-control behavior only. It does not assert production behavior.

## 18. Completion Criteria

The pilot's terminal success state is `production_eligible`. Production execution remains a separate future implementation and is impossible under `config/release-manager-policy.json` while `mode=non_production_only` and `production_transition_enabled=false`.

## 19. Final Resolution Note

For Support fixes, the Support item must remain open until later production verification proves the original defect is actually corrected. Source merge, RC formation, and pre-production success are not closure evidence.

## 20. Required Capabilities

- GitHub source/PR evidence;
- protected check evidence;
- Support List read;
- TODO backlog read;
- immutable SHA/digest evidence;
- pre-production evidence source when configured;
- persisted release record.

## 21. Acceptance Test

The non-production test suite must prove:
1. Support List priority over TODO starts when Support capacity exists;
2. TODO continuation is permitted once configured Support repair capacity is full;
3. state skipping is rejected;
4. release candidate SHA drift is rejected;
5. pre-production is blocked while the environment is unconfigured;
6. pre-production candidate/artifact drift is rejected;
7. unresolved Support blockers prevent Production Eligible;
8. attempted Production transition is rejected.

## 22. Section Goal Closure

This non-production Section Goal closes only when the branch validation passes and the state machine behaves as specified. Enabling a real pre-production environment and later production promotion are separate implementation goals.

## 23. Autonomous Execution Eligibility and Owner Review

This pilot grants no production authority. Any future change that enables `production_transition_enabled=true`, changes deployment topology, or makes automatic production execution possible is a material protected-core change requiring its own review and acceptance evidence.

## Support-first priority rule

Support List items represent known deficiencies in behavior Jason is already expected to provide. They therefore outrank future enhancements.

The scheduler rule is:

1. production incident / active broken production state;
2. open Support List repair;
3. release-blocking defect;
4. already Production Eligible release work;
5. TODO / feature enhancement;
6. cleanup.

The existing support-repair limit remains bounded. When fewer than the configured maximum Support repairs are active and another actionable Support item exists, a new TODO/feature change may not consume that unused Support repair capacity. Once Support repair capacity is full, independent feature development may continue without displacing active Support work.
