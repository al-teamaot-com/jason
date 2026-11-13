# AOT DRMM standing-safe diagnostic classification — preproduction

**Status:** Source-only remediation in review, not deployed to production.
**Owner objective:** Jason may autonomously collect bounded read-only first-pass Windows, disk and DNS diagnostic evidence under the existing Owner-approved Datto component registry. No remediation authority is implied.
**Governance:** Project Jason constitution; Owner authority; exact component identity; non-disruption; audit; immutable source; PMV3.1 release freeze and exact-SHA approval.

## Problem observed on 2026-11-04

The Jason Component Control Grafana panel showed these three items checked for Run autonomously, but `list_datto_component_approvals` rejected this ChatGPT caller with `DATTO_COMPONENT_APPROVAL_OWNER_REQUIRED`. The backend owner allowlist has one configured identity; this caller does not have it. The UI selected state is evidence of a user's chosen dashboard state, not by itself proof of every downstream authority gate.

A specifically bounded no-approval test of **Windows Diagnostic Snapshot - AOT** on AL-SAMSUNG was rejected **before dispatch**:
- code: `REMEDIATION_ACTION_NOT_JUSTIFIED`;
- reasons: `REMEDIATION_EVIDENCE_REFERENCES_REQUIRED` and `EXPLICIT_DISRUPTION_APPROVAL_REQUIRED`;
- server-derived impact: `service_interruption`;
- provider jobs executed: zero.

The source-level root cause is the shared remediation gate in `jason_mcp.server._governed_execute`: standing-safe non-disruptive diagnostics are exempt only if the component name begins with "Check ", "Get-", "Get status " or "Query status ". None of the three AOT names meet this prefix convention. Providing additional evidence alone does not eliminate the explicit-disruption reason, and setting `explicit_approval=true` would not verify autonomy.

## Narrow corrective design

The source-controlled passive diagnostic allowlist recognizes exactly:

| Datto UID | Verified name |
| --- | --- |
| 79943f0c-e614-4fcc-a5da-e396feab0a34 | Windows Diagnostic Snapshot - AOT |
| 4e9d59fb-440a-460b-9107-40f3954890fd | Disk Space Analysis - AOT |
| c259df3f-a6a2-4931-bf48-b6659846e9b1 | Network and DNS Diagnostics - AOT |

An entry bypasses **only the redundant remediation-justification gate**, never the ordinary governed execution/authorization gate, when **all** are true:
1. Exact Datto UID and name match the reviewed tuple.
2. The effective approval mode is server-computed `standing_safe`.
3. The approval is from the durable Owner registry, with nonempty metadata fingerprint.
4. The existing live Datto metadata fingerprint check has not found a mismatch; stale approvals fall back to per-run.
5. No component variables or dynamic command input are provided.

Per-run, unspecified, stale, wrong UID/name, ad-hoc PowerShell, and variable-bearing invocations retain the previous remediation gate and their exact approval requirements. No client-selected text, risk label, or component name prefix can create standing-safe status by itself.

The reviewed DRMM scripts were source-tested and executed through the governed provider path on AL/AL-SAMSUNG as part of PR #2303. **Caveat:** Datto's governed catalog does not currently expose an immutable executable script hash. Owner approval metadata fingerprints cover only reviewable catalog metadata, so later script-body-only changes must be independently change-controlled and revalidated. This feature is not a replacement for full script attestation.

## Preproduction acceptance

- Run the dedicated AOT diagnostic standing-safe classifier regression test on exact PR head.
- Positive: each of the three approved identity tuples performs one mocked governed call without explicit approval, and normal policy-based authority is recorded.
- Negative: same UID with wrong name, wrong UID with same name, stale fingerprint, source-configured rather than durable standing-safe, missing fingerprint, per-run mode, dynamic variables, ad-hoc PowerShell all fail before provider execution.
- Run security regressions, MCP capability discovery, full CI, and cross-PR overlap review against protected main.
- After eligible controlled release (with final Owner exact-SHA deployment approval), execute one bound diagnostic per component on an authorized AOT test endpoint with `explicit_approval` **omitted**, poll to terminal and fetch outputs from the same job, verify audit and no state change.
- If any test fails, keep the component per-run, do not weaken classification, and revert to last-known-good.

## Deployment boundary and production status

No production code, Datto component, registry, approval identity or endpoint configuration changes are made by this PR. PMV3.1 handles merged source review, last-known-good rollback, independent acceptance and exact-revision deployment authorization. The production freeze remains in force. Until such a release succeeds, the checked Grafana setting **does not imply working autonomous execution** for these three names.

## Documentation impact

Architecture: retains Central Orchestrator and Owner authority. Capability contract: adds exactly reviewed passive diagnostic identity exemption, not a generic provider-read escalation. Operations and security: this guide and regression tests. System Registry: unchanged. Release and rollback: governed PMV3.1 only.

## Concurrent change coordination (2026-11-04)

The exact server.py patches in #2158 (release ticket-read canary), #2125 and
stacked #2128 (client/onboarding write argument scope), and #2304 (paged Datto
job-output reads) were reviewed. This change is localized to the later,
post-canonicalization passive diagnostic exemption. It must be reconciled and
retested after any of those PRs merge; the current main baseline is not
permission to overwrite another workstream. Isolated preproduction CI exercises
the three no-approval cases and fail-closed scenarios using a temporary ledger.

## Verified preproduction regression evidence

At commit b0174f6ed8c533bf856116c7eaed692e0774c474 the targeted
standing-safe CI suite passed 12 tests: three distinct approved-component
execution scenarios plus refusal cases for wrong UID/name, missing/stale
Owner classification and variable-bearing requests. SEC-007 security regressions,
MCP capability discovery, gateway, routine runtime and other source checks
also passed. Full repository hygiene initially refused active shared-file
overlaps and was addressed using the required plain-text
`Integration coordination: #2304 #2158 #2125 #2128` PR metadata line.
This evidence proves behavior on an isolated mock Central Orchestrator only.
No production deployment, exact merge candidate, or live no-approval
acceptance is implied.
