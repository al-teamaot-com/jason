# Datto Dynamic Diagnostics Readiness — 2026-09-17

## Section Goal

Allow Jason to generate previously unseen legitimate diagnostic commands and execute only those that a deterministic server-side classifier proves are safe, read-only or bounded non-disruptive probes. Unknown, mutating, sensitive, disruptive, ambiguous, or unprovable commands must require exact per-run approval or fail closed.

## Governed boundary

- Central Orchestrator remains the only execution path.
- `direct_provider_access=false` remains required.
- Dynamic execution is restricted to Datto component `Run Ad Hoc Command (PowerShell 2-5) [WIN]`, UID `8a1c153c-feee-41c5-9c9b-58a48e0214fe`.
- The only dynamically promoted variable shape is exactly one `usrInput` value.
- Endpoint identity, component identity, allowlist, and device class are canonicalized server-side before authority evaluation.
- Caller/model approval-mode fields are not forwarded to execution and cannot promote a command to standing-safe.
- Standing-safe is derived only from deterministic command classification. Unknown syntax is not read-only by assumption.
- Per-run operations retain exact approval scope, maximum-attempt limits, audit, and provider readback semantics.

## Acceptance coverage

Focused CI validates both the classifier and the governed MCP execution boundary. It covers passive diagnostics, bounded probes, service mutation, registry mutation, DNS cache mutation, Wi-Fi mutation, arbitrary executables/scripts, command chaining, sensitive SAM/SECURITY reads, encoded/nested PowerShell, unknown syntax, extra variables, target mismatch, component UID/name mismatch, caller approval-mode override, exact canonical `usrInput`, and the single-attempt execution budget.

The focused workflow is `.github/workflows/datto-dynamic-diagnostics.yml`.

## Operational readiness

This capability does not authorize client disruption or remediation. It enables diagnostic evidence collection only when the runtime proves the command safe. Service starts/restarts, software changes, registry writes, reboots, configuration changes, and other disruptive or mutating actions remain approval-required.

No client-device execution was performed as part of this readiness validation.

## Next Section Goal

Harden the Datto EDR/AV diagnose-and-repair state machine so authoritative health, reboot-required routing, HUNTAgent startup state, force-reinstall output classification, dynamic AV force-update path discovery, and final `Status=Healthy` verification are deterministic and fully audited.
