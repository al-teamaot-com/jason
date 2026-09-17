# Jason - Datto EDR/AV Diagnose & Repair - Deployment Readiness

Status: source implementation in progress; no endpoint execution performed.

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

## Remaining production activation prerequisites

1. Unit tests for `datto_edr_av_playbook.py` and `datto_edr_av_runtime_contract.py` pass in the Jason build environment.
2. The playbook runtime is wired to Central Orchestrator rather than calling provider connectors directly.
3. Target resolution verifies exact Autotask company/ticket/device association and exact Datto device UID before action.
4. The generic component-execution pilot's current single-endpoint configuration is either deliberately retained for the supervised pilot or replaced by a governed exact-target mechanism before wider use.
5. Clean uninstall/recovery remains policy-gated for the first supervised pilot.
6. Immediate reboot remains approval-required; only the named 02:30 scheduled reboot path receives playbook standing authorization.
7. Autotask notes remain internal-only and milestone-driven.
8. Job status/StdOut read failures retry reads on the same job and never redispatch remediation.
9. `Status=Healthy` from the authoritative health component remains the only success terminal state.
10. Before first live use, confirm the live `Run Ad Hoc Command (PowerShell 2-5) [WIN]` component still uses the expected `Command` variable contract; this confirmation does not require running it on a device.

## No-device-work boundary

Source changes, capability reads, tests, documentation, and deployment preparation do not authorize endpoint execution. A live pilot begins only through a separately initiated governed playbook run against an explicitly selected endpoint.
