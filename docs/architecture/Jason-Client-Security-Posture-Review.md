# Jason Client Security/Posture Review

## Section Goal
Allow Jason to select one authorized client, collect authoritative governed evidence, compare that evidence with AOT's managed-security baseline, and produce an evidence-backed gap report and improvement proposals without making configuration changes.

## Classification contract
Every control must resolve to exactly one of:
- `confirmed_good` — authoritative current evidence matches the baseline;
- `confirmed_gap` — authoritative current evidence contradicts the baseline;
- `unknown` — the source is available but current evidence does not establish the answer;
- `not_applicable` — the control is explicitly not applicable to the client/resource;
- `evidence_unavailable` — Jason lacks the authoritative provider/read surface needed to establish the answer.

Missing evidence must never be interpreted as healthy. Historical memory may guide investigation but cannot independently establish current posture.

## Initial AOT baseline families
The deterministic evaluator defines controls for BitLocker, managed AV, managed EDR, supported OS, DRMM monitoring health, VulScan coverage, DNSFilter coverage, managed backup coverage, recent backup success, Microsoft MFA posture, Conditional Access baseline, and documentation completeness.

This is an evidence model, not a claim that every provider surface is already available. For example, recent successful backup remains `evidence_unavailable` until the Endpoint Backup API is integrated; Microsoft MFA/Conditional Access remain unavailable where tenant consent does not authorize those reads.

## Safety and authority
The review is read-only. A `confirmed_gap` creates an improvement proposal; it does not authorize remediation. Existing ticket/company client boundaries remain authoritative. Provider reads must retain their own evidence timestamp and correlation/source reference. Cross-client evidence is prohibited.

## Next production slice
1. Bind a review to an exact Autotask company/client identity.
2. Map existing governed DRMM/Autotask/IT Glue evidence into normalized control observations.
3. Run the first review against a controlled AOT/XYZ test client.
4. Verify unavailable sources remain visibly unavailable rather than guessed.
5. Add a report surface and Grafana aggregate telemetry only after the evidence mapping is production-proven.

## First production binding proof — XYZ Test Company
On 2026-09-19, Jason resolved `XYZ Test Company` to exact Autotask company ID `1158` through governed `service.company.search` (correlation `corr_mcp_f5d001cb7c4c480aac62d17a30f6fff9`). Autotask configuration enumeration for company 1158 succeeded (correlation `corr_mcp_6eac32f8f6fc497bae4c42403e6758b9`).

The corresponding governed DRMM site search by exact company name returned zero sites (correlation `corr_mcp_d33b93ca77ea4318974a5a7892a6eeec`). IT Glue organization search was denied by the existing information-release gate and requested approval rather than releasing evidence (correlation `corr_mcp_436c6fb9086b4cc68f42a3178464131e`). Neither result is treated as a security gap: the DRMM-backed controls and documentation control are `evidence_unavailable` until an authoritative provider mapping/evidence path exists.

This proof establishes the desired fail-closed behavior for a controlled test client: exact Autotask company identity is mandatory; absent DRMM mapping does not permit cross-client/site searching; denied IT Glue evidence is not bypassed; and unavailable evidence cannot become `confirmed_good` or `confirmed_gap`.

## Mapped-client production proof — Atomic Plumbing & Drain Cleaning
On 2026-09-19, governed DRMM site discovery returned `Atomic Plumbing & Drain Cleaning`, site UID `a6af04fc-2e2a-4236-82ca-9d47ac616524`, with provider-reported Autotask company ID `333`. Governed Autotask `service.company.read` independently resolved company 333 to the same exact company name. This is accepted as an authoritative Autotask↔DRMM client binding.

The DRMM site contains 25 returned managed resources in the current search result. Exact endpoint-scoped reads for `Atomic-50291` (UID `8a19290c-7057-3567-a04a-2589b552a775`) proved Datto AV `RunningAndUpToDate`, Datto EDR active/online/authorized, AV enabled/connected/engine-ready, and a completed full AV scan on 2026-09-18. The same endpoint has current unresolved DRMM alerts, including a Critical Datto AV threat alert and Moderate monitoring alerts. These observations are valid endpoint evidence, but a single healthy endpoint is not sufficient to mark a client-wide control healthy.

The evaluator therefore now requires explicit `coverage_complete` before any healthy observations can become client-wide `confirmed_good`. Any authoritative bad observation can still establish `confirmed_gap`. This prevents sampled or partial inventory evidence from overstating client posture.

A provider issue was also observed: account-level `management.alert.search` with an Atomic site selector returned alerts belonging to multiple sites/clients. That response is excluded from client posture evidence. Client reviews must use provider results whose returned resource/site identity is independently verified against the bound client; exact endpoint-scoped alert reads are acceptable for the tested endpoint.

IT Glue organization search for Atomic remains denied by the existing information-release gate, so `DOCUMENTATION` remains `evidence_unavailable`. No bypass was attempted.

## Complete Atomic DRMM inventory proof
Revision `abc4a9b` changed site-only DRMM device discovery so it enumerates the authorized account collection to provider completion and then filters locally by exact site identity. Production correlation `corr_mcp_1c093e1f87ab44dda140ca079806f645` examined four provider pages / 749 account resources and returned exactly 29 resources whose provider-returned site UID is Atomic's bound UID. `discovery_complete=true`. This replaces the earlier provider-default-page sample of 25 and is acceptable completeness evidence for the DRMM inventory itself.

All 29 returned resources were then read individually through governed `endpoint.device.read`; every read succeeded and independently returned Atomic's exact site UID. Twenty-five are Windows managed endpoints (desktop/laptop/server) and four are network devices, which are excluded from Windows endpoint controls rather than treated as missing endpoint data.

The complete 25-Windows-endpoint AV inventory establishes a **confirmed gap** for the managed-AV control: `APD-50213` reports Windows Defender Antivirus `NotRunning`, and `APD-HYPERV` reports Datto AV `RunningAndNotUpToDate`. `APD-50712` reports Windows Defender Antivirus `RunningAndUpToDate` rather than Datto AV; whether that is an approved exception requires policy/exception evidence, so it must not be silently counted as compliant with the managed-Datto-AV baseline. The remaining returned Windows endpoint AV records report running/up-to-date protection.

The same inventory also establishes that unsupported-OS evaluation needs a version-support policy table rather than string heuristics. Multiple Windows 10 19045 endpoints, Hyper-V Server 2012, and Windows Server 2016 are present, but the posture engine will not label them supported/unsupported until the AOT baseline explicitly defines lifecycle criteria and exceptions.
