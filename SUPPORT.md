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
- **Status:** Closed
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
- **Resolution verified:** 2026-09-22. In a fresh governed session, `service.ticket.search` for `T20260918.0005`, `service.ticket.read` for ticket `140629`, and `service.ticket.notes.search` all succeeded with `direct_provider_access=false`. The ticket is readable as status `5`, completed on 2026-09-18, and prior Jason-created internal verification notes are present. The original read-path blocker is no longer current.
- **Last observed:** 2026-09-18 during active antivirus troubleshooting on `AOT-50282`.

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
- **Status:** Closed
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
- **Resolution verified:** 2026-09-22. `endpoint.security.detection.read`, `endpoint.security.detection.search`, `endpoint.security.quarantine.search`, `endpoint.security.status.read`, and scan-history capabilities are active. Live governed readback of provider alert `c3aa92e3-92af-4c8f-889a-51bafa50790f` returned threat `EXP/CVE-2016-7228`, the affected XLS path, SHA-256, quarantine state, remediation state, response action, and the matching quarantine record while `direct_provider_access=false` remained enforced.
- **Last observed:** 2026-09-18 during antivirus investigation of `AOT-50282`.

---


### SUPPORT-CAP-004 — Missing governed Datto RMM alert-resolution capability blocks alert closeout

- **Priority:** P1
- **Status:** Fixed
- **Owner:** Jason Platform / Datto RMM Connector
- **Issue:** Jason can read Datto RMM alerts but has no governed write capability to resolve/close an alert after troubleshooting and verification are complete.
- **Production example:** `AOT-50282`, Datto RMM alert UID `bd0882e0-8700-4985-ad89-f789b865c76e`, Endpoint Security alert ID `15884344`, associated Autotask ticket `T20260918.0005`.
- **What Jason needed to do:**
  1. Resolve the exact Datto RMM alert `bd0882e0-8700-4985-ad89-f789b865c76e`.
  2. Supply a bounded closeout reason/evidence reference if the provider supports it.
  3. Read the same alert back after mutation.
  4. Verify `resolved=true`, capture `resolvedOn` / `resolvedBy` when available, and confirm the alert no longer appears in the open-alert set.
  5. Perform this through Central Orchestrator with `direct_provider_access=false`.
- **What was available:**
  - `endpoint.alert.search` and `endpoint.alert.history.search` for read-only alert inspection.
  - `management.alert.search` for broader read-only alert inspection.
  - Governed Datto component execution for endpoint diagnostics.
- **Exact blocker:**
  - `discover_capabilities` returned only read-only Datto alert capabilities.
  - No active write capability equivalent to `endpoint.alert.resolve`, `management.alert.resolve`, `endpoint.alert.update`, or a provider-specific Datto RMM alert-close action was exposed.
  - Because `direct_provider_access=false` is an intentional security boundary, Jason was not permitted to call Datto directly or use an unmanaged API/shell bypass to close the alert.
  - The user explicitly authorized closeout, but requester intent alone cannot create a capability that is absent from the governed registry.
- **Impact:** Jason can troubleshoot and verify endpoint health but cannot finish the operational workflow by clearing the RMM alert. This leaves resolved or likely-resolved conditions visible as active monitoring work and prevents true end-to-end playbook completion.
- **Expected behavior:** Expose a narrowly governed Datto alert-resolution action that targets one exact alert UID, requires the appropriate authority/approval, performs one provider mutation attempt, and requires provider readback before reporting success.
- **Recommended capability design:**
  - Capability: `endpoint.alert.resolve` or `management.alert.resolve`.
  - Required selector: exact `alert_uid`; optional `device_uid` as an additional target guard.
  - Optional bounded fields: resolution reason, evidence/correlation reference, ticket number.
  - No arbitrary alert editing.
  - One provider mutation attempt; no broad-credential fallback.
  - Post-mutation verification must confirm the exact alert is resolved and absent from open-alert results.
  - Keep `direct_provider_access=false`.
- **Verification required for closure:**
  1. Select a controlled Datto RMM test alert by exact alert UID.
  2. Resolve it through the governed capability.
  3. Confirm exactly one provider mutation attempt.
  4. Read the alert back and verify resolved state.
  5. Verify it no longer appears in `endpoint.alert.search(..., status='open')`.
  6. Prove an unauthorized or ambiguous alert target fails closed.
  7. Repeat using an Endpoint Security alert so the `AOT-50282` workflow is covered.
- **Current verification (2026-09-22):** `endpoint.alert.resolve` is now active, action-enabled, approval-required, and scoped by exact `alert_uid` with optional `device_uid`. The original `AOT-50282` threat alert is confirmed in resolved history (`resolved=true`, resolver `AT_AUTORESOLVER`) and no longer appears in the open-alert set. The missing-capability defect is fixed; a separate controlled mutation acceptance test should still be retained as regression evidence.
- **Last observed:** 2026-09-18 when the user explicitly asked Jason to close Datto RMM alert `bd0882e0-8700-4985-ad89-f789b865c76e`.

---

### SUPPORT-CONN-005 — Autotask closeout workflow blocked: ticket reads, internal-note write, status discovery, and verified completion unavailable

- **Priority:** P1
- **Status:** Mitigated
- **Owner:** Jason Platform / Autotask Connector
- **Issue:** Jason could not complete Autotask ticket `T20260918.0005` because the governed Autotask read path and the tested internal-note mutation path failed, while the ticket-update capability requires a tenant-specific numeric status ID and successful post-mutation readback.
- **Production example:** Autotask ticket `T20260918.0005`, internal ticket ID `140629`, associated with `AOT-50282`.
- **What Jason needed to do:**
  1. Read ticket `140629` and confirm its current state before mutation.
  2. Read or otherwise authoritatively resolve the tenant-specific Autotask status value representing **Complete**.
  3. Add an internal troubleshooting/closeout note documenting the AV/EDR findings and the Datto alert limitation.
  4. Update the exact ticket to Complete using `service.ticket.update`.
  5. Read the ticket back and verify the status change actually persisted.
  6. Confirm no unrelated fields changed.
- **Exact blockers encountered:**
  - `service.ticket.read` for ticket `140629` failed with `CAPABILITY_INVOCATION_FAILED`.
  - Earlier `service.ticket.search` for `T20260918.0005` also failed with `CAPABILITY_INVOCATION_FAILED`.
  - Earlier `service.ticket.notes.search` failed information release with `SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED` / `REQUEST_ACCESS`.
  - An explicitly authorized attempt to create an internal note on ticket `140629` through `create_autotask_internal_note` failed with:
    - `status=failed`
    - `error_code=CAPABILITY_INVOCATION_FAILED`
    - `provider_write_attempts=1`
    - `note_id=null`
  - The active `service.ticket.update` capability accepts a numeric `status` field, not a semantic value such as `Complete`.
  - The valid numeric Complete status is tenant-specific and was not available from a working governed read/metadata capability during this incident.
  - The ticket-update implementation requires requester-impersonated post-mutation GET readback and must fail if verification cannot be completed. With the Autotask read path broken, successful verified completion could not be guaranteed.
- **What Jason deliberately did not do:**
  - Did not guess a numeric Autotask status ID.
  - Did not mark the ticket complete without first being able to verify the intended status value.
  - Did not claim the failed internal-note mutation succeeded.
  - Did not bypass requester impersonation, use the service account as fallback authority, or call Autotask directly outside the governed path.
  - Did not bypass the required post-mutation verification contract.
- **Impact:** Even when endpoint troubleshooting is complete, Jason cannot reliably document the work and complete the corresponding Autotask ticket. This breaks the final stage of autonomous ticket handling and prevents deterministic closeout.
- **Expected behavior:** Jason should be able to resolve semantic ticket states such as **Complete** to the correct tenant-specific Autotask status ID, create an internal closeout note, perform one bounded ticket status update, and verify both mutations through provider readback.
- **Recommended remediation:**
  - Repair the governed Autotask read/authorization path described in `SUPPORT-CONN-001`.
  - Restore reliable `service.ticket.read`, `service.ticket.search`, and `service.ticket.notes.search`.
  - Restore the currently exposed `service.ticket.note.create` mutation path and its verification.
  - Add a governed read capability for Autotask ticket field metadata/status picklist values, or a provider-neutral semantic status resolver so Jason can request `Complete` without hard-coding tenant IDs.
  - Preserve the current safe `service.ticket.update` field allowlist and mandatory readback verification.
- **Verification required for closure:**
  1. Read a controlled ticket successfully.
  2. Resolve semantic status `Complete` to the authoritative current Autotask status ID without hard-coded guessing.
  3. Create an internal note and verify it exists.
  4. Update the controlled ticket to Complete through `service.ticket.update`.
  5. Verify the status through post-mutation readback.
  6. Confirm no unrelated fields changed.
  7. Repeat the sequence on a fresh session.
  8. Re-run the exact `T20260918.0005` closeout flow if the ticket remains open.
- **Current verification (2026-09-22):** The original ticket can now be searched, read, and its notes retrieved through the governed Autotask path. `T20260918.0005` is already completed, and Jason-authored EDR/AV verification notes are present. `service.ticket.note.create` and `service.ticket.update` are currently active governed write capabilities. Keep this item open only for the remaining semantic-status-resolution/fresh controlled mutation regression proof; the original read-path blocker is resolved.
- **Last observed:** 2026-09-18 when the user explicitly asked Jason to complete `T20260918.0005`.

---


### SUPPORT-CONN-006 — Autotask ticket company/contact reassignment unavailable through governed update

- **Priority:** P1
- **Status:** Open
- **Owner:** Jason Platform / Autotask Connector
- **Issue:** Jason can read an Autotask ticket and determine that it is associated with the wrong company/contact, but the governed `service.ticket.update` path does not currently permit or successfully apply company/contact/location reassignment.
- **Impact:** Jason cannot safely correct misassociated tickets before client-scoped troubleshooting or automation. This can block deterministic tenant isolation, configuration-item association, documentation lookup, billing context, and autonomous workflow execution.
- **Production example:** `T20260922.0017` (Network Device Discovery Gromelski And Associates Inc.).
- **Observed behavior:**
  - Incoming IT Glue notification created the ticket under Autotask company `Catchall` (company ID `1162`) because sender `notifications@itglue.com` is a Catchall contact.
  - Ticket body explicitly identifies the actual client as `Gromelski And Associates Inc.`.
  - DRMM site `Gromelski And Associates Inc.` independently maps to Autotask company ID `597`.
  - Governed update was attempted with `companyID=597`, `contactID=null`, and `companyLocationID=null`.
  - `service.ticket.update` returned `CAPABILITY_INVOCATION_FAILED`.
  - Authoritative readback confirmed `companyID=1162`, `companyLocationID=990`, and `contactID=30683770` remained unchanged.
- **Expected behavior:** A narrowly governed ticket-reassociation operation should allow Jason to move one exact ticket to an explicitly resolved Autotask company, clear or replace incompatible contact/location references, and verify the exact fields through post-mutation readback.
- **Safety requirements:**
  1. Resolve the destination company from authoritative evidence; never infer from fuzzy text alone.
  2. Require deterministic cross-provider evidence such as DRMM site -> Autotask company mapping, or another approved mapping source.
  3. Validate/clear incompatible contact and location references.
  4. Make exactly one bounded provider mutation attempt.
  5. Verify company/contact/location after mutation.
  6. Fail closed when client identity is ambiguous.
- **Verification required for closure:**
  1. On a controlled misassociated ticket, reassign to the correct company through Jason.
  2. Clear or replace the old Catchall contact/location as required.
  3. Read the ticket back and verify exact company/contact/location values.
  4. Confirm no unrelated ticket fields changed.
  5. Repeat using an IT Glue notification-derived ticket.
  6. Preserve `direct_provider_access=false`.
- **Operational workaround:** Document the authoritative client in an internal note and do not perform client-scoped writes based on the incorrect ticket company until reassignment is available.
- **Last observed:** 2026-09-22 on `T20260922.0017`.

---


### SUPPORT-CONN-007 — Autotask ticket CI association unavailable through governed ticket update

- **Priority:** P1
- **Status:** Open
- **Owner:** Jason Platform / Autotask Connector
- **Issue:** Jason can deterministically identify the correct Autotask configuration item for a ticket, but the governed `service.ticket.update` path does not currently attach that CI.
- **Impact:** Playbooks cannot enforce the AOT rule that tickets should be associated to the affected device when one is available. This reduces asset context, weakens automation safety, and forces technicians to repair ticket hygiene manually.
- **Production example:** `T20260918.0012` / `OWNSHOP412LT1`.
- **Observed behavior:**
  - DRMM uniquely identified endpoint UID `785e1f79-1572-4061-d01b-0f9ec931fae2`.
  - Autotask configuration search uniquely identified CI `1578` for the same endpoint.
  - Ticket `T20260918.0012` had `configurationItemID=null`.
  - Governed `service.ticket.update` attempted to set `configurationItemID=1578`.
  - Mutation returned `CAPABILITY_INVOCATION_FAILED`.
  - Authoritative ticket readback confirmed `configurationItemID` remained null.
- **Expected behavior:** Jason should be able to attach exactly one authoritatively resolved Autotask CI to one exact ticket through a bounded governed mutation with readback verification.
- **Safety requirements:**
  1. CI must belong to the same Autotask company as the ticket after authoritative client resolution.
  2. CI selection must be deterministic; no fuzzy best-match writes.
  3. Exactly one provider mutation attempt.
  4. Post-mutation readback must confirm the exact CI.
  5. No unrelated ticket fields may change.
- **Verification required for closure:**
  1. Use a controlled ticket with no CI and one uniquely matched endpoint/CI.
  2. Attach the CI through Jason.
  3. Read the ticket back and confirm the exact configurationItemID.
  4. Confirm no unrelated fields changed.
  5. Repeat on a VulScan or monitoring ticket.
- **Operational workaround:** Document the resolved CI in an internal note and use the DRMM UID/CI ID as evidence, but do not claim the ticket is asset-associated.
- **Last observed:** 2026-09-22 during controlled test of `T20260918.0012`.

---
