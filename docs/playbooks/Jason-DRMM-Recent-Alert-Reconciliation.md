# Jason Playbook: DRMM Recent Alert Reconciliation

```yaml
playbook:
  id: drmm_recent_alert_reconciliation
  name: Jason - DRMM Recent Alert Reconciliation
  version: 1.0.0
  owner: AOT
  target_type: provider_object
  trigger:
    provider: Datto RMM
    match: currently-open alert whose provider timestamp is within the previous 24 hours
  ownership:
    while_open: conditional
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 0
  recheck:
    enabled: false
    cadence: 24 hours
    stale_after: not applicable
  verification:
    authoritative_source: registered alert-class verifier
    success_condition: exact triggering condition is proven absent from current device state
  completion:
    terminal_disposition: resolve exact DRMM alert and reconcile exact matching Autotask ticket
  autonomy:
    allowed_branches:
      - current-state reads
      - endpoint.alert.resolve after verified healthy state
      - exact matching Autotask internal note and completion
    approval_bound_branches: []
    disruptive_branches: []
```

## 1. Section Goal

Once per day, evaluate only currently-open Datto RMM alerts from the previous 24 hours. For alert classes with an explicitly registered authoritative verifier, prove the current endpoint state. If the original unhealthy condition is demonstrably absent, resolve the exact alert, require provider readback, and reconcile the exact linked Autotask ticket. Never use alert age by itself as closure evidence.

Success requires both positive and negative acceptance: a proven recovered alert can be closed, while an offline, still-unhealthy, unsupported, or inconclusive alert is not mutated.

## 2. Trigger

- Scheduled runtime maintenance cadence: 24 hours.
- Rolling provider timestamp lookback: 24 hours.
- Datto RMM `status=open` only.
- Alerts older than the lookback are discarded locally before endpoint verification.
- Historical backlog cleanup is explicitly out of scope.

## 3. Scope and Boundaries

### In scope
- recent open Datto RMM alerts;
- exact alert/device identity;
- registered current-state verifier;
- exact alert resolution;
- exact linked Autotask ticket reconciliation.

### Out of scope
- historical alert cleanup;
- remediation of the underlying endpoint condition;
- reboot/service restart/software modification;
- monitor suppression or policy changes;
- unsupported alert classes;
- guesses based on age or prior response-component execution.

Preserve Central Orchestrator authority and `direct_provider_access=false`.

## 4. Initial Identification

Require exact alert UID and DRMM device UID. If either is absent, classify inconclusive and do not mutate. Ticket reconciliation requires the exact `ticketNumber` carried by the alert.

## 5. Expected State

Healthy state is verifier-specific. Version 1.0 registers `endpoint_security_threat_ctx` only:
- endpoint is currently online;
- Datto AV is enabled, connected, and engine-ready;
- EDR identity resolves to an exact agent;
- current non-archived detection search returns zero active detections.

## 6. State Model

`scheduled -> recent_open -> supported | unsupported -> verifying -> healthy | unhealthy | waiting | inconclusive -> resolving -> provider_verified -> ticket_reconciled -> complete`

The daily last-completed timestamp and summary are durable in SQLite so runtime restarts do not cause duplicate daily passes.

## 7. Diagnostic Workflow

1. Read all currently-open DRMM alerts.
2. Discard alerts outside the rolling 24-hour window.
3. Select a registered verifier by alert class.
4. Run authoritative current-state reads.
5. Classify healthy, unhealthy, waiting, unsupported, or inconclusive.
6. Only `healthy` may proceed to mutation.

## 8. Decision Gates

Before alert resolution require:
- alert timestamp in current 24-hour window;
- exact alert UID;
- exact DRMM device UID;
- registered verifier;
- authoritative reads succeed;
- current healthy state proven;
- exact durable owner promotion for the reconciliation playbook.

## 9. Remediation

This playbook performs no endpoint remediation. The only provider mutation is `endpoint.alert.resolve` for the exact verified alert. If an exact linked Autotask ticket remains open, Jason writes one internal resolution note and sets it Complete after alert-resolution readback.

## 10. Retry Policy

No blind mutation retries. A failed resolution or failed readback is inconclusive and remains open for later/human handling.

## 11. Periodic Rechecks

Not applicable within a run. The next scheduled sweep is the normal recheck. Offline endpoints are left untouched.

## 12. Aging / Stale Condition

Not applicable to the daily sweep. Alerts older than 24 hours are outside scope and are not walked historically.

## 13. Dependency Handling

Unsupported alert classes are counted and skipped. New classes require an explicit authoritative verifier and acceptance tests before autonomous resolution is enabled for that class.

## 14. Documentation Requirements

For a linked ticket that is reconciled, record status, no-technician-action-required, exact alert UID/device, authoritative healthy evidence, exact provider resolution/readback, and explicitly state that no endpoint remediation or disruptive action occurred.

## 15. Failure Handling

Fail closed on provider/read failure, endpoint offline, unresolved identity, active detections, unhealthy security engine, unsupported alert class, or failed resolution readback.

## 16. Autotask Reconciliation

Only reconcile the exact `ticketNumber` carried by the resolved alert. Do not search by fuzzy title/device match. If the ticket is already complete, no duplicate mutation is needed.

## 17. Required Capabilities

Reads: `management.alert.search`, `endpoint.device.read`, `endpoint.security.status.read`, `endpoint.security.detection.search`, `endpoint.alert.history.search`, `service.ticket.search`, `service.ticket.read`.

Actions: `endpoint.alert.resolve`, `service.ticket.note.create`, `service.ticket.update`.

## 18. Acceptance Test

Required cases: older-than-24-hours ignored; unsupported alert skipped; active detection refuses closure; offline endpoint waits; healthy security alert resolves exact provider alert and reconciles exact linked ticket; durable scheduler does not rerun before 24 hours.

## 19. Completion / Section Goal Closure

Production-ready when tests pass, exact playbook autonomy promotion exists, runtime is enabled with 24-hour cadence/lookback, and a controlled production pass demonstrates fail-closed behavior plus at least one verified positive closure when a qualifying alert exists.
