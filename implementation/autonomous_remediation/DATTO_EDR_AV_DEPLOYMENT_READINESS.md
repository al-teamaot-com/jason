# Jason - Datto EDR/AV Diagnose & Repair - Deployment Readiness

Status: v1.2 source implementation, dedicated OpenBao credential boundary, governed read-only Datto EDR connector, live tenant read proof, and observability source validation passed; no Datto EDR provider mutation or endpoint remediation was performed by this work. Remaining activation gates are production runtime deployment, a governed scan-execute path, controlled acceptance proof, and live observability verification.

## Live Jason capability surface verified 2026-09-17

- `automation.component.execute` is active and action-enabled through the Central Orchestrator.
- `automation.job.read` is active and read-only.
- `automation.job.output.read` is active and read-only.
- `service.ticket.note.create` is an active write capability.
- `direct_provider_access=false` remains authoritative.

The live component-catalog search capability was not exposed in the latest MCP registry check, so current exact component identities are carried from the previously verified catalog evidence plus the Owner-confirmed generic PowerShell component used in the successful AOT-50282 repair.

## Exact Datto component identities used by the playbook

| Purpose | Datto component | UID |
| --- | --- | --- |
| Authoritative EDR/AV health | Check Datto EDR/AV Status AOT Ver 12122025-1 | `8cb0f063-5875-452e-88ad-2e1748ed0fd0` |
| Service diagnostic | Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1 | `2b49d490-bcae-4825-b31e-c4f1be881ae5` |
| EDR maintenance | Datto EDR Maintenance [WIN] | `3f069258-9b5e-4083-9b13-fa61c0fc0499` |
| EDR reinstall/upgrade | Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024 | `9c30dab8-b76c-417d-a264-b3ca91995179` |
| Datto AV force-update transport | Run Ad Hoc Command (PowerShell 2-5) [WIN] | `8a1c153c-feee-41c5-9c9b-58a48e0214fe` |
| Clean uninstall | Uninstall Datto EDR / AV AOT Ver 11052025-1 | `b1e523aa-6464-4eaf-b99d-0172649f2115` |
| Scheduled reboot | 230 AM Scheduled Reboot AOT Ver 11282024 | `a61ce810-84a6-435c-ba02-b589a6008f28` |

These identities are evidence for exact matching. They do not create general standing authority outside this named workflow.

## Proven Datto AV recovery behavior

The successful AOT-50282 repair established the AV-specific recovery behavior without requiring a manual `EndpointProtectionService` start.

Observed successful path:

`EDR Maintenance / repair -> EDR Force Reinstall -> active HUNTAgent agent.exe datto-av --force-update -> reboot -> authoritative health check -> Status=Healthy`

The command arguments were exactly:

`datto-av --force-update`

The Datto component used to run that command was:

`Run Ad Hoc Command (PowerShell 2-5) [WIN]`

Component UID:

`8a1c153c-feee-41c5-9c9b-58a48e0214fe`

The RMM-managed HUNTAgent path before the successful force-update was:

`C:\ProgramData\CentraStage\AEMAgent\RMM.AdvancedThreatDetection\agent.exe`

After the recovery/reboot sequence, HUNTAgent was observed at the alternate supported path:

`C:\Program Files\Infocyte\agent\agent.exe`

The runtime therefore does not permanently assume one path. For the AV force-update step it uses the ad-hoc PowerShell component with a server-generated fixed command that resolves the active `HUNTAgent` service executable, accepts only those two known Datto paths, and invokes only `datto-av --force-update`.

The caller cannot supply arbitrary PowerShell through this playbook binding. Any other predefined command fails closed.

The prior force-update job remained active unusually long and produced no StdOut. A second force-update was not launched. After reboot, the same authoritative EDR/AV health component changed from `Status=IssuesFound` / Datto AV not clearly detected to `Status=Healthy`.

Component completion still does not mean AV health. The playbook must rerun `Check Datto EDR/AV Status AOT Ver 12122025-1`, and only `Status=Healthy` closes the workflow successfully.

## Runtime blocker removed: AV command transport

A separate dedicated Datto AV component is not required. Per Owner direction and the proven AOT-50282 repair, the playbook binds the exact AV force-update operation to the existing `Run Ad Hoc Command (PowerShell 2-5) [WIN]` component.

The generic component itself is not granted broad autonomous command authority by this playbook. The runtime binding only permits the exact logical operation `agent.exe datto-av --force-update`, generates the PowerShell payload server-side, fixes the Datto component UID/name, fixes the `Command` variable, and rejects any other predefined command.

## Required playbook requirements for threat detection and AV-scan verification

The production playbook must distinguish **EDR/AV product health** from **security-incident resolution**. A healthy agent does not prove that a detected threat has been contained or removed.

### Trigger classification

At intake, classify the ticket/alert into one or both branches:

1. **Agent health / product repair** - EDR or AV is missing, stopped, stale, unhealthy, incorrectly registered, or otherwise not operating as expected.
2. **Threat detection / incident response** - Datto AV/EDR has reported a malware, threat-hunting, suspicious-process, or other security detection.

If both conditions exist, restore enough security-stack health to investigate safely, then continue through the threat-response branch. Do not close a threat-triggered incident solely because the EDR/AV health component returns `Status=Healthy`.

### Threat evidence collection

For a threat-triggered incident, Jason should retrieve and persist the narrowest available authoritative Datto threat evidence, including when available:

- Datto threat/alert ID
- detection/threat name and severity
- original file path
- SHA256 or other provider-reported hash
- process and parent-process context
- logged-on user
- first-seen and last-seen timestamps
- detection/trigger count
- provider action/disposition
- quarantine, blocked, cleaned, failed, or unresolved state
- recurrence after remediation

Evidence must be captured before any destructive cleanup when reasonably available. Secrets or credential material must never be written to ticket notes.

### Separate health and incident state

Persist separate normalized states for:

- `SecurityStackHealthy`
- `ThreatResolved`

For agent-health-only tickets, authoritative EDR/AV health may satisfy the technical completion condition.

For threat-triggered tickets, completion requires both:

- `SecurityStackHealthy = true`
- `ThreatResolved = true`

### Malware / antivirus scanning

An approved AV/malware scan is a required verification mechanism.

- **Routine EDR/AV health repair:** once the protection stack is healthy, run an approved **quick scan** before completion when supported.
- **Threat-triggered incident:** run an approved scan during investigation or immediately after remediation, then run a post-remediation verification scan before completion.
- **Persistent, ambiguous, high-risk, or recurring detection:** permit a **full scan or approved second-opinion scanner** when warranted by the evidence.
- Prefer a provider-native Datto AV scan when an authoritative governed capability exists.
- An approved independent scanner such as Microsoft Safety Scanner may be used as a second opinion when Datto evidence is incomplete or the detection remains ambiguous.
- Do not interpret "scan job completed" as "endpoint clean." The scan record must be read and evaluated.
- The TeamAOT Datto EDR tenant's `ScanHistoryTracking` model exposes scan type, status, timestamps, and duration but no authoritative "zero threats found" field. Therefore Jason may derive a clean verification state only from a completed scan record plus a post-scan governed detection search showing no unresolved/new matching detection evidence.

Full scans may be CPU/disk intensive. They should be scheduled intelligently when practical. Scanning is non-destructive, but any disruptive follow-up action remains subject to the normal approval rules.

### Threat remediation and verification ladder

The threat-response branch should follow a bounded flow equivalent to:

`read threat evidence -> verify EDR/AV health -> scan -> remediate/quarantine when governed and appropriate -> rescan -> reread originating threat -> verify no recurrence -> verify EDR/AV health -> complete or escalate`

If Datto has already successfully blocked or quarantined the object, Jason should verify that disposition and endpoint state rather than repeating remediation unnecessarily.

### Containment and high-risk detections

If evidence suggests ransomware, credential theft, active persistence, lateral movement, repeated execution, or another materially high-risk condition:

- capture available evidence;
- recommend endpoint/network isolation or other containment;
- require explicit technician approval for user-disruptive containment actions unless a future separately approved policy grants that exact authority;
- continue to preserve `direct_provider_access=false` and Central Orchestrator authority.

### False-positive / business-application branch

If the detected object may be legitimate:

- inspect signer/publisher and available file metadata;
- compare the detection with known business application context and prior documented exceptions;
- preserve the hash/path/detection evidence;
- route to false-positive/allowlist review rather than repeatedly repairing the AV agent.

Jason must not autonomously create an AV exclusion merely because a user or application claims the file is safe. Exclusions and allowlisting require the applicable governed approval/policy.

### Post-remediation recurrence check

For threat-triggered incidents, do not close immediately after one clean action. Require a bounded verification period or reread sufficient to establish that:

- the originating threat is no longer active;
- no new matching detection has appeared;
- the post-remediation AV scan is clean or otherwise has no unresolved malicious finding;
- the EDR/AV stack still reports authoritative healthy state.

The exact recurrence window may vary by severity and implementation policy; it must be explicit and persisted so Jason can resume the same run without duplicating remediation.

### Required state additions

The implementation should support terminal/intermediate states sufficient to distinguish at least:

- `Healthy`
- `ThreatContained`
- `ThreatRemediated`
- `AwaitingVerification`
- `FalsePositiveReview`
- `AwaitingApproval`
- `EscalationRequired`

A provider action succeeding is never itself a terminal incident-resolution condition.

### Capability preflight

Before claiming that Jason can fully resolve a playbook run, perform a capability preflight for the exact branch. The threat branch should identify whether governed capabilities exist for the equivalent of:

- threat detail/status read
- endpoint alert reread
- component execution
- automation job status and StdOut/result read
- provider-native malware/AV scan
- approved secondary scanner, if configured
- threat quarantine/remediation or provider disposition action, if supported
- internal Autotask ticket note creation
- Autotask ticket update/closure

Missing capabilities must be recorded as explicit implementation gaps before remediation begins when they prevent full resolution.

### Ticket documentation

For every meaningful diagnostic, scan, remediation, recheck, approval gate, and terminal decision, record an internal-only ticket note containing:

- operation/component/scan performed
- job/correlation ID when available
- result or relevant StdOut
- interpretation
- resulting health/threat state
- next decision or escalation reason

For threat-triggered cases, the final note must include the originating threat ID, final threat disposition, final scan result, and final EDR/AV health result.

### Completion criteria

**Agent-health-only ticket:** complete only after authoritative EDR/AV health is restored and the required verification scan, when supported by the configured workflow, has no unresolved malicious finding.

**Threat-triggered ticket:** complete only after all of the following are true:

1. authoritative EDR/AV health is `Healthy`;
2. an approved post-remediation AV/malware scan has completed with no unresolved malicious finding;
3. the originating threat is no longer active or is authoritatively contained/remediated;
4. the configured recurrence/recheck requirement has passed without a matching new detection;
5. required Autotask documentation has been written successfully.

If any required completion evidence cannot be obtained, the run must remain open or transition to `EscalationRequired`; it must not be falsely marked resolved.

### Acceptance-test requirement

Use AOT-50282 / T20260918.0005 as a controlled acceptance-test pattern for the threat branch because it demonstrates the important case where the security stack can report healthy while the originating Datto threat remains open. The acceptance test must prove that the future playbook does not close solely on `Status=Healthy`, performs the required scan/verification path, and requires authoritative threat resolution before completion.

## V1.2 implementation validation completed 2026-09-18

Implemented and locally validated in the isolated playbook worktree:

- separate `SecurityStackHealthy` and threat-resolution state;
- deterministic security dispositions that do not infer compromise from product health or one alert;
- explicit provider-indicated versus corroborated compromise signals;
- Datto-documented alert/API field normalization contract;
- tenant API capability preflight that fails closed when required reads are unavailable;
- scan result model that requires result readback before clean completion;
- low-cardinality playbook telemetry and source registry;
- Prometheus playbook metrics contract;
- Grafana `Jason Playbook Control Center` source dashboard;
- canonical playbook document under `docs/playbooks/`;
- unit tests, Python compilation, dashboard JSON validation, shell syntax validation, and Prometheus configuration validation.

The Datto EDR/AV API credential is now stored in OpenBao as `datto_edr.readonly` behind the dedicated `jason-datto-edr-read` AppRole. Credential-safe AppRole resolution and bounded live read-only API access were proven without printing the token. No endpoint or provider mutation was performed by this commissioning/source-validation work.

The TeamAOT tenant LoopBack OpenAPI was discovered and inspected. The governed read-only connector is implemented and registered behind provider-neutral `endpoint.security.*` capabilities. AOT-50282 provided a live identity/health/security-evidence proof: the authoritative Datto RMM resource UID mapped exactly to one active Datto EDR `deviceId`, while a second same-hostname EDR record was stale/inactive. This proves hostname alone must not become EDR identity.

## Remaining production activation prerequisites

1. Deploy the Datto EDR connector, dedicated AppRole mounts, and provider-neutral `endpoint.security.*` read registrations into the production Jason runtime through the normal governed deployment path.
2. Verify the live production MCP exposes and successfully executes the canonical read capabilities through Central Orchestrator, including status, detection search/detail, policies, scan history, and quarantine history.
3. Wire persisted playbook runs and low-cardinality telemetry events through Central Orchestrator; the playbook itself must not create an unmanaged provider or telemetry persistence path.
4. Add a governed provider-native Datto AV scan execute path. Scan verification readback is now defined as a completed `ScanHistoryTracking` record plus a clear post-scan governed detection search; scan history completion alone never means clean. Until governed scan execution exists, threat-triggered completion must fail closed or use a separately approved second-opinion scanner where appropriate.
5. Retain clean uninstall/recovery as policy-gated for the first supervised pilot.
6. Require explicit technician approval for **every reboot instance**, including the normal 02:30 scheduled reboot. Approval of the playbook itself is not standing reboot authority.
7. Confirm the live `Run Ad Hoc Command (PowerShell 2-5) [WIN]` component still uses the expected `Command` variable contract before first live use; this confirmation does not require endpoint execution.
8. Deploy the playbook exporter/Prometheus/Grafana source through the normal observability deployment process and verify the `Jason Playbook Control Center`.
9. Run the controlled AOT-50282 / T20260918.0005 acceptance pattern. Prove exact ticket/device/EDR identity, healthy-stack versus threat-state separation, composite clean scan verification, recurrence verification, and that the threat branch cannot close on `Status=Healthy` alone.
10. Record acceptance evidence, known limitations, Grafana visibility, and final source revision before marking the Section Goal complete.

## No-device-work boundary

Source changes, capability reads, tests, documentation, and deployment preparation do not authorize endpoint execution. A live pilot begins only through a separately initiated governed playbook run against an explicitly selected endpoint.
