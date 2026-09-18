# Jason Playbook: Datto EDR/AV Diagnose & Repair

Version: 1.2.0
Playbook ID: `datto_edr_av`
Status: v1.2 governed read backend and playbook observability are deployed and production-accepted through Jason. All six `endpoint.security.*` reads are live and proven against AOT-50282; Prometheus and Grafana expose the pilot state and acceptance telemetry. The playbook remains in supervised pilot/read-ready state; full threat-branch activation remains fail-closed pending governed provider-native scan execution and a complete remediation/scan/recurrence acceptance run.

## 1. Section Goal

**Goal:** Allow Jason to identify, diagnose, repair, verify, document, and appropriately escalate Datto EDR/AV endpoint-security issues without conflating product health, configuration problems, security detections, malicious artifacts, or endpoint compromise.

**Success means:**
- the correct ticket/client/device is resolved and associated;
- product health and security-event state are evaluated independently;
- Datto documentation and Datto API evidence are authoritative for Datto product semantics;
- bounded, governed remediation is performed only when justified;
- threat-triggered runs cannot close solely because the EDR/AV stack is healthy;
- every meaningful action/result is documented;
- playbook outcomes are measured in Grafana for continuous improvement.

## 2. Trigger

This playbook may start from Autotask/DRMM EDR or AV alerts, Datto EDR/AV detections/webhooks, or a technician request for a named endpoint.

At intake classify the run as exactly one of:
- `health_only`
- `threat_only`
- `health_and_threat`

An alert is evidence requiring evaluation. It is not, by itself, proof of compromise.

## 3. Scope and Boundaries

### In Scope
- Autotask ticket/device correlation;
- Datto RMM endpoint identification and governed reads;
- Datto EDR/AV API reads;
- Datto EDR/AV alert/detection evidence;
- EDR/AV policy and status evidence;
- approved DRMM diagnostic/remediation components;
- approved Datto AV quick/full scans when warranted;
- approved second-opinion scanning when warranted;
- internal ticket documentation;
- Grafana playbook telemetry.

### Out of Scope
- declaring compromise from agent health, Windows Security status, or one uninvestigated alert;
- arbitrary PowerShell or shell execution;
- autonomous AV exclusions/allowlisting;
- autonomous disruptive containment;
- direct provider access outside Jason governance;
- unrelated endpoints/tickets;
- unbounded retry loops.

Preserve `direct_provider_access=false`, Central Orchestrator authority, exact requester grants, client isolation, evidence/audit logging, and disruption controls.

## 4. Initial Identification

Before troubleshooting:
1. Resolve the exact Autotask ticket.
2. Resolve the client/organization.
3. Extract the device selector from ticket/alert evidence.
4. Resolve the exact DRMM device UID; never choose the first ambiguous match.
5. Associate the ticket to the device/CI when available.
6. Resolve the corresponding Datto EDR/AV endpoint using durable provider mapping.
7. Record trigger timestamp, alert IDs, correlation IDs, and relevant provider IDs.

If identity remains ambiguous: `state=identification_blocked`; document and escalate.

## 5. Expected State

### SecurityStackHealthy
Expected evidence includes:
- endpoint reachable/checking in;
- HUNTAgent installed/running as expected;
- EDR agent current/registered;
- Datto AV present when required by client policy;
- AV engine/signature state current;
- expected AV/EDR policy assigned;
- real-time protection state consistent with assigned policy;
- no unresolved registration/tamper/license condition;
- authoritative AOT health component reports `Status=Healthy`.

### ThreatResolved
For threat-triggered runs:
- originating Datto detection has an authoritative final disposition;
- no unresolved malicious finding remains;
- the verification scan record is completed and read;
- a post-scan governed detection search shows no unresolved/new matching threat evidence;
- configured recurrence check has passed;
- security stack remains healthy.

`SecurityStackHealthy=true` does not imply `ThreatResolved=true`.

## 6. State Model

Persisted playbook states include:
- `new`, `diagnosing`, `repairing`, `verifying`
- `awaiting_approval`, `awaiting_scheduled_reboot`
- `awaiting_security_verification`
- `threat_investigation`, `threat_contained`
- `false_positive_review`
- `healthy`, `escalation_required`

Security disposition is separately persisted:
- `not_applicable`
- `no_detection`
- `detection_under_investigation`
- `malicious_artifact_contained`
- `false_positive_review`
- `resolved`
- `security_incident_escalation`

Compromise signal is separately persisted:
- `not_established`
- `provider_indicated`
- `corroborated_execution`

Contained detection state distinguishes `detection_contained` from
`malicious_artifact_contained`. Datto quarantine evidence can establish
containment without establishing that the endpoint is compromised or that the
provider explicitly classified the artifact as malicious.

Datto provider metadata `compromised=true` is recorded as `provider_indicated`; Jason does not silently rename it independent proof.

## 7. Diagnostic Workflow

### Step 1: Ticket/device/context
Resolve exact ticket, client, device UID, current user if relevant, related alerts, and known exceptions.

### Step 2: Authoritative product-health component
Run `Check Datto EDR/AV Status AOT Ver 12122025-1`.

Do not interpret a single Windows service state as the whole product state.

### Step 3: Datto EDR/AV API evidence
Using governed API reads, collect when available:
- EDR/AV endpoint IDs/mapping;
- agent/status/version;
- AV engine version and VDF version;
- assigned policies;
- recent scan history;
- alerts/detections;
- quarantine/disposition;
- isolation state.

Use the tenant LoopBack API Explorer as authority for actual entities, operations, models, parameters, and responses.

### Step 4: Classify the condition
Classify separately as:
- protection-health issue;
- policy/configuration issue;
- security detection under investigation;
- malicious artifact contained;
- false-positive review;
- provider-indicated/corroborated security incident.

A stale definition, stopped/missing agent, failed scan, or Windows Security warning is not compromise evidence.

### Step 5: Narrow service diagnostics
When appropriate use `Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1`.

Datto documents `HUNTAgent` as the EDR agent service for service monitoring. Do not assume `EndpointProtectionService=Stopped` independently proves Datto AV failure.

### Step 6: Security detection detail
For threat-triggered runs persist the narrowest authoritative evidence available:
- alert/detection ID;
- threat name/severity;
- malicious/non-malicious/suspicious flags;
- quarantine/block state;
- provider `compromised` signal;
- process/parent process;
- command line in secure evidence storage;
- SHA256;
- original path;
- user;
- timestamps;
- recurrence.

## 8. Decision Gates

Before remediation confirm:
- exact endpoint identity;
- endpoint is reachable enough to verify;
- action matches the current branch;
- no conflicting job is already running;
- required component/capability exists;
- current policy/expected state is known;
- no documented client exception explains the condition;
- disruptive action has explicit approval for that instance.

Threat branch preflight must confirm the required EDR API reads. Missing evidence means Jason cannot claim full threat resolution.

## 9. Remediation

Normal bounded health-repair order:
1. authoritative health check;
2. narrow service diagnostic when indicated;
3. `Datto EDR Maintenance [WIN]`;
4. authoritative verification;
5. `Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024` when still required;
6. authoritative verification;
7. one governed Datto AV force update using `agent.exe datto-av --force-update`;
8. authoritative verification;
9. scheduled reboot only when required/authorized;
10. post-reboot verification;
11. policy-gated clean recovery only after normal paths are exhausted.

The force-update binding permits only the fixed approved operation; callers cannot supply arbitrary PowerShell.

### Threat branch
`read threat -> verify stack -> scan -> governed remediation/quarantine if appropriate -> rescan -> reread threat -> recurrence check -> verify stack -> resolve/escalate`

If Datto already blocked/quarantined an object, verify that disposition rather than repeating cleanup unnecessarily.

## 10. Retry Policy

- Each repair step: maximum one normal attempt unless explicitly defined otherwise.
- One additional AV refresh may occur after the approved scheduled reboot.
- Read/poll/output failures retry the same read and never authorize redispatch.
- Failed AV scan may be retried when Datto-documented transient causes are plausible.
- Repeated AV scan failures (three or more) escalate per Datto guidance.
- No endless remediation loops.

## 11. Periodic Rechecks

For waits/reboots:
- scheduled reboot default: 02:30 local;
- post-reboot verification: 03:30 local;
- threat recurrence window must be explicit by severity/policy;
- prevent duplicate scheduled jobs.

Threat runs re-read the originating detection after remediation and at the configured recurrence boundary.

## 12. Aging / Stale Condition

Do not wait indefinitely for offline devices, stale EDR records, ambiguous mapping, scans that never complete, provider jobs with no terminal state, or threat dispositions that cannot be read. These become explicit escalation conditions.

## 13. Dependency Handling

Dependencies include:
- Datto EDR/AV API token;
- API entity/capability discovery;
- expected client policy;
- licensing;
- documented exceptions;
- required components;
- Autotask write capability;
- scan execute/read capability.

Tokens must be stored through Jason's secrets path and never logged. Datto API tokens currently expire one year after creation.

## 14. Documentation Requirements

Document every meaningful step:
- operation/component/scan;
- target;
- timestamp;
- job/correlation ID;
- result/output summary;
- interpretation;
- SecurityStackHealthy state;
- security disposition;
- next decision.

Never copy secrets, tokens, unnecessary raw threat artifacts, or sensitive command-line data into ticket notes.

## 15. Failure Handling

Explicitly document provider/API failures, ambiguous mapping, component failure, missing output, scan failure, conflicting evidence, missing license/policy, denied authority, service/engine disconnect, and recurrence after remediation.

Missing evidence never becomes a healthy/clean conclusion.

## 16. Escalation Criteria

Escalate when:
- endpoint identity cannot be established;
- tamper/registration blocks safe repair;
- bounded repair is exhausted;
- AV scans repeatedly fail;
- provider indicates `compromised=true`;
- malicious execution is explicitly corroborated;
- ransomware, credential theft, persistence, lateral movement, or repeated execution is indicated;
- disruptive isolation/containment is required;
- detection remains ambiguous;
- required API/scan evidence is unavailable;
- material evidence conflicts.

Endpoint/network isolation remains disruptive and requires explicit technician approval unless separately governed.

## 17. Verification

### Health-only
Required:
- authoritative health component = `Status=Healthy`;
- policy/API state consistent;
- if AV protection was repaired or unavailable, approved verification scan when supported;
- scan record read, not merely job completion; Datto `ScanHistoryTracking` does not itself expose a zero-findings result, so clean verification additionally requires a post-scan detection search with no unresolved/new matching evidence.

### Threat-triggered
Required:
- SecurityStackHealthy = true;
- originating threat authoritatively resolved/contained;
- post-remediation scan completed/read and composite clean verification established by a clear post-scan detection search;
- no matching recurrence during required check;
- required documentation succeeded.

A failed scan is not proof of malware. Datto documents transient causes including another scan/update, engine disconnect, agent restart/update, low disk, and permissions.

## 18. Completion Criteria

### Health-only ticket
Complete only after correct endpoint identification, health classification, required repair, `Status=Healthy`, applicable scan verification, and documentation.

### Threat-triggered ticket
Complete only when:
1. correct endpoint/detection identified;
2. `SecurityStackHealthy=true`;
3. `ThreatResolved=true`;
4. the verification scan record is completed/read and the post-scan detection check is clear;
5. recurrence check passed;
6. required ticket documentation succeeded.

## 19. Final Resolution Note

Include original trigger, health/configuration root cause if established, threat/detection ID when applicable, diagnostics, remediation, attempt count, scan type/result, final Datto disposition, final EDR/AV health, recurrence verification, and final classification.

Avoid wording such as "machine was compromised" unless the incident record contains explicit supporting evidence.

## 20. Required Capabilities

Existing capabilities include Autotask reads/writes, DRMM endpoint/alert reads, component execution, job/output reads, persisted state, and scheduled rechecks.

Endpoint-security API capabilities:
- `endpoint.security.status.read`
- `endpoint.security.detection.search`
- `endpoint.security.detection.read`
- `endpoint.security.policy.read`
- `endpoint.security.scan.history.search`
- `endpoint.security.quarantine.search`
- `endpoint.security.scan.execute`

Exact Datto API entities remain inside the connector and must be discovered from the tenant LoopBack Explorer rather than guessed.

## 21. Acceptance Test

Controlled target pattern:
- AOT-50282
- T20260918.0005

Prove exact association, trigger classification, health check, API evidence, health/threat separation, no compromise inference from misconfiguration, no threat closure from `Status=Healthy` alone, bounded remediation, scan execution/read, threat reread/recurrence, ticket documentation, terminal disposition, telemetry event, Grafana metrics, and duplicate-job prevention.

No live acceptance execution is authorized by this document alone.

## 22. Section Goal Closure

Close only after code/tests pass, EDR API connector/token is governed and available, controlled acceptance succeeds, telemetry reaches Prometheus/Grafana, limitations are documented, source is committed/pushed, and Grafana reflects the playbook/version/status.

## 23. Datto Documentation Authority

Primary technical references:
- Admin/API index: https://edr.datto.com/help/Content/09-navigating-admin-options/admin-option-intro.htm
- LoopBack API Explorer: https://edr.datto.com/help/Content/09-navigating-admin-options/api-loopback-explorer.html
- API tokens: https://edr.datto.com/help/Content/09-navigating-admin-options/api-generate-token.htm
- Webhooks/alert metadata: https://edr.datto.com/help/Content/09-navigating-admin-options/api-create-webhooks.htm
- Alerts: https://edr.datto.com/help/Content/05-investigating-responding-to-alerts/page-alerts.htm
- Alert details: https://edr.datto.com/help/Content/05-investigating-responding-to-alerts/page-alert-detail.htm
- Device details: https://edr.datto.com/help/Content/02-managing-organizations-locations-devices/page-device-details.htm
- Datto AV: https://edr.datto.com/help/Content/01-getting-started/what-is-datto-av.htm
- AV policy best practices: https://edr.datto.com/help/Content/04-configuring-assigning-policies/datto-av-policy/av-policies-best-practices.htm
- Alert Only behavior: https://edr.datto.com/help/Content/04-configuring-assigning-policies/datto-av-policy/configuring-datto-av-alert-only-mode.htm
- Service monitoring: https://edr.datto.com/help/Content/troubleshooting/service-monitoring.htm
- Failed AV scan diagnosis: https://edr.datto.com/help/Content/troubleshooting/diagnose-failed-datto-av-scan.htm
- Tasks: https://edr.datto.com/help/Content/09-navigating-admin-options/page-tasks.htm

When AOT observations or scripts conflict with Datto product semantics, review current Datto documentation/API evidence before changing the playbook.
