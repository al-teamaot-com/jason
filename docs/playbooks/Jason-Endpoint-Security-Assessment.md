# Jason Endpoint Security Assessment

Version: 0.1.0 | Owner: Atlantic Office Technologies | Lifecycle: draft/preproduction | Autonomy: disabled

Canonical template: docs/playbooks/Jason-Standard-Playbook-Template.md
Shared runtime: docs/playbooks/Jason-Playbook-Runtime-Automation-Contract.md

This playbook is **procedure, not authority**. It cannot activate itself or change production, grant provider permissions, bypass Central Orchestrator, or lift the production freeze.

## Playbook manifest

    id: endpoint_security_assessment
    name: Jason - Endpoint Security Assessment
    version: 0.1.0
    target_type: endpoint
    owner: Atlantic Office Technologies
    trigger: authenticated_technician_explicit_endpoint_assessment
    ownership: conditional
    retry.max_remediation_attempts: 0
    retry.max_component_dispatches: 1
    recheck.cadence: 120s
    recheck.stale_after: 15m
    verification.authoritative_source: Datto RMM exact device/job/output + managed AV + authorized diagnostics
    completion.terminal_disposition: verified_report_or_human_review
    autonomy.activation: disabled
    autonomy.allowed_branches: governed_read_only_evidence_and_internal_report
    autonomy.approval_bound_branches: component_execute, client_report_delivery
    autonomy.disruptive_branches: []

## 1. Section Goal

Technician asks "Jason, run an Endpoint Security Assessment on DEVICE and give me the AOT report." Jason resolves the correct client/device, runs the existing read-only sweep once under exact governed approval, investigates suspicious items independently, verifies each important fact, and delivers a polished AOT PDF to the authorized technician. Passing unit tests or an accepted job alone is not success. Completion requires live end-to-end technical evidence and authorized file delivery.

## 2. Trigger

One explicit authenticated technician request with exact, unique target hostname or provider UID. A request for general device status or security advice is NOT an instruction to dispatch this component. No unattended scheduled assessments are authorized by this version.

## 3. Scope and Boundaries

In scope: device/site/AV read, component search, bounded read-only component execution, terminal job/output readback, safe evidence-based follow-up, accurate finding disposition and branded PDF. Out of scope: full-disk scanning, active remediation, service/task disablement, quarantine, reboot, logoff, network reset, broad direct PowerShell, unauthorized client communication, provider shell/API bypass. Existing Central Orchestrator, exact requester permissions, client boundary, audit, retry and disruption policy remain binding; direct_provider_access=false.

## 4. Initial Identification

Resolve exactly one matching live endpoint using endpoint.device.search, then endpoint.device.read to verify exact hostname, provider UID and caller-authorized site. Verify exact component UID 8ff72744-cb29-4cad-a11b-7a1c2a199f06 and name Check RATs and Malicious Tools - AOT Ver 11042026 through automation.component.search. Reject duplicate, retired, mismatched and cross-client targets. Ticket-linked work inherits the global configuration-item association and Jason queue/In Progress/Remote Support work-start gates and readback. Do not create or claim a ticket for standalone report requests.

## 5. Expected State

Managed Datto AV independently reports RunningAndUpToDate; the read-only sweep completes and reports explainable findings; any suspected software can be classified from exact identity, path, signature and action semantics. Defender preferences being unavailable when Defender is inactive does not establish AV absence or presence. A partial/failed collector cannot be represented as an all-clear.

## 6. State Model

identified -> waiting_device / waiting_approval -> dispatched -> waiting_job -> investigating -> report_ready -> complete. Terminal exceptions: blocked, human_review.

Persist immutable request ID, requester, client, target, exact component UID, active job UID, recheck count, findings fingerprint, classification, report status and authorized audience. The state store belongs outside releases. Reserve a dispatch atomically before the provider action, do not redispatch ambiguous accepted jobs, and resume exact prior job across chats and restarts. Waiting releases active slots without losing ownership.

## 7. Diagnostic Workflow

Step 1: verify identity, authority, client and device status through endpoint.device.search/read.
Step 2: verify exact component from live catalog.
Step 3: read managed antivirus product/status from Datto device record, independent of Windows Defender.
Step 4: submit exactly one request to automation.component.execute through governed requester binding, no optional DeepFileHunt/MonitorMode flags. The playbook never manufactures explicit approval.
Step 5: poll automation.job.read on the returned job UID; retrieve stdout/stderr using exact job/device/component selectors after terminal completion; an accepted job is not success.
Step 6: parse bounded collector result. Preserve High/Medium/Low/Info source counts, coverage and scope. A preview ending in [bounded] is NOT full JSON regardless of output_bounded=false.
Step 7: investigate flagged tasks, services and startup entries using approved endpoint.powershell.read recipes. Require exact task/service identity, expected executable path, valid Authenticode signature, matching trusted signer and safe action arguments. Missing or conflicting evidence -> unresolved, not trusted.
Step 8: distinguish original heuristic severity from reviewed disposition: verified_expected, concern, unresolved. Unknown findings must not vanish in the PDF.
Step 9: render AOT report from normalized evidence. Client copy must be gated on complete finding-level evidence and confirmed protection; otherwise provide internal report prominently marked incomplete.
Step 10: deliver through existing authenticated technician file mechanism only after allowed audience and content hash verification.

## 8. Decision Gates

Requester authenticated and entitled to the client. Exact endpoint and component. Online before dispatch. Explicit exact per-run approval or separately Owner-promoted immutable playbook-scoped authorization. One-job invariant. Terminal output selectors validated. AV and finding evidence present. Content unavailable or authorization denied => fail closed. Do not bypass with direct API/shell or broader credentials.

## 9. Remediation

Not applicable. This is a report-only assessment. It cannot disable, remove, quarantine, reboot or alter endpoint software; remediation is a separate authorized playbook.

## 10. Retry Policy

Maximum one component submission per immutable request. Job polling may recheck without redispatch; up to 35 bounded polls. On ambiguous action acceptance, retain dispatched state and reconcile rather than resubmit. Read-only follow-up retries only on proven recoverable transport failure, with deduplicated recipe IDs.

## 11. Periodic Rechecks

Recheck accepted job roughly every 2 minutes (or platform backoff), only until completed/failed/cancelled, denied, stale or aborted. Retain job UID; suppress duplicate jobs and unchanged notes. Do not restart the scanner on delayed output.

## 12. Aging / Stale Condition

Active job older than 15 minutes: inspect authoritative job and agent state, not blind retries. If endpoint remains offline or stale, distinguish retired/replaced/duplicate provider objects from unreachable current hosts. Persist blocked state and narrow next step.

## 13. Dependency Handling

Missing component, permissions, exact signer, incomplete outputs, unsupported executable or PDF delivery route are explicit dependency states. Search existing linked tickets before creating a new authorized dependency, suppress duplicates, and never borrow facts from another client. Bounded V2 stdout can conceal Low/Info entries; a finding-level output contract or additional authorized evidence is necessary for client-ready publication.

## 14. Documentation Requirements

Keep exact requester/client/device/UID, component/job/correlation IDs, timestamp, original counts, inventory totals, current AV status, evidence class/signer/path/action, disposition, unresolved reasons, report revision/hash and changes made (None). Ticket-linked work uses standard technician-scannable notes and dedup; standalone reports do not create unsolicited tickets. Never retain secrets, raw unbounded output or user process command-line values.

## 15. Failure Handling

Explicitly record failed identity, inactive agent, ambiguous job acceptance, denied read, malformed JSON, missing finding-level detail, inconsistent counts, bad signature, unsafe action, unknown antivirus, PDF generation error and delivery failure. No all-clear on partial evidence.

## 16. Escalation Criteria

Corroborated malicious behavior, confirmed disabled protection, unknown suspicious execution after bounded safe checks, contradictory signatures, exact authorization denial, expired job/attempt budget or out-of-scope remediation. Escalate the actual unresolved condition, not known signed Lenovo/Datto software that Jason can verify.

## 17. Verification

Verify active managed AV via endpoint.device.read, exact terminal Datto job and non-error StdOut/StdErr, classification trace, scoped signed task/service evidence, complete actionable findings, and PDF content/render. A valid signature alone does not prove compromise absent. A PDF existing does not prove its facts.

## 18. Completion Criteria

For client-ready report: all High/Medium/Low actionable findings accounted for and dispositioned, no omitted findings, complete collector, protection verified, report generated and delivered only to authorized requester. If evidence remains unavailable, completion is a clearly labeled internal review and exact unresolved exception, NOT an unqualified client report. Terminal ticket-state transitions require separate provider readback where applicable.

## 19. Final Resolution Note

State hostname and client, managed protection, original and verified severity totals, what was checked, factual limitations, outstanding exceptions, changes made (None), job/correlation IDs, PDF revision/hash, technician next step only if truly necessary. No client-facing jargon such as "unexplained finding" when a valid investigation is possible.

## 20. Required Capabilities

Existing: endpoint.device.search/read, automation.component.search/execute, automation.job.read/output.read, endpoint.powershell.read, endpoint.security.status.read/detection.search. **Preproduction source now implements:** a disabled-by-default trio of exact MCP start/resume/PDF tools; requester- and site-bound persistent execution state; narrowly allow-listed automatic Lenovo and Datto follow-up reads; server-side governed output normalization into bounded per-finding pages; private PDF artifact storage and integrity checking; and a ReportLab runtime dependency. These source changes remain **not active** in the live Jason catalog.

**Remaining production integration:** authenticated end-user Teams/ChatGPT intent-to-tool acceptance with real Entra identities; background scheduler or same-turn bounded polling to complete delayed jobs without a new technician instruction; target/client authority acceptance; deployment packaging of the ReportLab dependency; preservation of report artifact bytes through actual MCP/client UI delivery; and a governed live run with proof of exact findings and no duplicate dispatch. A playbook is never a permission grant.

## 21. Acceptance Test

Safe fixtures: Al (OneNote startup), Al-Samsung (signed Defender/Datto and SMB tasks), CCPC-50960 (signed Lenovo Vantage + Datto EDR; MapS.bat unknown). Unit tests must cover exact client isolation, accepted job idempotence, same-job polling, restart resume, denied/failed provider read, false-positive vs true suspicious matching, incomplete output, AV independently verified, secret-safe report, no client PDF on unresolved, and workflow state persistence. One governed live pilot on an authorized AOT test endpoint is required before production promotion. No unrelated endpoint actions or tickets.

## 22. Section Goal Closure

Only after all required CI, preproduction and live acceptance, actual one-turn technician-to-report delivery proof, release SHA, verified rollback SHA, clean PMV3 release gates, permitted owner authorization, accurate Grafana/Project Jason status, and documented residual limitations. Tests and PR are intermediate milestones, not operational completion.

## 23. Autonomous Execution Eligibility and Owner Review

Version 0.1.0 nominates autonomy.activation=disabled. Component execution remains per-run approval-bound until separate owner promotion of exact playbook ID/version/policy, component UID/arguments, site/target scope and tests. Read-only diagnostics follow existing governed grants. No authority for disruptive or modifying actions. Client-facing publication remains a separate, explicit delivery permission. Production requires exact-candidate Owner authorization under PMV3.
