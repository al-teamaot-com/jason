# AOT — DRMM first-pass Windows diagnostic components

**Status:** The Owner imported the first source revision into Datto RMM on 2026-11-04. Six governed test jobs on AL and AL-SAMSUNG reached terminal completed status. The updated source revision in this PR is not yet imported or operationally accepted because evidence output was capped and disk folder sampling was incomplete. No monitoring policy or scheduled execution was activated.
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

Datto RMM Component Library import of the initial script revision **was performed by the Owner**; no governed Jason automation.component.create/update capability has been observed. No direct Datto API, browser UI, or credential bypass is approved in place of the governed path. Manual technician import through the authorized Datto RMM UI is an optional separate operator step only after technical acceptance and explicit scope choice.

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

## 2026-11-04 initial provider-backed acceptance findings

All six jobs reached terminal completed via governed automation.component.execute on exactly AL (69571572-83f7-1e33-9cdf-01717d4e74a4) and AL-SAMSUNG (710e63d6-caca-d830-697a-81250b0a8321). No reboot, network reset, file cleanup, or other mutation was requested. Evidence:

- Windows Snapshot: AL job e523dd87-c050-4528-9e95-2fcc3addeff8: 9 sections complete, 13.826 seconds, pending-file-rename reboot indicator. AL-SAMSUNG job a985382a-aab7-4365-9954-cb01715f08e4: 9 sections complete, 21.313 seconds, no reboot indicator.
- Disk Space: AL job 4f6d08d5-49ba-4ba6-8472-35ab61878a19: 6 sections reported, partial root traversal and source output truncated at 65,536 chars. AL-SAMSUNG job 72e65dc9-e64c-400b-9ced-a59e1ec6ac40: 6 sections, partial root and Sysmon measurements; at least 15.373 GB measured in Sysmon, no files removed. Both jobs report 40 sampled events; these must be attributed by provider rather than assumed storage failures.
- Network and DNS: AL job 44ab2810-bb68-42bb-8f2c-23dbf28c96a2 and AL-SAMSUNG job 3f53df88-e389-4e86-8bd4-d3574c9670ce: 6 sections complete each, zero reported findings.

Separate MCP presentation truncates every returned text field after 2,000 chars, including these job output records. The full raw JSON cannot be accepted through the current governed read projection; separate output paging is being prepared. The disk component also exceeded the Datto connector's 65,536-character upstream source cap. Fixes in this source update address oversized CIM reference serialization, starvation of other folders by the first large folder, storage-provider event false positives, and MAC suffix display. Acceptance requires Owner re-import of revised component text, fresh governed read-only runs, full output retrieval through an approved governed mechanism, and evidence-sensitive review. No automatic standing approval has been requested or claimed.

**Operational next step:** Import the revised source artifacts only after technical review, then execute and verify exactly one job of each revised component on an approved test endpoint. The precise updated SHA256 values live in the generated manifest. Do not re-run the same DRMM job merely because its output was truncated at presentation time.

## Ephemeral Windows runtime acceptance (additional preproduction gate)

A dedicated Windows GitHub Actions workflow now tests the generated standalone scripts on an isolated hosted Windows runner under Windows PowerShell 5.1, without any Datto provider access or client credentials. It executes each read-only script exactly once, confirms an exit code of zero, verifies the complete marked JSON output and all required schema fields, ensures at least five sections contain collected evidence, and rejects output exceeding 65,536 characters (Datto's connector bound). It prints only bounded collection status and output lengths, never full endpoint evidence. This is **functional Windows-runner validation**, not DRMM provider-backed acceptance on AL/AL-SAMSUNG. That final gate still requires an authorized import of revised scripts and governed job execution/readback.
