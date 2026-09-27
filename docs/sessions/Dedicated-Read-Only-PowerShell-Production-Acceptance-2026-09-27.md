# Dedicated Read-Only PowerShell Production Acceptance — 2026-09-27

**Status:** PASS  
**Roadmap:** TODO-CONN-018  
**Capability:** `endpoint.powershell.read`  
**Provider:** `datto_rmm_powershell_read`

## Purpose

Prove the dedicated provider-neutral read-only PowerShell capability on representative Windows workstation and server targets using exact governed device identity, fixed Datto component identity, bounded output, one provider job per accepted command, and terminal job/output readback.

No endpoint mutation, reboot, service restart, file write, registry write, or destructive command was used.

## Production workstation acceptance

Target:

- hostname: AOT-50282
- Datto device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`

Accepted classifier-approved command:

`Get-CimInstance Win32_OperatingSystem | Select-Object CSName,Caption,Version,ProductType | ConvertTo-Json -Compress`

Result:

- dedicated `endpoint.powershell.read` invocation accepted;
- exactly one Datto diagnostic job created;
- job UID: `74568268-75c5-4c4e-85f7-f9a5b4fa0cae`;
- governed terminal readback: completed;
- stdout identified Microsoft Windows 11 Pro;
- ProductType = 1;
- command exit code = 0;
- stderr empty.

## Production server acceptance

Target:

- hostname: vz-server-00
- Datto device UID: `5cb0931e-51d0-b73c-cb53-ccc17f31e39e`

The first safe read used `Get-CimInstance`. Transport and Datto job execution worked, but Windows Server 2008 R2 / its installed PowerShell environment did not provide that cmdlet. Governed stderr correctly exposed a CommandNotFoundException. This was endpoint command compatibility, not a transport or authority failure.

A single compatibility replacement acceptance used:

`Get-WmiObject Win32_OperatingSystem | Select-Object CSName,Caption,Version,ProductType | Format-List`

Result:

- dedicated `endpoint.powershell.read` invocation accepted;
- exactly one replacement Datto diagnostic job created;
- job UID: `0340a4f9-f348-43f2-bddc-f9d24a132204`;
- governed terminal readback: completed;
- stdout identified VZ-SERVER-00;
- OS: Microsoft Windows Server 2008 R2 Enterprise;
- version: 6.1.7601;
- ProductType = 2;
- command exit code = 0;
- stderr empty.

## Correctness defects discovered and remediated

Production acceptance exposed two usability/correctness defects:

1. A read-only classifier denial, such as local variable assignment, was internally safe but surfaced to the caller as a generic capability invocation failure.
2. A completed Datto job with non-empty PowerShell stderr could otherwise be interpreted as completion-verified solely from provider job state/exit wrapper behavior.

Merged PR #396 / revision `d2aff802be2a052019d25759a5218e5b4a12f622` corrects both:

- classifier `PermissionError` is translated to typed `ConnectorAuthorizationError`;
- completed jobs with non-empty stderr fail closed as `DATTO_POWERSHELL_COMMAND_FAILED`;
- raw stderr is not copied into the exception/audit;
- focused connector/classifier tests pass 38/38.

The merged fix is deployed on live `jason-runtime` revision `d2aff802be2a052019d25759a5218e5b4a12f622`, healthy with zero restarts.

A production no-provider denial smoke using a variable-assignment form returned:

- error code: `CONNECTOR_AUTHORIZATION_DENIED`;
- no provider evidence/job was created.

## Acceptance conclusion

TODO-CONN-018's dedicated provider-neutral workstation/server acceptance requirement is satisfied.

The capability is proven for:

- representative Windows workstation;
- representative Windows server, including older PowerShell compatibility;
- exact device UID targeting;
- fixed server-side component identity;
- classifier-approved read-only commands;
- fail-closed mutating/sensitive/uncertain commands;
- bounded asynchronous job submission;
- governed terminal status/output readback;
- typed classifier denial;
- command-level stderr failure detection.

This does not grant arbitrary write-capable PowerShell, autonomous disruptive action, or provider mutation authority.
