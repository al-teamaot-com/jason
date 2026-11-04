# AOT — DRMM first-pass Windows diagnostic components

**Status:** Source implementation for preproduction review; not imported, activated, or accepted on Datto RMM.
**Scope:** Three independent Windows PowerShell 5.1 Datto RMM scripts intended for NT AUTHORITY\SYSTEM noninteractive execution.
**Operational owner:** Atlantic Office Technologies.
**Authority:** Project Jason Governance Handbook, JES-001–004, Jason Platform Integrity / governed component execution, and production freeze.
**Review:** Before first DRMM import, after meaningful OS/Datto changes, and whenever evidence demonstrates a diagnostic gap.

## Goal and order

1. **AOT - Windows Diagnostic Snapshot [WIN]** — one broad, quick first-pass general ticket diagnostic.
2. **AOT - Disk Space Analysis [WIN]** — characterize volume usage, top root folder sizes, known high-volume paths, disk health, VSS, and related events before any cleanup is proposed.
3. **AOT - Network and DNS Diagnostics [WIN]** — enumerate adapters, DNS, gateways, routes, network profiles, domain and time status, bounded resolution/connectivity, relevant system event evidence.

They are independent collections so a single case-specific component gives broad relevant evidence with no additional routine components needed. They share versioned helper source compiled into three standalone scripts; they do not call one another at runtime. No existing Datto component or monitor is overwritten, disabled or repurposed. Existing components such as Proactive Event Log Health Diagnostic, Comprehensive Disk & Storage Diagnostic, DNSFilter / DNS Agent Diagnostic, Get-DNS Settings and Get time source can provide deeper additional evidence where necessary, but are not mandatory for the first pass.

## Implementation and provenance

- Source: scripts/drmm-diagnostics/source/common.ps1, windows-snapshot.ps1, disk-space-analysis.ps1, network-dns.ps1
- Build: python3 scripts/drmm-diagnostics/build.py
- Single-file output: scripts/drmm-diagnostics/components/*.ps1
- Manifest: scripts/drmm-diagnostics/manifest.json, SHA256 of each artifact
- Tests: python3 -m unittest discover -s scripts/drmm-diagnostics/tests -v

Datto RMM Component Library integration **has not been executed**; no governed Jason automation.component.create capability has been observed. No direct Datto API, browser UI, or credential bypass is approved in place of the governed path. Manual technician import through the authorized Datto RMM UI is an optional separate operator step only after technical acceptance and explicit scope choice.

## Contract

Each component prints a concise technician summary followed by:
- AOT_DIAGNOSTIC_JSON_BEGIN
- one compressed, self-contained JSON object
- AOT_DIAGNOSTIC_JSON_END

The object includes schema version, component, UTC observation time, device name, run identity, ordered diagnostic sections with individual collection status and duration, interpreted findings, and whole collection status.

Section status: complete, partial, unavailable, not_applicable.
Collection status: complete, partial, unavailable. An empty/error section is **not evidence** of a healthy condition. A successful read of bad endpoint state is still a successful collection; findings communicate observed concerns.

DRMM script exit 0 means the component collected at least one complete or partial section; exit 1 means collection as a whole is unavailable. **These are diagnostic scripts, not Datto RMM monitors.** Do not use monitor-specific result semantics or automatic remediation based only on a diagnostic exit code.

## Safety and performance bounds

- Read-only observation only. Never restart services, reboot, log off, disconnect or reset networking, alter policy, clear DNS/cache, remove files, update software or install a module.
- Powershell 5.1, SYSTEM, noninteractive, no UI prompts, no credentials, no external upload, no implicit public Internet connectivity probes.
- Bounded event history: 3–7 days, with individually limited event counts; event message excerpts truncated.
- Disk traversal: six fixed volumes maximum, up to 32 top-level directories each, at most 40,000 counted files, 25 seconds per volume and approximately 75 seconds across top-level traversal; inaccessible entries and reparse points are skipped, and truncated scans marked **partial**. Measured folder bytes represent a **lower bound**, never a precise total when a scan is partial. Additional known directories are sampled separately at small bounds.
- Network: at most 30 adapters, six DNS servers enumerated for relevant settings, up to three queried per name, up to three selected test names, short timeout probes to in-scope gateways/DNS/DC only; optional DiagTargetHost allows a syntactically valid technician-supplied hostname (no URL or command arguments). TCP/ICMP failures may be blocked by network policy and are not definitive proof of endpoint failure.
- No disk scan follows directory junctions/reparse points. File names are not listed; only top-level folder paths and aggregate counts/size are returned. Diagnostic logs, local paths, event text and network/hostname data may still be client-sensitive; keep results within the authorized ticket/client evidence boundary.
- Avoid Win32_Product, installer/uninstaller invocation, state-changing registry reads, or destructive cleanup commands.
- No second component invocation is authorized solely by an output-read failure. Fetch the same Datto job output using the exact job/device/component identifiers.

## Known limitations

- Windows APIs differ by edition/role and may be unavailable; such sections are explicitly partial or unavailable.
- Folder traversal only calculates sampled lower bounds, and Windows file size differs from physical allocated storage, compressed/deduplicated files, VSS and hardlink accounting.
- DNS settings may be intentionally replaced by DNSFilter/DNS Agent. A loopback resolver is a **symptom for investigation**, not sufficient evidence of a broken configuration.
- Ping, DNS and TCP tests do not prove application-layer health, firewall correctness or domain trust.
- PowerShell output lengths, confidentiality, provider timeouts, and DRMM job output truncation must be observed in the provider-backed pilot.

## Integration and acceptance gates

1. Preserve source-only PR and review with concurrent PMV3.1 work; no production deployment by implication.
2. Static/contract tests and Windows PowerShell 5.1 parser validation on an authorized test host.
3. Import three **new** components with exact names into an authorized DRMM test scope, preserving existing component IDs/policies. For each, verify imported content SHA or byte-for-byte source equivalent and selected execution identity/timeout.
4. Run each on **one designated non-production Windows test endpoint** using Jason's governed component execution path after required per-run/standing authorization. Capture job identity, terminal state, stdout JSON, collection completeness, duration and evidence.
5. Simulate/validate low disk, failed DNS lookup, inaccessible event logs, and capped traversal; establish that partial/unavailable state does not incorrectly imply health.
6. Confirm no user-visible disruption, no endpoint state change, and no new monitoring policy/automatic ticket action; obtain review of secret-safe/redacted output.
7. Only after owner-governed promotion, register exact live Datto component IDs and classify standing-safe/per-run according to observed provider result and risk. Never assume all diagnostics are automatically standing-safe.
8. Any Jason runtime/release change requires separately governed, immutable revision and exact-revision approval through PMV3.1; DRMM component-library changes also require their own authorized execution path.

## Documentation impact

- Architecture/standards/ADR: no authority architecture change; reuses existing governed component-execution boundary.
- Component contract: three standalone read-only scripts and JSON schema documented here.
- Construction guidance: shared helper/build/manifest pattern is self-contained in source and this runbook; no new connector class.
- System Registry: no operational entities registered because nothing is deployed.
- Operations and proof: this runbook and manifest; provider-backed acceptance remains outstanding.
- Current resume point: PR/runbook is the durable handoff; no claim of production readiness or DRMM presence.
