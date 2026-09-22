# Jason Standard Playbook Template

Use this as the default structure for every new Project Jason operational playbook. Preserve the sections; when one truly does not apply, mark it `Not applicable` instead of silently changing the standard.

## 1. Section Goal

Define exactly what Jason should be able to accomplish and the criteria that prove success. Do not close the Section Goal until acceptance criteria have been demonstrated and documented.

## 2. Trigger

Define exactly when the playbook applies: ticket-title pattern, alert type, queue, provider event, device/site condition, or other deterministic trigger. Confirm the trigger before starting.

## 3. Scope and Boundaries

Define in-scope systems, objects, diagnostics, and remediation. Define exclusions. Preserve Central Orchestrator authority, exact requester grants, provider/client isolation, approval rules, audit trail, and `direct_provider_access=false`.

## 4. Initial Identification

Identify the exact ticket/triggering object, client, affected asset/device/user, authoritative provider object, relevant IDs/timestamps, and any duplicate/stale/mismatched objects. If identity is uncertain, use `state = identification_blocked`, document, and escalate rather than guessing.

## 5. Expected State

Define the healthy target condition before remediation: required software/service/policy/configuration/status, expected backup/monitoring behavior, or equivalent.

## 6. State Model

Define explicit persisted states. Suggested base flow:

`identified -> waiting -> diagnosing -> blocked -> remediating -> verifying -> complete`

or `escalated`.

Add playbook-specific states as needed. State should survive rechecks, conversation boundaries, handoffs, and service restarts where practical.

## 7. Diagnostic Workflow

For every diagnostic step record:

- Purpose: what question the step answers.
- Evidence source: Autotask, DRMM, IT Glue, Entra, provider, etc.
- Exact read/command/component when known.
- Expected healthy result.
- Decision branches and next state/action.

Do not infer root cause solely from an alert when authoritative evidence can verify it.

## 8. Decision Gates

Define mandatory preconditions before remediation, such as endpoint identity, online/availability window, confirmed unhealthy state, required configuration/variable/license, maintenance conflicts, and requester authority. Do not bypass failed gates.

## 9. Remediation

For each remediation define:

- exact action/component
- preconditions
- authority classification: read-only / non-destructive / modifying / disruptive
- required verification

Job submission is not success. Verify terminal completion and retrieve actual output where available.

## 10. Retry Policy

Use bounded retries. Define maximum full attempts and when another attempt is justified. Document each attempt. When the limit is reached, transition to `escalated`; never create endless loops.

## 11. Periodic Rechecks

When waiting is required, define recheck interval, recheck condition, stop conditions, and duplicate-scheduled-job suppression. Stop rechecks after completion, escalation, closed ticket, stale/retired condition, or other terminal state.

## 12. Aging / Stale Condition

Define when waiting becomes abnormal and requires investigation of retirement, replacement, stale/duplicate objects, rename/reimage, or broader connectivity/management problems. Do not retry indefinitely.

## 13. Dependency Handling

For missing configuration, credentials, variables, licensing, documentation, or another team's work:

1. Confirm the dependency is missing.
2. Search for an existing open dependency ticket.
3. Suppress duplicates.
4. Create one only if authorized and needed.
5. Cross-reference it.
6. Put the original workflow into `state = blocked` when appropriate.

Never fabricate or borrow client-specific configuration.

## 14. Documentation Requirements

Document every meaningful step in the authoritative ticket/case when one exists. Include:

- what was checked and why
- exact command/read/component
- target and timestamp
- result
- job/correlation ID where available
- relevant StdOut/StdErr or sanitized summary
- interpretation
- resulting decision
- next step

Suggested note titles:

- `Jason - [Playbook] - Asset Validation`
- `Jason - [Playbook] - Diagnostic`
- `Jason - [Playbook] - Recheck`
- `Jason - [Playbook] - Remediation`
- `Jason - [Playbook] - Verification`
- `Jason - [Playbook] - Escalation`
- `Jason - [Playbook] - Resolution`

Never document passwords, API keys, tokens, private keys, or secret variable values. Presence/status may be documented when appropriate.

## 15. Failure Handling

Document failed reads, unmatched objects, component failures, missing output, timeout, missing dependencies, contradictory evidence, or denied authority as carefully as successes. Do not silently skip failures.

## 16. Escalation Criteria

Define exact automatic-stop conditions: retry limit, disruptive action required, unresolved identity, unavailable dependency, unexpected provider result, repeated service failure, conflicting evidence, or out-of-scope issue. The escalation note should summarize symptoms, evidence, diagnostics, attempts/results, current state, and recommended next step.

## 17. Verification

Define authoritative resolution evidence. Examples: successful backup, cleared alert, healthy service, agent reporting, user confirmation, event no longer recurring, or monitoring returned healthy. Do not close solely because a command/component succeeded.

## 18. Completion Criteria

Complete only when the correct object is identified, required diagnostics are done, root cause/resolution classification is established, required remediation succeeded, authoritative healthy-state evidence exists, all work is documented, and the final resolution note exists.

## 19. Final Resolution Note

Summarize original condition, root cause, relevant environment state, diagnostics, remediation, number of attempts, final verification and timestamp, and disposition.

## 20. Required Capabilities

List the narrowest Jason capabilities required, such as Autotask ticket read/write/note/create, DRMM endpoint/software/service/component/job/output access, IT Glue reads, scheduler/recheck support, and persisted state. Do not broaden capabilities for convenience.

## 21. Acceptance Test

Define a controlled real-world or safe test target. Prove trigger detection, object association, documentation, diagnostics, gates, recheck/wait behavior, remediation, retry limits, failure handling, verification, completion/escalation, scheduled-job cleanup, and persisted state. Do not modify unrelated production objects.

## 22. Section Goal Closure

When acceptance succeeds, document implementation, capability additions, test results, limitations, Grafana/Project Jason Section Goal status, and any unresolved follow-up TODOs.


## 23. Autonomous Execution Eligibility

Every playbook must explicitly declare whether it is eligible for autonomous execution. Absence of an explicit approval means the playbook is **not** autonomous.

Required metadata:

- `autonomous_allowed: true|false`
- approval owner and approval date
- approved playbook/version or immutable content fingerprint
- allowed trigger/scope
- allowed actions/capabilities
- actions that still require per-run approval
- revocation/expiry condition where applicable

Rules:

1. Global autonomy never grants new operational authority by itself.
2. Jason may autonomously execute only a playbook/version that has been explicitly approved for autonomous use and whose required capabilities remain active.
3. Material playbook changes invalidate prior autonomous approval until the changed version is reviewed.
4. Revocation must take effect before the next autonomous execution.
5. Ambiguous scope, missing evidence, unavailable dependency, denied capability, or stale approval causes fail-closed behavior.
6. User-disruptive actions remain approval-bound even when the surrounding playbook is autonomous. This includes reboot/shutdown, forced logoff, terminating user applications/processes, disconnecting network/VPN, restarting services that interrupt active work, and equivalent disruption.
7. Autonomous approval never bypasses Central Orchestrator authority, client isolation, audit, provider verification, post-action verification, retry limits, or playbook-specific safety gates.

Acceptance testing for an autonomous playbook must prove both paths: an approved autonomous execution succeeds within scope, and an unapproved/revoked/version-mismatched execution is blocked.
