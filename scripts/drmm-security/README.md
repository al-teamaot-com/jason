# AOT Read-Only RAT & Malicious-Tool Sweep — V2

**Datto RMM component:** `Check RATs and Malicious Tools - AOT Ver 11042026`
**Existing Datto UID:** `8ff72744-cb29-4cad-a11b-7a1c2a199f06`
**Source:** `scripts/drmm-security/rat-sweep.ps1`
**Execution:** Windows PowerShell 5.1 / NT AUTHORITY\SYSTEM, no prompt, no reboot, no process/service/network modification, no file deletion or quarantine.

## What prompted V2

Verified, read-only tests on **Al** and **Al-Samsung** completed on November 4, 2026 after correcting a false-positive classifier that treated null Win32_Process.ExecutablePath as system-process masquerading. Both hosts then produced **zero High** alerts, but the scripts flagged expected Microsoft Defender and Datto components due to a generic `ProgramData` path heuristic. On Al, `Get-MpPreference` raised `0x800106ba`; an independently read-only local diagnostic confirmed `Get-MpComputerStatus` reports `AMRunningMode=Not running` and `AntivirusEnabled=False`. This may be normal with Datto AV, but does NOT establish security-product health.

## V2 behavior

1. Signed Microsoft Defender services `WinDefend`, `WdNisSvc`, and `MDCoreSvc` under the exact expected `ProgramData\Microsoft\Windows Defender\Platform\<version>\` executable paths are **Info** inventory when their actual Authenticode signature is Valid and signer is Microsoft Corporation. These findings are retained, not suppressed. No name-only or path-only trust.
2. Datto endpoint-protection service / registered AOT EDR autorun under the expected `ProgramData\CentraStage\AEMAgent\` subtree can also be reported as Info **only** with valid Authenticode signature and a matching known vendor signer. Any unexpected signer, missing file, hidden attribute, wrong location or suspicious command-line signal preserves the prior warning.
3. Defender coverage distinguishes `active_or_passive`, `inactive`, `unknown`; `Get-MpPreference` is not called when Defender AV is inactive. The preference status becomes `skipped_inactive`, with a durable optional-coverage note stating that exclusions were not checked. `0x800106ba` from a still-attempted query also becomes `skipped_inactive` while unrelated errors remain `collection_status=partial`.
4. Jason-friendly bounded header now includes `Coverage | DefenderAV=... Preferences=... DefenderDetections=... SignedSecurityInventory=...` before the long JSON. JSON adds `optional_sections`, `defender_coverage` and `scanned.expected_signed_security_components` without removing previous v1 keys. The existing output-size ceiling and report-only exit status remain.
5. The collector still cannot prove absence of RATs, fileless malware or kernel rootkits. Signature validity and expected paths do not prove a component is authorized or uncompromised. Microsoft Defender being inactive does not mean Datto AV/EDR protection was inspected by this script.

## Guardrails

- `Get-AuthenticodeSignature`, `Get-FileHash`, `Get-CimInstance`, `Get-MpComputerStatus` and similar read-only operations only. Never alter Defender settings or program execution in this scan.
- High-severity RAT names, suspicious command arguments, unexpected masquerading paths, registry hijacks, and Defender detections retain their alert classifications.
- Standard reporting mode omits `-MonitorMode`. Do not turn this on automatically across client devices before reviewing baseline false positives.
- **Existing component must be updated through the authorized Datto UI/provider process.** The Jason MCP plugin currently offers read/search/execute but does **not** expose Datto component-body update. Do not use shell/API/credential bypasses.
- Deployed component script-body identity **cannot be cryptographically proven through Jason's current governed component catalog**, which exposes component UID/name and metadata but not executable content hash. Hash parity is established only for the source-controlled artifact and the staged AOT workstation copy.

## Acceptance and status

- V1 2026-11-04 governed DRMM runs: 2/2 completed; zero High after prior null-path correction; `DefenderPreference` incomplete as above.
- V2 source: SHA-256 **`2f4c43360a04cc69dea47d9bbfe89e8456114f476660f192105d1817459476d8`**; copied to Al's Downloads and isolated Jason worktree with exact SHA parity; Windows PowerShell 5.1.26100.9711 AST parse passed with **zero errors**.
- On Al, local Windows script-file execution is restricted by its effective PowerShell execution policy. Do **not** bypass this restriction simply for testing; provider-backed acceptance must use the authorized Datto component runner after normal component-library import.
- Targeted CI: `.github/workflows/aot-rat-sweep-security.yml` runs a Windows PowerShell 5.1 parser/AST and synthetic read-only classification + Defender sensor coverage suite. Passing CI does not replace live SYSTEM acceptance.
- **No provider component update, component reassignment, production merge/release or customer endpoint action is authorized merely by this PR.** Production freeze and exact-SHA rules remain in place.

## Planned live acceptance after approved import

Run once in standard report-only mode on the previously authorized AOT test devices:
- Al UID `69571572-83f7-1e33-9cdf-01717d4e74a4`
- Al-Samsung UID `710e63d6-caca-d830-697a-81250b0a8321`

Use governed `automation.component.execute`, one exact job ID per device, poll to terminal, retrieve exact-job stdout/stderr and confirm:
- Both scripts complete in NT AUTHORITY\SYSTEM with normal exit.
- Neither creates High findings for unreported Windows process paths.
- Known validly signed Defender services become Info; unexpected/malicious signs still warn.
- Defender preference skip has a clear reason and does not mask unexpected sensor errors.
- JSON coverage notes, finding counts, no raw command-line secret exposure and no endpoint mutation are verified.

**Version state:** Source change in development/preproduction. Not yet imported, not live-accepted, not production-deployed.
