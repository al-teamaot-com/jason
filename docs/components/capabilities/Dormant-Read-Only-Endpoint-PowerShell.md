# Dormant Read-Only Endpoint PowerShell Foundation

Status: source-only candidate capability; not deployed; not registered for production runtime use.

## Purpose

Provide Jason with broad read-only endpoint PowerShell for discovery and troubleshooting without granting endpoint mutation authority.

Canonical capability name:

`endpoint.powershell.read`

The capability is intended for future use with a separately reviewed real-time endpoint transport such as a supported Datto RMM/Web Remote integration. This change does not implement or enable that transport.

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

The policy exposes a `ReadOnlyPowerShellTransport` protocol but provides no Datto transport implementation.

If no reviewed transport is injected, execution fails closed with:

`read-only PowerShell transport is not configured`

Before production activation, a transport must be separately reviewed for:

1. authoritative device identity binding;
2. provider-supported authentication/session establishment;
3. exact command, classification, endpoint, and correlation audit evidence;
4. output bounding and sensitive-data controls;
5. timeout/cancellation behavior;
6. ticket/device context binding;
7. confirmation that the transport cannot silently broaden into arbitrary shell authority.

## Deployment state

No production runtime, MCP catalog, compose file, OpenBao policy, credential, provider activation profile, or deployment configuration is modified by this feature branch.

The capability remains dormant until a later governed activation decision.
