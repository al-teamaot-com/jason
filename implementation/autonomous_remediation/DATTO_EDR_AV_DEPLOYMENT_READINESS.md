# Jason - Datto EDR/AV Diagnose & Repair - Deployment Readiness

Status: source implementation in progress; no endpoint execution performed.

## Live Jason capability surface verified 2026-09-17

- `automation.component.execute` is active and action-enabled through the Central Orchestrator.
- `automation.component.search` is active and read-only.
- `automation.job.read` is active and read-only.
- `automation.job.output.read` is active and read-only.
- `service.ticket.note.create` is an active write capability.
- `direct_provider_access=false` remains authoritative.

## Exact Datto component identities verified through governed catalog search

| Purpose | Datto component | UID |
| --- | --- | --- |
| Authoritative EDR/AV health | Check Datto EDR/AV Status AOT Ver 12122025-1 | `8cb0f063-5875-452e-88ad-2e1748ed0fd0` |
| Service diagnostic | Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1 | `2b49d490-bcae-4825-b31e-c4f1be881ae5` |
| EDR maintenance | Datto EDR Maintenance [WIN] | `3f069258-9b5e-4083-9b13-fa61c0fc0499` |
| EDR reinstall/upgrade | Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024 | `9c30dab8-b76c-417d-a264-b3ca91995179` |
| Clean uninstall | Uninstall Datto EDR / AV AOT Ver 11052025-1 | `b1e523aa-6464-4eaf-b99d-0172649f2115` |
| Scheduled reboot | 230 AM Scheduled Reboot AOT Ver 11282024 | `a61ce810-84a6-435c-ba02-b589a6008f28` |

These identities are evidence for exact matching. They do not themselves create standing authority.

## Proven Datto AV recovery behavior

The prior successful AOT-50282 repair established the missing AV-specific behavior without requiring a manual `EndpointProtectionService` start.

Observed successful path:

`EDR Maintenance / repair -> EDR Force Reinstall -> active HUNTAgent agent.exe datto-av --force-update -> reboot -> authoritative health check -> Status=Healthy`

The exact AV command was:

`agent.exe datto-av --force-update`

The RMM-managed HUNTAgent path before the successful force-update was:

`C:\ProgramData\CentraStage\AEMAgent\RMM.AdvancedThreatDetection\agent.exe`

After the recovery/reboot sequence, HUNTAgent was observed at the alternate supported path:

`C:\Program Files\Infocyte\agent\agent.exe`

This confirms the playbook must discover the current service executable path rather than permanently assuming one location.

The prior force-update job remained active unusually long and produced no StdOut. A second force-update was not launched. After reboot, the same authoritative EDR/AV health component changed from `Status=IssuesFound` / Datto AV not clearly detected to `Status=Healthy`.

## Dedicated AV component prepared

Source and operating contract are now present in:

- `components/Datto_AV_Force_Update_WIN_AOT_Ver_09172026-1.ps1`
- `components/Datto_AV_Force_Update_WIN_AOT_Ver_09172026-1.md`

Proposed Datto component name:

`Datto AV Force Update [WIN] AOT Ver 09172026-1`

The component is intentionally narrow. It discovers the active HUNTAgent path, allows only the two known Datto agent locations, validates the binary signature, prevents duplicate force-update processes, runs only `datto-av --force-update`, and self-bounds its observation window. If the child process remains active, it returns `Status=PendingReboot` instead of hanging indefinitely or dispatching another update.

Component completion never means AV health. The playbook must still run `Check Datto EDR/AV Status AOT Ver 12122025-1`, and only `Status=Healthy` closes the workflow successfully.

## Remaining runtime blocker

The dedicated AV component source is ready but the component does not yet have a Datto RMM UID. It must be created in Datto RMM, then its exact UID/name must be independently discovered through Jason's governed `automation.component.search` capability.

Until that exact identity exists and is added to the runtime binding/server-controlled scope, the runtime contract intentionally fails closed at the AV force-update step rather than falling back to generic PowerShell or direct provider access.

## Production activation prerequisites

1. Unit tests for `datto_edr_av_playbook.py` and `datto_edr_av_runtime_contract.py` pass in the Jason build environment.
2. Create `Datto AV Force Update [WIN] AOT Ver 09172026-1` in Datto RMM from the reviewed source and verify its exact Datto UID through governed catalog discovery.
3. Add that exact UID/name to the playbook runtime binding and server-controlled component scope; do not grant generic PowerShell standing authority.
4. The playbook runtime is wired to Central Orchestrator rather than calling provider connectors directly.
5. Target resolution verifies exact Autotask company/ticket/device association and exact Datto device UID before action.
6. The generic component-execution pilot's current single-endpoint configuration is either deliberately retained for the supervised pilot or replaced by a governed exact-target mechanism before wider use.
7. Clean uninstall/recovery remains policy-gated for the first supervised pilot.
8. Immediate reboot remains approval-required; only the named 02:30 scheduled reboot path receives playbook standing authorization.
9. Autotask notes remain internal-only and milestone-driven.
10. Job status/StdOut read failures retry reads on the same job and never redispatch remediation.
11. `Status=Healthy` from the authoritative health component remains the only success terminal state.

## No-device-work boundary

Source changes, catalog reads, tests, documentation, and deployment preparation do not authorize endpoint execution. A live pilot begins only through a separately initiated governed playbook run against an explicitly selected endpoint.
