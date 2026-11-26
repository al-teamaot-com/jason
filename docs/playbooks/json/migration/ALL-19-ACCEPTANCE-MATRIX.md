# All 19 source-specific JSON candidates — evidence and open gates

## Section Goal
Show independently what is accepted, what is source-tested, and what remains unproven. This is NOT a production activation request.

## Canonical source reconciliation

| Legacy ID | Candidate version | Source-only validation | Full behavioral parity | Isolated live provider |
|---|---|---|---|---|
| backupiq_endpoint_backup | `1.3.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| client_information_request | `1.0.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| datto_edr_av | `1.3.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| disk_bad_block_event_7 | `1.0.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| dns_agent_diagnostic | `1.0.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| drmm_recent_alert_reconciliation | `1.0.0-migration.1` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| gpt_insights_tech_assist | `0.2.1-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| idle_log_off | `1.1.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| jason_activity_log | `1.0.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| low_disk_space | `1.1.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| offline_ticket_context_augmentation | `0.1.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| post_error_investigation | `1.0.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| security_log_self_heal | `1.0.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| unexpected_shutdown | `1.1.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| unsupported_readonly_triage_note | `1.0.0-migration.1` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| unsupported_triage_human_review | `1.0.0-migration.1` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| vulscan_missing_patch | `1.1.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| vulscan_multi_device_split | `1.0.0-migration.2` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |
| windows_time_source | `0.1.0-migration.1` | Schema, interpreter and exact legacy authority PASS | NOT ACCEPTED | NOT VERIFIED |

## Unresolved per-source gates

### backupiq_endpoint_backup
Source: `docs/playbooks/Jason-BackupIQ-Datto-Endpoint-Backup.md`
Candidate: `docs/playbooks/json/migration/candidates/backupiq_endpoint_backup.v1.json`
Immutable candidate fingerprint: `18d2ab42682ac126e346b9d34adb758e1340e8b9f28edc647de348d435906562`
The following are **unresolved** and must not be counted as passing acceptance:
- OpenBao-backed verified backup_net customer-to-Autotask company binding and zero-asset customer proof not yet connected to JSON runtime
- Original provider asset, backup success and alert result parser normalization, existing agent components/site variable reads and linked job output not fully wired
- Durable one-reinstall job and 1-hour/10-day waiting state and reverse-recheck/readback continuation must be proven
- Exact one authorized reinstall and post-install new backup/current alert verification plus ticket note/provider readback not accepted in isolated preproduction
- Potential BackupIQ false-positive provider statuses and protected asset exceptions need independent synthetic/live acceptance

### client_information_request
Source: `docs/playbooks/Jason-Client-Information-Requests-Round1.md`
Candidate: `docs/playbooks/json/migration/candidates/client_information_request.v1.json`
Immutable candidate fingerprint: `a1848fe643728391707e1dc35096811cffcc7749d49738835ca0ae4d193430f5`
The following are **unresolved** and must not be counted as passing acceptance:
- Exact resumed originating playbook authority from persisted worker state not fully composed with JSON runtime
- Existing SQLiteClientQuestionLedger reservation, uncertain-send reconciliation, reply verifier and 10-day expiration not wired to JSON interpreter
- External notification provider write, independent new same-contact recipient history and note readback not accepted in isolated live preproduction
- Server-side immutable catalog body reconstruction and client profile/Owner promotion must be independently verified for source version and exact action
- One send per ticket/question/evidence fingerprint across crashes and duplicates needs full end-to-end acceptance

### datto_edr_av
Source: `implementation/autonomous_remediation/datto_edr_av_playbook.py`
Candidate: `docs/playbooks/json/migration/candidates/datto_edr_av.v1.json`
Immutable candidate fingerprint: `08cca798a22392ad71c94ce95a49ff988c735a30a6e9d13c982b9676c95d967c`
The following are **unresolved** and must not be counted as passing acceptance:
- Normal Python PlaybookRun persisted state and step-specific job identity not yet wired to canonical JSON interpreter
- Existing Python security threat classifier, clean-scan/detection/recurrence requirements need end-to-end JSON evidence normalization and approval integration
- Governed AV Force Update predefined command and recovery clean uninstall policy-gated branches are not executable by approved JSON capabilities
- 02:30 scheduled reboot/03:30 verification remain separately exact Owner-approved and MUST NOT be auto-dispatched
- Job reconciliation, protected source/JSON takeover, Autotask ticket notes and provider-connected preproduction acceptance not done

### disk_bad_block_event_7
Source: `docs/playbooks/Jason-Windows-Disk-Bad-Block-Event-ID-7.md`
Candidate: `docs/playbooks/json/migration/candidates/disk_bad_block_event_7.v1.json`
Immutable candidate fingerprint: `6bde35361a6732af1dd75e6ffe4ceef86f8a96ca91079a577a1edebb414ac427`
The following are **unresolved** and must not be counted as passing acceptance:
- Full original authored playbook includes alert resolution but original registry does NOT authorize endpoint.alert.resolve; exact-scope governed approval and source change needed
- Exact physical disk model/serial/HarddiskX mapping (Event 7) or POST firmware/WHEA/boot evidence requires independent controlled diagnostic job and source-scoped normalization
- Bounded provider component job status and useful StdOut readback, no duplicate execution, and available safe diagnostic capability must be independently validated
- Owner-promoted note/handoff and provider readback plus full outcome/restart tests pending
- Isolated provider-connected live preproduction acceptance pending

### dns_agent_diagnostic
Source: `docs/playbooks/Jason-DNSFilter-DNS-Agent-Diagnostic.md`
Candidate: `docs/playbooks/json/migration/candidates/dns_agent_diagnostic.v1.json`
Immutable candidate fingerprint: `a0f12074057afef7a1583a0f0f849ce88aef3980ec1bf96051df73d3b6b17a55`
The following are **unresolved** and must not be counted as passing acceptance:
- Dedicated diagnostic component stdout and both service states exact parser, native client-safe DNSFilter site/agent/policy posture integration incomplete
- Existing standing-approved diagnostic component UID is bound in persisted state but provider job execution/orchestrator/authorization must be independently validated
- Exact registered install/reinstall component versions, customer-scoped OpenBao keys, one uninstall/install cycle and no network changes need side-effect readback and explicit promotion
- Full post install/reinstall service-manager DNS health check, DRMM exact alert resolution and ticket readback not yet independently accepted
- Failure/retry/reboot denial, restart and cross-tenant scenario tests need isolated real provider preproduction
- Original legacy registry does not authorize endpoint.alert.resolve; healthy state cannot complete the original alert/ticket until separate exact-scope authorization and source amendment. The JSON healthy branch currently goes to Human Review.

### drmm_recent_alert_reconciliation
Source: `docs/playbooks/Jason-DRMM-Recent-Alert-Reconciliation.md`
Candidate: `docs/playbooks/json/migration/candidates/drmm_recent_alert_reconciliation.v1.json`
Immutable candidate fingerprint: `53753e4f1d69f243f614c52b82de44384626a06e16d3686b0762c99127507055`
The following are **unresolved** and must not be counted as passing acceptance:
- Single registered endpoint_security_threat_ctx verifier relies on existing Python verifier and trusted normalized facts from Datto provider; no JSON-bound governed verifier capability proven.
- The current JSON interpreter cannot provide durable 24-hour sweep scheduling, alert-item iteration, provider result-to-fact mapping or multi-alert fanout.
- After creating an internal resolution note the legacy worker immediately updates the ticket without independent note readback; broader new readback requirement must be defined and parity-tested before acceptance.
- The existing worker does not expose general exact-owner promotion as an explicit internal gate; the JSON candidate adds a conservative gate and requires existing Central Orchestrator enforcement.
- No actual isolated end-to-end shadow, provider write, nor unattended ticket completion acceptance has been performed.

### gpt_insights_tech_assist
Source: `docs/playbooks/Jason-GPT-Insights-Tech-Assist.md`
Candidate: `docs/playbooks/json/migration/candidates/gpt_insights_tech_assist.v1.json`
Immutable candidate fingerprint: `2f7f8c15d3e233284270e55a38a838cf7a09ff11ddc1c08ef81a2915e280fe51`
The following are **unresolved** and must not be counted as passing acceptance:
- Exact same-company CI and endpoint optional governed read composition and network-specific PowerShell evidence collection
- Full bounded same-company related-ticket correlation and source Recurring exclusion integration
- Persisted augmentation state and no-duplicate source-version wake/recheck composition
- Per-provider exact owner-promoted internal note update, creator guard and authoritative post-write readback
- Full shadow end-to-end acceptance against live client-scoped provider connection

### idle_log_off
Source: `docs/playbooks/Jason-Windows-Idle-Log-Off-Compliance-Repair.md`
Candidate: `docs/playbooks/json/migration/candidates/idle_log_off.v1.json`
Immutable candidate fingerprint: `6520da707d310448b15de77d01b4fbc92e5fdaaf7c4156c83297737665884cf4`
The following are **unresolved** and must not be counted as passing acceptance:
- Source original registry does NOT authorize endpoint.alert.resolve, despite authored document; exact separate approved grant/source amendment needed
- Exact current client/site required idle duration, component version and variables must be bound through live governed site policy and Owner promotion
- Monitor provider output/UID/cadence and setter job/error response must be fully parsed into trusted JSON source facts
- One setter lifecycle, existing job polling, monitor normal 15-minute refresh and exact completion readback require end-to-end isolated acceptance
- No provider-connected preproduction or live confirmation of same client/role/CI and no production dispatcher selection tested

### jason_activity_log
Source: `docs/playbooks/Jason-Activity-Log.md`
Candidate: `docs/playbooks/json/migration/candidates/jason_activity_log.v1.json`
Immutable candidate fingerprint: `84755d1fc0bccc58ca34dd27dcb536ebd47d03a6d0aee95a2c8bb40137dccdb6`
The following are **unresolved** and must not be counted as passing acceptance:
- No live versioned internal persisted activity read adapter attached to the JSON interpreter
- The JSON v1 runtime does not orchestrate multiple consecutive rollover chunks as one durable batch
- No exact owner-promoted provider write/readback acceptance of create/update through this candidate
- No independent continued/changed source-state and reboot recovery acceptance with real Autotask session

### low_disk_space
Source: `docs/playbooks/Jason-Windows-Low-Disk-Space.md`
Candidate: `docs/playbooks/json/migration/candidates/low_disk_space.v1.json`
Immutable candidate fingerprint: `8ddfe6f27137480d72b22e750ad9b1b8953e1cd73309b73a46ab12b632622959`
The following are **unresolved** and must not be counted as passing acceptance:
- Trusted read-only multi-command volume/large-file/VSS/physical disk evidence collection and parser fanout incomplete
- Exact 15-minute existing Autotask cleanup grace and DRMM alert scoping plus current volume policy threshold
- Only approved versioned Sysmon component after individual job plan and durable one-attempt lock
- Complete job status and output read, per-device monitor/current free-space evidence, ticket note and terminal readback
- Full restart/recheck, provider failure, protected role and live isolated preproduction acceptance

### offline_ticket_context_augmentation
Source: `docs/playbooks/Jason-Offline-Ticket-Context-Augmentation.md`
Candidate: `docs/playbooks/json/migration/candidates/offline_ticket_context_augmentation.v1.json`
Immutable candidate fingerprint: `feeb7e6e0379487f65906a712d1955d1e7da97769ce6a57aaaa17a91f82dd698`
The following are **unresolved** and must not be counted as passing acceptance:
- 10-minute source-version conditional recheck and durable augmentation state
- same-site role refresh, active fixed-server read-only Get-NetIPConfiguration witness and complete evidence correlation
- per-company exact DEB asset selection identity and all uncertainty branches
- approved internal note creation, deterministic technical note renderer and no-duplicate provider note readback
- full worker source-to-JSON isolation and live preproduction provider acceptance

### post_error_investigation
Source: `docs/playbooks/Jason-Windows-POST-Error-Investigation.md`
Candidate: `docs/playbooks/json/migration/candidates/post_error_investigation.v1.json`
Immutable candidate fingerprint: `6d93920c32e13583c40a74fee13d31d72dc7d2c7f3744a645836d390a0b2f9cc`
The following are **unresolved** and must not be counted as passing acceptance:
- Full original authored playbook includes alert resolution but original registry does NOT authorize endpoint.alert.resolve; exact-scope governed approval and source change needed
- Exact physical disk model/serial/HarddiskX mapping (Event 7) or POST firmware/WHEA/boot evidence requires independent controlled diagnostic job and source-scoped normalization
- Bounded provider component job status and useful StdOut readback, no duplicate execution, and available safe diagnostic capability must be independently validated
- Owner-promoted note/handoff and provider readback plus full outcome/restart tests pending
- Isolated provider-connected live preproduction acceptance pending

### security_log_self_heal
Source: `docs/playbooks/Security-Log-Self-Heal-Playbook.md`
Candidate: `docs/playbooks/json/migration/candidates/security_log_self_heal.v1.json`
Immutable candidate fingerprint: `76e458c394689a153fb43bfd3b911b341324528231344058e9811f5e1f7ca959`
The following are **unresolved** and must not be counted as passing acceptance:
- Security Log self-heal clears security audit history and requires exact authenticated Owner approval bound to production-sensitive component and current incident, not merely a generic standing-safe label
- Original registry does NOT authorize endpoint.alert.resolve or SOC/EDR alert cleanup; full authored side-effect cleanup and original-alert resolution cannot execute without separately governed source amendment
- Secure exact SOC correlation of all event-log-cleared side effects and original ticket closure must be implemented through existing governed provider readback
- Independent fresh Quick Test after one Security Log Self-Heal job requires separately persisted job identity and output, no speculative command replay
- No isolated real-provider preproduction approval, safe target or production Core coexistence acceptance has been verified

### unexpected_shutdown
Source: `docs/playbooks/Jason-Windows-Unexpected-Shutdown-Site-Correlation.md`
Candidate: `docs/playbooks/json/migration/candidates/unexpected_shutdown.v1.json`
Immutable candidate fingerprint: `c23b8ed6c8091e291704daa5ec18a2696715af6a89780f0030d8d6efd1f40e61`
The following are **unresolved** and must not be counted as passing acceptance:
- Bounded all-same-company site peer enumeration and exact ±15 minute grouping is not wired into the JSON runtime
- Read-only five-command per-device event/WHEA/physical disk/reliability/volume telemetry and parser fanout is not connected end-to-end
- All device health observations and protected host branch need independently reviewed current source fingerprints
- Durable 30-day recurrence and 15-minute site incident recheck not wired into existing JSON scheduler
- Approved exact note and ticket actions and provider readbacks not independently validated in live isolated preproduction

### unsupported_readonly_triage_note
Source: `docs/playbooks/Jason-Unsupported-ReadOnly-Triage-Note-Pilot.md`
Candidate: `docs/playbooks/json/migration/candidates/unsupported_readonly_triage_note.v1.json`
Immutable candidate fingerprint: `d0b54b17155b7126226242d462ccb8db3180654a244a5ce92ab8e1bb219f7ad7`
The following are **unresolved** and must not be counted as passing acceptance:
- Legacy gather_unsupported_triage classification and note rendering remain Python worker logic and have not yet been migrated as reusable registered capabilities.
- Existing interpreter has no durable next_due_at/throttled retry/recheck scheduler, so blocked step does not implement legacy waiting state.
- Trusted adapter must derive source-version, company identity, fingerprint ownership, note history and promotion from governed results; externally supplied facts are not authority.
- Current candidate covers note publication/update path only; no claim of complete legacy-vs-JSON behavioral parity or live shadow acceptance.

### unsupported_triage_human_review
Source: `docs/playbooks/Jason-Unsupported-Triage-Human-Review-Handoff-Pilot.md`
Candidate: `docs/playbooks/json/migration/candidates/unsupported_triage_human_review.v1.json`
Immutable candidate fingerprint: `5c8388351ff72d0cbe8e8bac7950c8b99f27bff310f61ff7ae7c2197ade2c662`
The following are **unresolved** and must not be counted as passing acceptance:
- Current interpreter does not persist or enforce the declared workflow state, retries, queue/status field allowlist or live readback.
- A trusted orchestrator must supply fresh facts after each capability call; synthetic facts alone do not prove provider integration.
- No live acceptance or behavioral parity against production ticket write has been performed.
- Source action arguments now match the legacy worker: payload.id/queueID/status; pre-read uses resource_id and page_size=2. Actual returned jasonVerification.verifiedFields remains an external trusted fact and has not been mapped from adapter output.

### vulscan_missing_patch
Source: `docs/playbooks/Jason-Windows-Update-VulScan-Missing-Patch.md`
Candidate: `docs/playbooks/json/migration/candidates/vulscan_missing_patch.v1.json`
Immutable candidate fingerprint: `a486a0561d85d6fa3b3af90f61512ea6b43d927d5f0670ba79fe2c1bcdb44022`
The following are **unresolved** and must not be counted as passing acceptance:
- The authored Windows Update repair and patch install require automation.component.execute, which original registry does NOT authorize; cannot make that JSON action executable without separately governed authority
- Exact KB supersedence and update install-error data parse, Patch Window policy and 10-day persisted state must be integrated with JSON interpreter
- Normal user session, safe reboot timing and protected servers require separately approved action and source
- Multi-device VulScan source must use existing ticket split primitive and verified child creation instead of direct JSON fanout
- Owner-promoted exact note/optional client notification/terminal ticket readback and real isolated preproduction acceptance remain incomplete

### vulscan_multi_device_split
Source: `docs/playbooks/Jason-VulScan-Multi-Device-Split.md`
Candidate: `docs/playbooks/json/migration/candidates/vulscan_multi_device_split.v1.json`
Immutable candidate fingerprint: `c3b693dd1d5ee17309a8281ef21d3cee5ccad4893e5c0f9f6fa7062a3c6ab318`
The following are **unresolved** and must not be counted as passing acceptance:
- JSON v1 interpreter lacks persisted foreach-target orchestration and source-version-aware resume; must REUSE existing TicketSplitExecutor, never implement duplicate engine
- No independently verified Owner-promoted real provider child creation/readback for all nodes in isolated preproduction
- Source ticket claim -> child creates -> note -> completion entire transactional/saga boundary not yet wired end-to-end
- Interrupted or uncertain child create reconciliation must confirm exact marker/provider child before any retry
- Full source lineage and source-completion rollback/partial failure tests not yet accepted

### windows_time_source
Source: `docs/playbooks/Jason-Windows-Time-Source-Self-Heal.md`
Candidate: `docs/playbooks/json/migration/candidates/windows_time_source.v1.json`
Immutable candidate fingerprint: `b75a183d829f7cb98c4b53a8813919e47ece77698d4fd8d6a5a8ee98ea983b44`
The following are **unresolved** and must not be counted as passing acceptance:
- Full Windows Time Self-Heal definition includes governed diagnostic component, domain-member remediation, per-action Owner approvals, bounded jobs/retries, exact alert and ticket readback, and protected DC/security branches; these are not represented in read-only shadow JSON.
- The current isolated preproduction composition is synthetic and has not been deployed or tested with a real client-bound provider session.
- No source-to-runtime activation/cutover or coexistence acceptance is authorized.

## Isolated source acceptance (not provider-connected)

All 19 canonical source documents are staged only as **drafts** in the same existing JSON SQLite registry, under a separate temporary test directory. Zero active JSON versions, zero new action grants, zero production dispatcher wiring, zero provider mutations. The shared source gate tests source SHA mapping, canonical schema, interpreter decision defaults, exact mutation allowlists, immutable staging/restart and synthetic classifiers. Passing these tests is **not** equivalence to per-source complete positive/negative/retry/readback/approval acceptance.

## Production boundary

Before activation: independently verify source-specific trusted client/provider fact adapters and a real isolated preproduction target, approved exact user/Owner authority, durable per-step retry/recovery/no-replay, exact action/readback, audit and rollback, and no duplicate legacy execution paths. Protected PMv4 Ticket Core and Stage E remain untouched.

**Totals: 19 detailed candidates, 0 structural drafts, 0/19 full parity accepted, 0 production activations, 0 legacy retirements.**
