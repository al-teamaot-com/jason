# Jason Playbook: Windows HOSTS File Drift

Status: Draft reference playbook v0.1.0. Not enabled for production execution.

## 1. Section Goal

**Goal:** Process a Windows HOSTS-file drift ticket from exact ticket/device identification through evidence-backed benign/threat classification, governed remediation or escalation, authoritative verification, and documented completion.

**Success means:**
- the exact client and endpoint are bound without ambiguity;
- the changed HOSTS entries are captured through governed evidence;
- benign, suspicious, threat, and inconclusive outcomes are distinguished without assuming the alert proves compromise;
- modifying/disruptive actions remain separately governed;
- the run survives rechecks/restarts without repeating completed work; and
- the final outcome is verified and documented.

## 2. Trigger

Applies when an Autotask/DRMM monitoring ticket or alert explicitly reports Windows HOSTS-file drift/change for a managed endpoint and the ticket/company/device can be deterministically resolved.

## 3. Scope and Boundaries

### In Scope
- Autotask ticket/company/configuration context;
- DRMM endpoint/alert context;
- governed read-only inspection of HOSTS contents or drift evidence;
- approved documentation/exception evidence;
- AI-assisted threat/benign decision support using only governed evidence;
- separately authorized remediation and alert/ticket lifecycle actions.

### Out of Scope
- cross-client evidence;
- arbitrary shell/provider bypass;
- declaring compromise from a drift alert alone;
- deleting an entry solely because it is unfamiliar;
- disruptive actions without instance-specific approval.

Preserve `direct_provider_access=false`, Central Orchestrator authority, exact grants, provider/client isolation, audit trail, and existing approval rules.

## 4. Initial Identification

1. Resolve the exact Autotask ticket.
2. Derive the company boundary from the ticket.
3. Resolve the exact DRMM endpoint and active Autotask CI using the hardened ticket/device correlation rules.
4. Resolve the exact originating monitor/alert where available.
5. Record timestamps and provider correlation IDs.

Ambiguity -> `state = blocked` or escalation; never guess.

## 5. Expected State

The HOSTS file contains only operating-system defaults plus entries supported by an AOT/client-approved durable exception or authoritative application requirement. A non-default entry is not automatically malicious.

## 6. State Model

Uses the generic persisted states:

`triggered -> identifying -> diagnosing -> deciding -> awaiting_approval -> remediating -> verifying -> complete`

Side states: `waiting`, `recheck_pending`, `blocked`, `escalated`, `cancelled`.

## 7. Diagnostic Workflow

### Step 1: Capture drift evidence

**Purpose:** Determine exactly what changed.

**Evidence source:** DRMM endpoint/monitor plus governed read-only endpoint diagnostic.

**Command/read/component:** Exact read-only HOSTS inspection capability/component to be selected and production-proven before activation.

**Expected result:** Current HOSTS contents/diff plus authoritative endpoint identity.

### Step 2: Correlate exception/documentation evidence

Search same-client approved documentation, ticket history, and Resolution Memory for a durable explanation of the specific entry/pattern. Historical evidence informs classification but grants no action authority.

### Step 3: AI-assisted security classification

Use a registered/versioned security-triage prompt once implemented. Required structured output: classification, confidence, threat evidence, benign evidence, missing evidence, recommended next evidence/action, and human-review requirement.

Permitted classifications: `benign`, `likely_benign`, `suspicious`, `likely_threat`, `confirmed_threat`, `inconclusive`.

### Decision

- documented/verified benign -> verify expected exception state and resolve appropriately;
- suspicious/inconclusive -> gather more evidence or escalate;
- likely/confirmed threat -> branch to governed security-response workflow;
- unauthorized but non-threat configuration drift -> propose bounded remediation.

## 8. Decision Gates

Before remediation require:
- exact ticket/company/device/CI binding;
- current authoritative HOSTS evidence;
- exception/documentation search completed;
- classification not inconclusive;
- exact proposed change identified;
- requester/action authority satisfied;
- rollback/restoration path defined.

## 9. Remediation

**Action:** Remove/restore only the exact unauthorized HOSTS drift identified by evidence.

**Approval classification:** modifying; approval-required during pilot. Reboot remains disruptive and separately approval-required if ever needed.

**Verification required:** re-read HOSTS and verify the originating monitor/condition is healthy. Provider job success alone is insufficient.

## 10. Retry Policy

Maximum full remediation attempts: `2`. No blind repeat. A second attempt requires evidence that retrying is reasonable. Then escalate.

## 11. Periodic Rechecks

If endpoint is offline or evidence is temporarily unavailable, persist `recheck_pending`. Initial pilot recheck cadence should be bounded and scheduled through Jason's governed automation layer. Do not create duplicate rechecks for one run.

## 12. Aging / Stale Condition

Persistent offline/unreachable or repeated drift should trigger investigation for stale/retired/renamed endpoints, repeated application rewrite, policy conflict, or active security concern rather than indefinite retries.

## 13. Dependency Handling

If required exception documentation, diagnostic capability, or provider evidence is unavailable, verify the dependency, search for existing related work, create/cross-reference only when authorized, and put the run into `blocked`. Never borrow data from another client.

## 14. Documentation Requirements

Document meaningful identification, diagnostic, decision, approval, remediation, verification, failure, and escalation steps in the authoritative case/ticket. Include exact command/read/component, target, timestamp, result, provider job/correlation IDs, interpretation, and next decision. Never document secrets.

## 15. Failure Handling

Read failure, ambiguous endpoint, unavailable output, contradictory evidence, authority denial, or remediation failure must be recorded and must not silently advance the run.

## 16. Escalation Criteria

Escalate for unresolved identity, conflicting evidence, inconclusive security classification after bounded evidence collection, required disruptive action without approval, failed remediation limit, repeated drift, or evidence indicating a broader security incident.

## 17. Verification

Resolution requires authoritative current HOSTS state plus healthy/cleared monitoring evidence. A component/job returning success is not enough.

## 18. Completion Criteria

Complete only when exact object identity, diagnostics, classification/root cause, authorized remediation where needed, authoritative verification, and final documentation are all present.

## 19. Final Resolution Note

Summarize original drift, classification/root cause, device/client state, diagnostics, remediation/exception, attempts, final verification, verification timestamp, and disposition.

## 20. Required Capabilities

- Autotask ticket/company/configuration reads;
- ticket work-start lifecycle and internal notes;
- DRMM endpoint/alert reads;
- exact read-only HOSTS diagnostic capability/component;
- IT Glue/same-client exception evidence when authorized;
- Resolution Memory search;
- registered AI threat/benign triage prompt;
- persisted generic PlaybookRun state;
- governed scheduled recheck support;
- modifying HOSTS remediation capability (pilot approval-required);
- DRMM alert resolution and Autotask completion after verification.

Missing exact HOSTS read/remediation capabilities remain implementation gates, not assumptions.

## 21. Acceptance Test

**Test target:** Synthetic generic-runtime run first; later one controlled real HOSTS-drift ticket/device selected by the Owner.

Prove trigger detection, exact binding, documentation, diagnostics, AI classification, decision gates, approval binding, recheck behavior, bounded remediation, failure handling, verification, completion/escalation, scheduled-job cleanup, and persisted state. Do not modify unrelated production objects.

## 22. Section Goal Closure

Close only after implementation evidence, capability additions, controlled live test results, known limitations, Grafana live-run telemetry, and follow-up TODOs are documented. The draft remains disabled until those acceptance conditions are met.
