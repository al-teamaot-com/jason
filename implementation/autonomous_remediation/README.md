# Governed Autonomous Remediation Framework

Jason may progress from triage to remediation only through deterministic policy, explicit authorization, verifiable evidence, and auditable execution.

## Constitutional principle

> Jason shall earn autonomy rather than assume it. Every autonomous action must be supported by evidence, governed by policy, verified after execution, fully auditable, and continuously evaluated. Automation is promoted through demonstrated success and human approval, not confidence alone.

## End-to-end flow

```text
Autotask ticket
  -> Triage Intelligence assessment
  -> proposed remediation plan
  -> policy and authorization evaluation
  -> approval when required
  -> orchestrator invokes approved DRMM capability
  -> execution evidence captured
  -> post-change verification
  -> Autotask ticket updated with structured log
  -> client follow-up requested through Communication Broker
  -> outcome and client confirmation recorded
  -> automation performance metrics updated
```

Agents never invoke Datto RMM, Autotask, communications, or other agents directly. They return structured requests to the central orchestrator, which performs routing, policy checks, approvals, execution, retries, timeouts, audit logging, and final response assembly.

## Autonomy levels

- `observe`: gather evidence only.
- `recommend`: create a proposed remediation plan for technician review.
- `approved_execute`: execute only after a named human approval.
- `low_risk_autonomous`: execute a pre-approved, narrowly scoped capability automatically.
- `prohibited`: no automated execution is permitted.

Confidence alone never determines autonomy. The policy decision also considers action risk, device role, client authorization, maintenance window, reversibility, blast radius, evidence quality, prior success, and required approvals.

## Initial production boundary

The first implementation remains `recommend` or `approved_execute` only. It must not automatically close tickets or declare success without post-change verification and client confirmation when user-visible behavior is involved.

## Required execution stages

1. **Assessment** — identify the likely cause and supporting evidence.
2. **Plan** — name the exact capability, target, expected result, verification method, rollback path, and timeout.
3. **Policy decision** — allow, require approval, or block.
4. **Execution** — invoke a registered capability through the orchestrator.
5. **Evidence capture** — preserve provider job IDs, timestamps, output, exit codes, and version changes.
6. **Verification** — prove the desired state was reached.
7. **Ticket update** — add a technician-readable summary plus the structured execution log.
8. **Client follow-up** — contact the approved recipient through the Communication Broker.
9. **Learning** — record success, failure, intervention, duration, rollback, and client confirmation.

## Safety requirements

- Fail closed when the client, device, authorization, or capability scope is ambiguous.
- Block cross-client evidence and actions.
- Require an idempotency key for every execution request.
- Prevent duplicate DRMM jobs for the same ticket, target, and plan version.
- Enforce timeouts, retry limits, and maintenance windows.
- Require an explicit rollback or escalation path before execution.
- Treat provider-reported success as unverified until an independent check passes.
- Preserve raw execution output centrally and pass artifacts by reference.
- Never expose secrets, credentials, or sensitive cross-client details in ticket notes or client communications.

## Jason - Datto EDR/AV Diagnose & Repair

The Datto EDR/AV playbook is the first named endpoint-security remediation state machine. It is implemented in `datto_edr_av_playbook.py` and is deliberately separate from provider connectors so runtime policy remains authoritative.

The successful terminal condition is only the authoritative health component returning `Status=Healthy`. A Datto job reporting `Completed`, a service appearing present, or a component returning exit code zero is evidence, not closure.

Normal repair order is bounded: health check, narrow service diagnostic when applicable, one EDR Maintenance attempt, one Force Reinstall/Upgrade attempt, one governed Datto AV force-update, then a 02:30 local scheduled reboot with 03:30 verification when the repair requires reboot or an AV update appears hung. After the scheduled reboot, one additional AV force-update may be attempted. The playbook never loops a failed remediation indefinitely.

Within this named workflow, the standard 02:30 local reboot is a standing-safe playbook action. Immediate reboot remains approval-required. The deeper clean recovery branch remains policy-gated during the supervised pilot: clean uninstall, scheduled recovery reboot, base Maintenance, one recovery Force Reinstall/Upgrade, one recovery AV force-update, and authoritative verification. If that bounded sequence cannot reach `Status=Healthy`, Jason escalates.

Every dispatch receives a deterministic idempotency key. A failed read, poll, or StdOut retrieval causes another read of the same provider job and never authorizes a second remediation dispatch. The playbook preserves provider job IDs and evidence references for escalation while keeping routine Autotask internal notes brief.

Autotask updates are internal-only milestones: initial diagnosis/remediation start when useful, scheduled reboot pending, resolved, or escalated. Poll-by-poll detail and long StdOut remain in central audit/evidence storage rather than being copied into the ticket.

The playbook exports a stable metrics payload for Jason/Grafana containing version, terminal state, attempt count, reboot use, clean-recovery use, and success/escalation status. It also exports an escalation payload containing the target device, ticket, job IDs, attempted steps, EDR version, HUNTAgent path/status, AV/service/WSC state, evidence references, and reasons without exposing registration secrets or tokens.

No device execution is part of source implementation or unit testing. A live pilot must be started separately against an explicitly selected endpoint after source review and deployment.

## Initial pilot scenario

A ticket reports a QuickBooks problem. Jason correlates the installed version from DRMM with authoritative vendor intelligence and prior AOT resolutions. It proposes an approved QuickBooks update capability. After technician approval, the orchestrator triggers the DRMM component, captures its job output, verifies the installed version and service health, updates the Autotask ticket, and asks the client to confirm the original symptom is resolved.

## Promotion process

A remediation workflow may be proposed for higher autonomy only after a defined observation period and minimum execution count. Promotion requires human approval and documented thresholds for success rate, rollback rate, technician intervention, client impact, evidence quality, and retirement criteria. Jason may recommend promotion but may never approve its own promotion.
