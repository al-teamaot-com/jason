# Jason Playbook — RocketCyber Alert Triage and Autotask Reconciliation

```yaml
playbook:
  id: RC-ALERT-TRIAGE-001
  name: RocketCyber Alert Triage and Autotask Reconciliation
  version: 0.1.0-design
  owner: AOT Security Operations
  target_type: ticket
  trigger:
    provider: autotask
    match: "queueID=29683485 (RocketCyber Alerts), nonterminal ticket; or newly received RocketCyber incident with exact client mapping"
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  classifications:
    - verified_benign
    - remediated_verified
    - active_threat
    - inconclusive
    - identity_blocked
    - dependency_blocked
    - duplicate_correlated
  retry:
    max_remediation_attempts: 1
  recheck:
    enabled: true
    cadence: PT1H
    stale_after: P2D
  verification:
    authoritative_source: "Exact originating provider plus Datto EDR/RMM, Entra or other applicable independent evidence"
    success_condition: "Safe disposition confirmed; exact Autotask ticket and provider incident reconciliation verified"
  completion:
    terminal_disposition: Complete
  autonomy:
    allowed_branches:
      - evidence_only_investigation
      - exact_false_positive_with_authoritative_corroboration
      - verified_remediation_with_approved_existing_playbook
      - internal_autotask_documentation
    approval_bound_branches:
      - account_or_role_changes
      - device_modifying_response
      - rocketcyber_provider_mutations_when_capability_enabled
    disruptive_branches:
      - endpoint_isolation
      - account_disable_or_session_revoke
      - security_log_clear
```

Design only; this manifest does **not** activate an unattended scheduler, enable a provider capability, or grant new execution authority. Inherit shared runtime semantics from `Jason-Playbook-Runtime-Automation-Contract.md` and the authoritative `Jason-Standard-Playbook-Template.md`.

## 1. Section Goal
Jason continuously admits RocketCyber-generated Autotask work, investigates it using current corroborated evidence, autonomously completes verified benign or verified remediated cases under existing standing-safe playbooks, and promptly escalates credible threats or missing authority. Success is measured by high coverage of first-pass triage, verified outcomes, no unjustified closure, no duplicate processing, and provider/ticket reconciliation.

## 2. Trigger
Nonterminal Autotask ticket in RocketCyber Alerts queue (ID `29683485`) or incoming RocketCyber incident that maps deterministically to an AOT client and a nonterminal Autotask ticket. Poll new and existing work at the approved Jason admission cadence; event triggers may supplement polling. Use pagination and resume cursors. Never infer that queue entry automatically establishes compromise.

## 3. Scope and Boundaries
In: Autotask ticket/notes, RocketCyber incident IDs and state, Datto RMM/EDR evidence, approved Microsoft Entra sign-in/audit evidence, approved existing AV and Security Log Self-Heal playbooks, related CI/asset, duplicate/correlated alert sets, and governed internal notifications. Out: unapproved client communications, guessed user authorization, arbitrary scripts, bulk security settings, speculative closures, scope expansion to unrelated client/tenant, and bypass of approval. Preserve Central Orchestrator, `direct_provider_access=false`, exact requester grants, client isolation, protected-core gates, auditable bounded actions.

## 4. Initial Identification
Identify exact Autotask ticket ID/number, client/company, queue/status, RocketCyber incident ID, timestamp, affected device UID/hostname or Entra tenant/user, current ticket notes, related DRMM/EDR alerts, and all matching already-open tickets. Validate existing CI; when missing and applicable, resolve one active same-client CI before substantive diagnostics. For identity-only events document 'No applicable device association'. Ambiguous associations => `identification_blocked`. Before substantive work perform the shared work-start gate: move ticket to Jason queue, set In Progress/Remote Support as appropriate, and read back all changed fields. Waiting tickets retain ownership and release the active work slot. Do not claim ownership when this transition fails.

## 5. Expected State
No unexplained active threat or unresolved identity privilege/risk event. Endpoint protections operating and scans/events appropriately reviewed; security logs readable. Any actual malicious artifact is contained/remediated and independently verified. Benign events have a corroborated benign explanation. RocketCyber incident, Datto detection and Autotask ticket have consistent, separately verified dispositions, subject to each provider's actual supported writes and authority.

## 6. State Model
`detected -> owned -> identified -> diagnosing -> classified -> waiting | blocked | remediating | verifying | human_review | escalated | complete`. Persist tenant/company/ticket/provider/endpoint identifiers, correlation group, evidence fingerprint, detection times, active job ID, attempt count, authority/approval outcome, next recheck, last note fingerprint, disposition and verification timestamps. Crash/restart must resume without repeating completed actions.

## 7. Diagnostic Workflow
1. **Exact admission and duplicate matching** — Autotask `service.ticket.search/read/notes.search`; validate queue ID, nonterminal status and same-client incident ID. Group duplicates as one investigation but preserve distinct ticket dispositions.
2. **Provider incident state** — use governed RocketCyber incident read/search when *actually available*; record event/detection state, investigation conclusion, status and exact ID. If capability missing, explicitly `dependency_blocked`; ticket text is not a live RocketCyber read.
3. **Malware/EDR** — `endpoint.device.search`, `endpoint.security.status.read`, `endpoint.security.detection.read/search`, `endpoint.security.quarantine.search`, `endpoint.security.scan.history.search`. Require correct same-client asset, explicit quarantine record/status, meaningful scan result, related unresolved detections, execution evidence, source, and recency. 'Quarantine-file' by itself is not proof of a clean host. Treat provider-compromised as a security signal until corroborated.
4. **PowerShell/process alert** — inspect exact command line, URI/hash, process parent, execution identity, signed installer/approved tool evidence, EDR verdict, and recent related detections. Official-looking URL or clean AV scan alone is not proof of authorized deployment. If actor/deployment cannot be established, keep open.
5. **Security log clearing** — correlate Event 1102/wevtutil and monitoring health. Only use the approved Security Log Self-Heal playbook after online, identity, precheck and authority gates. Never treat a `SYSTEM` command or duplicate event alone as benign.
6. **Risky sign-in / international login** — exact Entra tenant/account, success/failure, MFA, conditional access, IP, device, location, user-confirmed travel/VPN and surrounding risky activity. MFA success is not proof of authorization. Missing tenant-scoped Entra audit capability blocks automatic closure.
7. **Privilege change** — compare actor, target, event timestamp, audit ID, current role membership, approved change and authorized administrator. Current account enabled state is not grant authorization. Unknown actor/approval => urgent human review.
8. **Severity and escalation** — make preliminary security escalation promptly when credible high-severity active threat/role compromise/critical visibility failure is identified, even while investigation continues. Do not wait for exhaustive triage to notify.

Record authoritative source and timestamp for each evidence question. Empty successful reads are negative evidence only for the exact requested scope; denied/failed reads are gaps.

## 8. Decision Gates
Require exact ticket/company/asset or identity match, correct current provider record, scope and authority, online endpoint when running a component, no conflicting job, approved maintenance window when needed, and sufficient evidence for the chosen classification. No cross-client or inferred Entra mappings. A modifying/disruptive action must pass existing action-specific approvals; playbook text never substitutes for approval.

## 9. Remediation
- **Read-only diagnosis and note:** Standing-safe; inspect, classify, document and retain source IDs.
- **Benign detector event:** Close Autotask only when independently supported by authorized business context or trustworthy provider disposition + process provenance and absence of contradictory evidence. Explain decision in one concise internal note. Do not silence future detections globally.
- **Quarantined malware:** Recheck execution, exact quarantine records, source/reentry and recent scan; invoke existing Datto AV playbook if its approved gates are satisfied. If offline, enter waiting; never falsely state clean. Missing isolation/quarantine mutation authority -> human-review approval.
- **Security log unhealthy:** Delegate to existing Security Log Self-Heal playbook; one repair max for unchanged episode, independently check readability and source alert.
- **Identity event:** No automatic acceptance merely from geography or MFA; verify audit and approval. Privilege changes, disabling users, MFA resets, session revocations require separate governed authority.
- **Provider reconciliation:** After verified Autotask closure, reconcile RocketCyber incident only with real, approved RocketCyber mutation capability and readback. When unavailable, create one cross-linked provider-reconciliation dependency, not a fictitious resolved state.
All component/job dispatches require terminal job and StdOut/StdErr verification.

## 10. Retry Policy
At most one modifying/remediation attempt per unchanged incident unless an existing specific approved playbook is stricter. Read-only transient connector retries bounded to two; never redispatch an existing active job. Contradictory results => investigate or escalate; fail closed on lost job output.

## 11. Periodic Rechecks
Check waiting cases hourly or on grounded event wake-up, bounded by work admission capacity. Endpoint availability recheck and current alert state determine resumption. Do not create duplicate scheduled jobs for ticket/incident. No repeated notes when observed evidence unchanged. Stop on complete, escalated, cancelled/retired, or expired authority.

## 12. Aging / Stale Condition
After 48 hours waiting (shorter for high-severity), examine offline/stale/retired/reimaged/renamed asset, missing account mapping and stale provider incident. Escalate high-impact evidence gaps immediately; aging alone never authorizes closure. Enforce the existing Jason-ticket >10-day Human Review policy when applicable.

## 13. Dependency Handling
Required but absent provider capability, tenant-scoped Entra audit access, CI mapping, missing approval or offline endpoint => record blocker, deduplicate related dependency, cross-link one issue, and retain persistent state. Current (2026-10-26) live MCP discovery does not expose RocketCyber incident read/update/resolve. AOT-tenant identity directory reads are present, but historical privilege-grant actor audit and tenant-scoped client sign-ins were not proven. Do not invent these abilities or attempt direct API bypass.

## 14. Documentation Requirements
One summary note per meaningful session or state change, with `STATUS`, `KEY EVIDENCE`, `WHAT JASON DID`, `NEXT ACTION/OWNER`, `JASON STATE`. Include exact ticket, client, endpoint/user, incident/alert IDs, source, time, evidence query or job/correlation ID, result, disposition and next recheck. Write one final resolution note and confirm ticket status readback. Never include secret values or unsanitized tokens. Deduplicate unchanged notes.

## 15. Failure Handling
Distinguish provider failure, access denial, empty result, stale detection, unexpected nonterminal result and evidence conflict. Record exact error and stopped branch. Keep case open; do not claim a provider incident closed merely because Autotask completed.

## 16. Escalation Criteria
Immediate urgent security notice for confirmed/suspected privilege compromise, active execution/persistence, malware with unconfirmed containment, disabled logging with uncertain cause, or cross-tenant identity anomaly. Human Review for missing audit actor, user authorization, inaccessible offline host after aging threshold, ambiguous CI, required destructive/disruptive action, unresolved provider reconciliation, or retry limit. Include specific next action, not a generic "investigate."

## 17. Verification
Read originating provider's current exact state, independent relevant endpoint/identity health, complete component/job output, all correlated alert state, and Autotask ticket status after write. Confirm no unexplained concurrent detections and correct company. Verification timestamp must be newer than remediation/incident event.

## 18. Completion Criteria
Exact episode/client established; benign/closed outcome proved or authorized remediation verified; active threats and unresolved gaps explicitly disposed; final note present; ticket status Complete read back. Provider incident status reconciled with separate readback when supported; if provider sync blocked, record dependency and never imply provider closure. Close only each exact ticket whose evidence supports it.

## 19. Final Resolution Note
Summary must include original signal and incident ID; classification and why; evidence sources/timestamps; remediation/job IDs or none; number of attempts; verification facts; exact ticket disposition; RocketCyber/Datto provider disposition or explicit reconciliation blocker; next action if applicable.

## 20. Required Capabilities
Available on 2026-10-26: `service.ticket.search/read/notes.search/note.create/update`, `endpoint.device.search`, `endpoint.alert.search`, `endpoint.security.status.read`, `endpoint.security.detection.read/search`, `endpoint.security.quarantine.search`, `endpoint.security.scan.history.search`, `automation.component.search/execute`, `automation.job.read`, `automation.job.output.read`; `identity.user.search` for connected tenant only. Required implementation gaps: governed RocketCyber incident search/read/resolve and current-status readback, client-tenant sign-in/role-change audit provenance, durable admission/schedule and persistent rechecks, canonical cross-provider object mapping and ticket CI association, secure early Teams escalation. Enable any additions through ordinary capability/release governance.

## 21. Acceptance Test
1. Seed or pick one real *known benign* SOC ticket with provenance; prove admission, CI or user identification, work-start transition, note, closure and Autotask readback.
2. Feed one Datto AV quarantine event with an offline endpoint; prove it waits, suppresses duplicate work, does not declare clean, and resumes on contact.
3. Feed paired 1102/wevtutil + unreadable log alerts; confirm correlation, approved Security Log Self-Heal delegation, limited attempts, health verification, and no unauthorized log-clearing.
4. Feed unknown Entra Global Administrator role grant; prove urgent escalation, no guess-based closure and client isolation.
5. Feed duplicate tickets for one incident; prove single investigation and exact per-ticket outcomes.
6. Prove a RocketCyber provider incident remains visibly pending while provider write is unavailable, then test exact provider read/resolve/readback after governed capability rollout.
7. Restart worker during waiting and verify persisted resume; test denied write and component output failure.
8. Demonstrate normal ticket updates/notes are persisted without manual re-prompting, with observability metrics in Jason/Grafana.
Never mark playbook production-enabled from this design PR alone.

## 22. Section Goal Closure
Only after code, governed capability and production scheduler deployment plus above controlled acceptance tests, capture merged SHA, release-manager/deployment record, test results, Grafana/Project Jason Section Goal update, residual blockers and owner acknowledgement. Unmerged or merged documentation alone is not acceptance.
