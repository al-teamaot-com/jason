# Jason Dynamic Diagnostic Command Policy

Status: source policy and tests only. This document does not authorize or initiate endpoint execution.

## Goal

Jason must be able to reason about an endpoint and gather legitimate evidence even when the exact diagnostic command has never been pre-registered. A fixed catalog of every possible read-only command would prevent useful troubleshooting and would turn ordinary evidence gathering into a human-maintained allowlist problem.

The approved model is therefore **classify the proposed command, not the literal command string**.

Jason may generate a previously unseen diagnostic command and submit it through the exact reviewed Datto RMM component `Run Ad Hoc Command (PowerShell 2-5) [WIN]` only after the Central Orchestrator independently and deterministically classifies the command.

## Command classes

### 1. Passive read

May execute under standing-safe authority when all deterministic checks pass.

Examples include bounded local-state queries such as:

- `Get-Service`
- `Get-CimInstance`
- `Get-WinEvent`
- `Get-Process`
- `Get-NetIPConfiguration`
- `Get-NetTCPConnection`
- `Get-ItemProperty` outside protected secret locations
- `reg.exe query`
- `ipconfig /all`
- `netsh ... show ...`
- `sc.exe query`
- `systeminfo`
- `tasklist`
- `pnputil.exe /enum-*`

The exact command text does not have to exist in source control before Jason proposes it.

### 2. Active diagnostic probe

May execute under standing-safe authority when it is a single bounded non-disruptive probe.

Examples include:

- `Test-NetConnection`
- `Test-Connection`
- `Resolve-DnsName`
- bounded `ping`
- bounded `tracert`
- `nslookup`

This class is distinguished from a passive read because it sends diagnostic traffic, even though it does not intentionally change endpoint state.

### 3. Approval required

Anything the deterministic classifier cannot prove to be passive-read or bounded-probe remains per-run approval required. Unknown does not mean safe.

This includes commands that modify state, restart/stop/start services, change network configuration, install/remove software, alter files or registry values, reboot/log off a user, invoke nested shells, chain commands, use script blocks/method invocation/redirection, widen management scope to another computer, or request sensitive credential/secret material.

## Deterministic safeguards

The standing-safe path requires all of the following:

- exact Datto ad-hoc PowerShell component identity;
- exactly one `usrInput` variable;
- one bounded command or simple read-only projection pipeline;
- no command chaining, script blocks, nested expressions, redirection, encoded command, background job, or credential/session parameter;
- no remote-management `-ComputerName` scope for passive reads;
- no known secret-bearing registry/file locations or explicit credential/secret fields;
- command-specific validation for native utilities such as `reg`, `sc`, `netsh`, `ipconfig`, `route`, `wevtutil`, `manage-bde`, `pnputil`, `ping`, and `tracert`;
- unknown syntax fails closed to per-run approval rather than being guessed safe.

## Governance boundary

The language model may propose the command, but it does not decide the command's authority. The deterministic runtime classifier decides whether the exact proposed command receives standing-safe diagnostic authority or remains approval-required.

This preserves Jason's ability to reason and gather new evidence while maintaining the constitutional separation between reasoning, policy, and execution.

No command classified through this policy is considered evidence of remediation success by itself. Any workflow that changes state must still use its independent post-action verification and terminal-success criteria.
