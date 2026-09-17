# Datto AV Force Update [WIN] AOT Ver 09172026-1

Purpose: provide a narrow governed Datto RMM component for the exact Datto AV recovery action proven during the AOT-50282 repair sequence: run the active HUNTAgent executable with `datto-av --force-update`, then independently verify EDR/AV health.

## Datto RMM component definition

- Name: `Datto AV Force Update [WIN] AOT Ver 09172026-1`
- Platform: Windows
- Script engine: PowerShell
- Intended runtime: Windows PowerShell 5.1 / SYSTEM
- Variables: none
- Recommended component timeout: 10 minutes or greater
- Source: `Datto_AV_Force_Update_WIN_AOT_Ver_09172026-1.ps1`

## Evidence behind this component

The successful AOT-50282 recovery used the RMM-managed HUNTAgent executable at:

`C:\ProgramData\CentraStage\AEMAgent\RMM.AdvancedThreatDetection\agent.exe`

with the exact arguments:

`datto-av --force-update`

After reboot, the authoritative health component reported `Status=Healthy`. The HUNTAgent executable later resolved to the alternate supported Datto path:

`C:\Program Files\Infocyte\agent\agent.exe`

Therefore this component discovers the active path from the HUNTAgent service each run and accepts only those two known locations. It does not hard-code one install location as authoritative.

## Safety behavior

The component:

1. Requires the HUNTAgent service to exist and be running.
2. Extracts the executable path from the service definition.
3. Allows only the two known Datto EDR agent locations.
4. Requires the executable to have a valid Authenticode signature.
5. Detects an already-active `agent.exe datto-av --force-update` process and does not start a duplicate.
6. Starts only `agent.exe datto-av --force-update`; no arbitrary arguments or shell input are accepted.
7. Observes the process for five minutes. If still active, it returns `Status=PendingReboot`, leaves the process alone, and instructs the playbook not to redispatch.
8. Does not echo the child process's raw output into Datto component StdOut, reducing the chance of leaking registration or tenant details.
9. Never declares Datto AV healthy. Jason must run `Check Datto EDR/AV Status AOT Ver 12122025-1` after the component or after the required reboot.

## Result semantics

- `Status=UpdateCommandCompleted` — the force-update process exited successfully; rerun the authoritative health component.
- `Status=PendingReboot` — the force-update remains active after the bounded wait; do not dispatch another update. Use the approved reboot path, then verify.
- `Status=AgentNotReady` — repair EDR/HUNTAgent first.
- `Status=UntrustedAgentPath` or `Status=SignatureInvalid` — stop automated AV repair and escalate.
- `Status=MultipleUpdatesActive` — stop rather than adding another process.
- `Status=CommandFailed` or `Status=ComponentError` — do not blindly retry; continue only according to the bounded playbook policy.

## Governance

This component is intended to become an exact-identity Datto component in `Jason - Datto EDR/AV Diagnose & Repair`. It does not authorize generic PowerShell execution and does not broaden Jason's Datto component allowlist. Its Datto UID must be discovered through Jason's governed component catalog after it is created in Datto RMM, then added to the runtime binding and server-controlled component scope before live use.
