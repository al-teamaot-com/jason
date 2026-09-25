# Dormant Read-Only Endpoint PowerShell Foundation

Status: source-only candidate capability; not deployed; not registered for production runtime use.

## Purpose

Provide Jason with a bounded, read-only endpoint diagnostic surface for discovery and troubleshooting without granting arbitrary PowerShell or endpoint mutation authority.

Canonical capability name:

`endpoint.powershell.read`

The capability is intended for future use with a separately reviewed real-time endpoint transport such as a supported Datto RMM/Web Remote integration. This change does not implement or enable that transport.

## Safety model

Jason does not submit arbitrary PowerShell text. Jason selects a reviewed diagnostic operation and supplies bounded parameters. The policy renders the exact PowerShell command.

The current source-only allowlist includes:

- system summary
- service list/read
- process list
- volume list
- network configuration
- TCP connection inspection
- installed hotfix list
- scheduled task list
- bounded event-log reads
- allowlisted CIM class reads
- bounded registry reads under approved HKLM prefixes
- DNS resolution
- TCP connectivity tests

DNS resolution and TCP connectivity tests are marked as active probes because they generate network traffic even though they do not intentionally modify endpoint state.

## Explicit exclusions

This foundation does not permit:

- arbitrary command strings
- script blocks
- pipelines
- redirection
- command chaining
- encoded commands
- arbitrary native executable invocation
- arbitrary WMI/CIM classes
- unrestricted registry access
- file-content collection
- credential/SAM/LSA reads
- mutation cmdlets
- service/process changes
- software installation/removal
- reboot, shutdown, logoff, or other disruptive actions

## Execution boundary

The policy exposes a `ReadOnlyPowerShellTransport` protocol but provides no Datto transport implementation.

If no reviewed transport is injected, execution fails closed with:

`read-only PowerShell transport is not configured`

Before production activation, a transport must be separately reviewed for:

1. authoritative device identity binding;
2. provider-supported authentication/session establishment;
3. exact command and endpoint audit evidence;
4. output bounding and sensitive-data controls;
5. timeout/cancellation behavior;
6. correlation to ticket/device context;
7. confirmation that the transport cannot silently broaden into arbitrary shell authority.

## Deployment state

No production runtime, MCP catalog, compose file, OpenBao policy, credential, provider activation profile, or deployment configuration is modified by this feature branch.

The capability remains dormant until a later governed activation decision.
