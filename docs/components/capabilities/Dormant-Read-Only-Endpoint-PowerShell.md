# Governed Read-Only Endpoint PowerShell

Status: production-active through the governed Datto RMM Quick Job/component transport.

## Purpose

Provide Jason with broad read-only endpoint PowerShell for discovery and troubleshooting without granting endpoint mutation authority.

Canonical capability name:

`endpoint.powershell.read`

The production implementation currently uses Datto RMM Quick Jobs with the exact reviewed component `Run Ad Hoc Command (PowerShell 2-5) [WIN]` (UID `8a1c153c-feee-41c5-9c9b-58a48e0214fe`) as its execution transport. This is not Datto Web Remote or an interactive real-time shell. A separately reviewed supported Web Remote/real-time transport remains future work; when available, it may be preferred while this component path remains the reliable fallback.

## Safety model

Jason may construct diagnostic PowerShell directly. The capability is no longer limited to a small fixed menu of commands.

Before a command can reach a transport, Jason classifies it into one of four states:

- `read_only`: demonstrably observational and eligible for this capability.
- `sensitive`: read-only in system-state terms, but requests protected or user-sensitive information and requires a separate information-access authority.
- `mutating`: changes or can directly change endpoint state and must use normal governed execution.
- `uncertain`: cannot be confidently proven observational and therefore fails closed for reformulation or governed execution.

The governing principle is:

**Read broadly. Change narrowly. Access sensitive information deliberately.**

## Read-only scope

The classifier is designed to permit normal technician discovery patterns, including:

- `Get-*`, `Test-*`, `Resolve-*`, `Find-*`, `Search-*`
- safe pipelines
- `Where-Object`, `Select-Object`, `Sort-Object`, `Group-Object`, `Measure-Object`
- common read-only aliases
- process, service, event-log, registry, filesystem-metadata, networking, patch, task, and system queries
- bounded filtering and formatting
- a small set of harmless expression methods used for diagnostic filtering

Examples intended to pass include:

`Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 20`

and:

`Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddDays(-3)} | Where-Object Id -in 41,6008 | Select-Object TimeCreated,Id,Message`

DNS resolution and TCP connectivity checks are marked as active probes because they generate network traffic even though they do not intentionally modify endpoint state.

## Mutation boundary

Known mutating PowerShell verbs and constructs are rejected from the read-only capability. This includes service/process changes, filesystem or registry writes, install/remove actions, CIM/WMI method invocation, redirection to files, process launch, executable shell escape, and similar state-changing behavior.

A mixed pipeline such as:

`Get-Process | Stop-Process`

is classified as mutating and cannot execute through this capability.

The classifier is intentionally conservative. PowerShell text alone cannot prove every possible program is read-only. Ambiguous .NET methods, remote execution, custom verbs, or other constructs that cannot be confidently classified are rejected rather than guessed safe.

## Sensitive information boundary

Read-only does not automatically imply unrestricted information access.

The current classifier separates obvious protected reads such as:

- SAM/SECURITY registry or hive access
- LSASS-related collection
- DPAPI/protected-key locations
- browser credential/cookie stores
- private-key material
- NTDS database access
- direct file-content reads from common user Documents/Desktop/Downloads locations

Those reads require a future separate information-access authority even though they do not necessarily mutate endpoint state.

Filesystem metadata discovery remains distinct from file-content collection.

## Compatibility helpers

The original fixed diagnostic operations remain as convenience wrappers. They render normal PowerShell and then pass through the same general classifier, so they do not create a second safety path.

## Execution boundary

Production execution is bound to the supported Datto RMM Quick Job path and the exact reviewed ad-hoc PowerShell component:

- component UID: `8a1c153c-feee-41c5-9c9b-58a48e0214fe`
- component name: `Run Ad Hoc Command (PowerShell 2-5) [WIN]`
- component approval mode in the shared MCP component scope: `per_run`
- capability activation profile: `JASON_DATTO_POWERSHELL_READ_PROFILE=readonly-v1`

The capability performs its own read-only classifier and authority checks before the component transport is invoked. Generic Datto component execution is not enabled merely by activating this capability.

Datto execution is asynchronous. A successful dispatch may initially return a durable job ID while the job is still active. Follow-up must read that same job and its output; it must not redispatch the PowerShell command simply because inline polling expired.

The production transport must preserve:

1. authoritative device identity binding;
2. provider-supported authentication through the dedicated Datto execution AppRole;
3. exact command classification, endpoint, component, correlation, and job evidence;
4. bounded output retrieval and sensitive-data controls;
5. timeout behavior that does not create duplicate jobs;
6. ticket/device context binding when applicable;
7. the rule that this read capability cannot silently broaden into arbitrary shell authority.

### Real-time transport boundary

Datto Web Remote/interactive PowerShell is **not implemented by this capability today**. The current production path remains the ad-hoc component/Quick Job transport. Future Web Remote work must be separately researched and reviewed to determine whether Datto exposes a supported authenticated API, session, or WebSocket transport suitable for Jason. If admitted, it should preserve the same `endpoint.powershell.read` governance contract and use the current Quick Job/component path as fallback rather than creating an ungoverned shell path.

## Deployment state

Production activation was proven on 2026-09-25.

The production runtime and MCP expose `endpoint.powershell.read` under the dedicated `readonly-v1` activation profile. The transport uses the dedicated Datto RMM execution AppRole mounted read-only. The exact ad-hoc component remains explicitly scoped rather than permitting caller-selected arbitrary components.

Authority remains separate from activation. The controlled acceptance used an exact `observe` grant for principal `person-al` and capability `endpoint.powershell.read`.

### Production acceptance evidence

The controlled acceptance targeted AOT-50282 after resolving its authoritative Datto device UID. The command was `Get-Date`.

- exactly one PowerShell Quick Job was dispatched;
- Datto returned job ID `d4db5540-6c2f-4d41-ac70-0f45f42c0ff7`;
- the initial bounded inline poll timed out while the job remained active;
- Jason followed the same job through `automation.job.read` and `automation.job.output.read` rather than redispatching;
- stdout was returned from the exact reviewed component;
- the command completed with exit code `0`;
- the endpoint returned `Friday, September 25, 2026 9:33:24 AM`.

This proves the governed component-backed read path. It does **not** constitute proof of a Datto Web Remote/interactive PowerShell transport.
