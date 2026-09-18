# Project Jason Support List

This document is the governed support backlog for current defects, degraded capabilities, connector failures, operational blockers, and other issues that require repair or investigation.

It is intentionally separate from `TODO.md`. The TODO list tracks future ideas, enhancements, and planned capabilities; this Support List tracks things that should already work, or operational conditions that are preventing Jason from working as intended.

## How to use this document

Each item should include:

- **Issue** — what is failing or degraded.
- **Impact** — what Jason or a technician cannot reliably do because of the issue.
- **Observed behavior** — the concrete failure or evidence seen.
- **Expected behavior** — what should happen instead.
- **Scope** — affected connector, capability, provider, workflow, or environment.
- **Priority** — P0, P1, P2, or P3.
- **Status** — Open, Investigating, Mitigated, Blocked, Fixed, or Closed.
- **Owner** — person or role responsible for resolution.
- **Verification** — evidence required before the item can be closed.
- **Last observed** — most recent confirmed occurrence.

Items remain on this list until the underlying issue is fixed and the expected behavior is verified through the governed production path.

---

## Priority legend

- **P0** — production-blocking or safety-critical failure.
- **P1** — significant operational degradation affecting active work.
- **P2** — limited degradation with a usable workaround.
- **P3** — minor issue, cleanup, or low-impact defect.

---

## Open support items

### SUPPORT-CONN-001 — Autotask ticket read path failing through Jason

- **Priority:** P1
- **Status:** Investigating
- **Owner:** Jason Platform / Connector Support
- **Issue:** Jason's governed Autotask ticket read and mutation paths are failing for an active production ticket.
- **Impact:** Jason can identify the Datto RMM alert and its associated Autotask ticket, but cannot reliably read the ticket details/notes or perform the currently exposed governed ticket-note mutation. This prevents complete autonomous troubleshooting documentation, ticket-state assessment, and ticket closeout.
- **Observed behavior:**
  - Datto RMM correctly identified critical antivirus alert `bd0882e0-8700-4985-ad89-f789b865c76e` on `AOT-50282`.
  - The alert correctly references Autotask ticket `T20260918.0005` / internal ticket ID `140629`.
  - `service.ticket.search` failed with `CAPABILITY_INVOCATION_FAILED`.
  - `service.ticket.read` failed with `CAPABILITY_INVOCATION_FAILED`.
  - `service.ticket.notes.search` was denied with `SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED` / `REQUEST_ACCESS`.
  - Governed Datto RMM reads and component execution continued to work, isolating the observed degradation to the Autotask path rather than the endpoint itself.
  - On 2026-09-18, an explicitly approved attempt to create an internal note on ticket `140629` using the dedicated `create_autotask_internal_note` governed tool failed with `CAPABILITY_INVOCATION_FAILED` and `provider_write_attempts=1`; no note was created.
  - The active `service.ticket.update` capability requires a numeric tenant-specific Autotask status value and post-mutation readback verification. Because the read path is failing, Jason could not safely discover/verify the tenant's Complete status ID and did not guess or bypass governance.
- **Expected behavior:** Jason should be able to search, read, and retrieve notes for authorized Autotask tickets through the governed read path, including `T20260918.0005`, without using direct provider access or bypassing governance.
- **Scope:** Jason MCP -> governed Autotask reads and bounded mutations, including `service.ticket.search`, `service.ticket.read`, `service.ticket.notes.search`, `service.ticket.note.create`, and `service.ticket.update`.
- **Operational workaround:** Continue safe endpoint diagnostics through the governed Datto RMM path, but do not treat the Autotask ticket workflow as complete until ticket read access is restored.
- **Verification required for closure:**
  1. Search for `T20260918.0005` succeeds through the governed Autotask path.
  2. Read the ticket by its governed resource identifier succeeds.
  3. Ticket notes can be retrieved by an authorized Jason request.
  4. No direct-provider bypass is required.
  5. Create and verify one bounded internal note on a controlled ticket through the governed mutation path.
  6. Perform and verify one bounded ticket update through `service.ticket.update`.
  7. Repeat the reads in a fresh session to confirm the fix is durable.
- **Current diagnosis (2026-09-18):**
  - Reproduced `service.ticket.search` and `service.ticket.count` failures for `T20260918.0005` with `CAPABILITY_INVOCATION_FAILED`.
  - Reproduced the same `CAPABILITY_INVOCATION_FAILED` on a minimal `service.company.search`, showing the failure is broader than one ticket.
  - `service.ticket.notes.search` and `service.entity.describe` reach the governed Autotask path but fail information release with `SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED` / `REQUEST_ACCESS`.
  - Current source defines `jason_managed` as the temporary production default because provider-native Autotask requester impersonation is known to produce an Autotask HTTP 500. The split live behavior is consistent with production running with a stale or explicit `impersonated` requester-authorization mode.
  - The runtime Compose source does not explicitly declare `JASON_AUTOTASK_REQUESTER_AUTH_MODE`, so live container environment/configuration must be checked before changing anything.
- **Next safe action:** Inspect the live `jason-runtime` environment for `JASON_AUTOTASK_REQUESTER_AUTH_MODE` without exposing secrets. If it is explicitly `impersonated`, restore the approved `jason_managed` mode, recreate only the affected runtime service using the governed deployment runbook, then repeat all five closure checks above.
- **Blocked on:** Access to the production Jason runtime host/deployment path for configuration inspection and bounded remediation.
- **Last observed:** 2026-09-18 during active antivirus troubleshooting on `AOT-50282`, reconfirmed during Support List processing.

---

### SUPPORT-CONN-002 — Jason MCP transport intermittently returns UNAVAILABLE during governed work

- **Priority:** P1
- **Status:** Open
- **Owner:** Jason Platform / Connector Support
- **Issue:** The Jason MCP transport intermittently drops active governed requests with `UNAVAILABLE: McpServerError: Connection failed`.
- **Impact:** Active endpoint troubleshooting is repeatedly interrupted. Readbacks and status polls must be retried, increasing latency and making long-running Datto jobs harder to monitor reliably.
- **Observed behavior:**
  - Multiple consecutive `UNAVAILABLE` transport failures occurred on 2026-09-18 while troubleshooting `AOT-50282`.
  - Failures affected harmless reads such as `jason_mcp_status`, `automation.job.read`, `automation.job.output.read`, and alert reads.
  - Successful retries often immediately followed failures, showing the issue is intermittent rather than a persistent Datto endpoint failure.
  - The underlying Datto jobs remained intact across the transport failures; no evidence indicates the endpoint jobs themselves failed because of the disconnects.
  - At the latest checkpoint, repeated consecutive failures made Jason MCP temporarily unreachable and blocked further governed endpoint work.
- **Expected behavior:** Jason MCP should maintain reliable transport for governed reads/actions and allow stable polling of long-running provider jobs without repeated connection failures.
- **Scope:** ChatGPT/connector -> Jason MCP transport/session reliability; affects governed Autotask and Datto workflows.
- **Operational workaround:** Retry idempotent reads only; never redispatch a write or component solely because the readback transport failed. Preserve known job IDs and resume polling after MCP connectivity returns. Do not bypass Jason governance with direct-provider access.
- **Verification required for closure:**
  1. Run a sustained sequence of Jason status and governed read calls without `UNAVAILABLE` failures.
  2. Launch one approved safe Datto diagnostic and poll it through terminal completion without transport loss.
  3. Retrieve its StdOut successfully through the same governed session.
  4. Confirm no provider job duplication occurred during the test.
  5. Repeat from a fresh conversation/session.
- **Last observed:** 2026-09-18 while troubleshooting `AOT-50282`; repeated failures culminated in multiple consecutive MCP connection failures that temporarily blocked further governed work.

---


### SUPPORT-CAP-003 — Missing governed Datto AV/EDR threat-detail and remediation-state capability

- **Priority:** P1
- **Status:** Open
- **Owner:** Jason Platform / Datto RMM Connector
- **Issue:** Jason can see that Datto RMM raised an Endpoint Security threat alert, but the governed capability set does not expose the underlying Datto AV/EDR threat record needed to investigate and close the incident confidently.
- **Impact:** Jason can confirm that an antivirus alert exists and can troubleshoot endpoint health, but cannot directly answer the most important incident questions: what threat was detected, where it was found, what Datto AV did with it, whether it was quarantined or removed, and whether any remediation remains outstanding. This prevents a deterministic end-to-end AV playbook and can leave a critical RMM alert/ticket open even when the endpoint otherwise appears healthy.
- **Production example:** `AOT-50282`, Datto RMM alert `bd0882e0-8700-4985-ad89-f789b865c76e`, Endpoint Security alert ID `15884344`, Autotask ticket `T20260918.0005`.
- **What Jason needed to do:**
  1. Read the provider-native Datto Endpoint Security / Datto AV record for `esAlertId 15884344`.
  2. Retrieve the threat name/classification and severity.
  3. Retrieve the affected file, process, registry object, URL, or other detection source when available.
  4. Retrieve file hash or other useful IOC data when available.
  5. Determine the AV action taken: blocked, quarantined, deleted, cleaned, allowed, failed, or pending.
  6. Determine whether the object still exists or remediation is incomplete.
  7. Read quarantine/remediation state directly from Datto AV/EDR rather than inferring it from local folders.
  8. Determine whether the Datto alert is safe to resolve after clean verification.
  9. If supported by policy, perform or request the appropriate bounded remediation and then verify the threat state again.
- **What Jason was allowed to do:**
  - Read the Datto RMM endpoint record and see `Datto AV = RunningAndUpToDate`.
  - Read the open RMM alert, which exposed only `Detected threat from Datto AV` plus `esAlertId 15884344`.
  - Run approved Datto RMM diagnostic components on `AOT-50282`.
  - Run `Check Datto EDR/AV Status AOT Ver 12122025-1`, which confirmed HUNTAgent and Datto AV health.
  - Run `Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1`, which confirmed `EndpointProtectionService` was Running and Automatic.
  - Run Microsoft Safety Scanner (MSERT) and monitor its process/log state.
  - Run approved read-only PowerShell through the governed Datto component path to inspect local Datto AV, Infocyte/HUNTAgent, Windows Event Log, and MSERT evidence.
- **What was not available or not allowed:**
  - No governed capability was exposed for something equivalent to `endpoint.security.threat.read`, `endpoint.security.threat.search`, Datto EDR threat-detail read, quarantine read, or remediation-state read.
  - The standard `endpoint.alert.search` capability exposed the RMM wrapper alert but not the underlying threat name, file/path, hash, disposition, quarantine result, or remediation status.
  - `discover_capabilities` did not reveal a provider-native Datto AV/EDR threat-detail capability.
  - The Datto component catalog did not contain a native Datto AV threat-review or AV scan component that returned the missing provider threat record; MSERT was the only useful malware-scan component found.
  - Jason was **not allowed to bypass governance by using direct provider access**. Production remained `direct_provider_access=false`, and that boundary was preserved.
  - Jason therefore could not directly query Datto EDR/AV APIs or portal data outside the governed capability layer, even though that provider data was the authoritative source needed to identify the detection.
  - No governed alert-resolution/remediation capability was identified during this investigation for safely closing the Datto Endpoint Security alert after verification.
- **Observed workaround and why it is insufficient:**
  - Jason searched local Datto AV files, Windows Application/System events, quarantine-like folders, and Infocyte/HUNTAgent logs using approved read-only PowerShell.
  - This successfully established current product health and found historical evidence that the Datto AV engine had previously reported `not connected`.
  - It did **not** expose the authoritative provider threat record for `15884344`.
  - The exact alert ID was not found in recent local Datto AV files, Windows logs did not contain a corresponding threat/quarantine/remediation event, and the local quarantine search found only the SDK legal/license directory rather than an authoritative quarantine record.
  - This filesystem/log approach is useful supplemental evidence but should not be the primary method for determining the disposition of a managed AV detection.
- **Expected behavior:** Jason should have a governed, read-only Datto Endpoint Security capability that accepts an RMM alert identifier or Endpoint Security alert ID and returns the authoritative threat record, including available threat name, classification, affected object, IOC/hash, detection timestamp, action/disposition, quarantine/remediation state, and current resolution state. A separately governed mutation capability should exist for supported remediation or alert resolution when policy and approval allow it.
- **Recommended capability design:**
  - Read-only capabilities such as `endpoint.security.threat.search`, `endpoint.security.threat.read`, and `endpoint.security.quarantine.read`.
  - Selectors should support `device_uid`, RMM `alert_uid`, and provider `es_alert_id`.
  - Output should normalize provider fields into a canonical threat record while retaining provider evidence references.
  - Read capability should remain low-risk and not require per-run approval.
  - Any remediation, quarantine release, delete, isolate, or alert-resolution action should be a separate governed write capability with explicit risk classification and appropriate approval policy.
  - No design should require setting `direct_provider_access=true`.
- **Verification required for closure:**
  1. Using only Jason governed capabilities, query `AOT-50282` alert `bd0882e0-8700-4985-ad89-f789b865c76e` or `esAlertId 15884344`.
  2. Return the provider-native threat name/classification.
  3. Return the affected object/path and IOC/hash when the provider supplies them.
  4. Return the action/disposition and quarantine/remediation state.
  5. Correlate the threat record back to the RMM alert and Autotask ticket.
  6. Demonstrate the same capability against a second controlled Endpoint Security alert.
  7. Confirm all reads work with `direct_provider_access=false`.
  8. If an alert-resolution capability is implemented, prove that it requires the intended approval/authority and verifies provider readback after mutation.
- **Last observed:** 2026-09-18 during antivirus investigation of `AOT-50282`.

---
