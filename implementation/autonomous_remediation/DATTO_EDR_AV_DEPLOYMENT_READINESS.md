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

## Remaining runtime blocker

The playbook currently models Datto AV refresh as the predefined operation:

`agent.exe datto-av --force-update`

Jason's live governed action surface does not expose arbitrary shell execution, and the Datto component catalog search did not identify an exact dedicated Datto AV force-update component. Therefore the runtime binding intentionally fails closed at this step rather than falling back to PowerShell or direct provider access.

Before production activation, create or identify one narrowly scoped Datto RMM component that performs only the approved AV force-update behavior, discovers the active HUNTAgent executable path, validates the expected executable, refuses duplicate concurrent update work, and emits structured Result/Diagnostic output. Then verify its exact Datto UID through governed catalog discovery and add it to the runtime binding contract.

## Production activation prerequisites

1. Unit tests for `datto_edr_av_playbook.py` and `datto_edr_av_runtime_contract.py` pass in the Jason build environment.
2. The dedicated governed Datto AV force-update component/capability exists and is exact-identity verified.
3. The playbook runtime is wired to Central Orchestrator rather than calling provider connectors directly.
4. Target resolution verifies exact Autotask company/ticket/device association and exact Datto device UID before action.
5. The generic component-execution pilot's current single-endpoint configuration is either deliberately retained for the supervised pilot or replaced by a governed exact-target mechanism before wider use.
6. Clean uninstall/recovery remains policy-gated for the first supervised pilot.
7. Immediate reboot remains approval-required; only the named 02:30 scheduled reboot path receives playbook standing authorization.
8. Autotask notes remain internal-only and milestone-driven.
9. Job status/StdOut read failures retry reads on the same job and never redispatch remediation.
10. `Status=Healthy` from the authoritative health component remains the only success terminal state.

## No-device-work boundary

Source changes, catalog reads, tests, documentation, and deployment preparation do not authorize endpoint execution. A live pilot begins only through a separately initiated governed playbook run against an explicitly selected endpoint.
