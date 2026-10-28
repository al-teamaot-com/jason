# Jason JSON playbook conversion — source-preserving drafts
**Audit date:** October 28, 2026  
**Change type:** Draft PR documentation and inert JSON source data **only**  
**Review:** https://github.com/al-teamaot-com/jason/pull/2111

## Outcome
All **16** entries in `implementation/autonomous_remediation/playbook_registry.json` have a separate JSON v1 **conversion draft** under `docs/playbooks/json/candidates/`.

- The original playbook Markdown has been preserved, reconstructed and checked in JSON as an inert source document (`source_document.prelude_markdown`, `source_document.sections[]`).
- Domain-specific diagnostic subsections, remediation branch text, safety checklists, retry and verification sections are also extracted into structured `procedure` fields **without executable capability mapping**.
- Every candidate conforms to the *review-only* JSON v1 envelope and passes static JavaScript checks for JSON parsing, step-graph reachability/acyclicity, minimum fields, source reconstruction, absent executable remediation, and `autonomy.activation=disabled`.
- All candidates are `lifecycle=pilot`, have **no JSON runtime activation**, no allowed capability actions, and stop in human review in their preview step graph.
- **No production JSON runtime registry was modified.** No live Jason playbook was staged, activated, promoted, replaced or deployed. The original production behavior remains governed by its existing source registry and runtime.
- The *canonical Python semantic validator* and live runtime worker parity **have not yet been executed/proven**. Do not claim these source conversion drafts are production-ready executable playbooks.

## Converted playbook inventory

| Playbook | Registered version | Legacy autonomy declaration | Missing original sections | JSON draft |
| --- | --- | --- | --- | --- |
| `backupiq_endpoint_backup` | `1.2.0` | autonomous | None detected | [draft](./candidates/backupiq_endpoint_backup-1.2.0-jsonpreview.json) |
| `datto_edr_av` | `1.3.0` | autonomous | None detected | [draft](./candidates/datto_edr_av-1.3.0-jsonpreview.json) |
| `disk_bad_block_event_7` | `1.0.0` | autonomous | None detected | [draft](./candidates/disk_bad_block_event_7-1.0.0-jsonpreview.json) |
| `dns_agent_diagnostic` | `1.0.0` | autonomous | §23 | [draft](./candidates/dns_agent_diagnostic-1.0.0-jsonpreview.json) |
| `drmm_recent_alert_reconciliation` | `1.0.0` | autonomous | §20, §21, §22, §23 | [draft](./candidates/drmm_recent_alert_reconciliation-1.0.0-jsonpreview.json) |
| `gpt_insights_tech_assist` | `0.2.1` | autonomous | None detected | [draft](./candidates/gpt_insights_tech_assist-0.2.1-jsonpreview.json) |
| `idle_log_off` | `1.1.0` | autonomous | None detected | [draft](./candidates/idle_log_off-1.1.0-jsonpreview.json) |
| `jason_activity_log` | `1.0.0` | autonomous | None detected | [draft](./candidates/jason_activity_log-1.0.0-jsonpreview.json) |
| `low_disk_space` | `1.1.0` | autonomous | §23 | [draft](./candidates/low_disk_space-1.1.0-jsonpreview.json) |
| `offline_ticket_context_augmentation` | `0.1.0` | shadow | None detected | [draft](./candidates/offline_ticket_context_augmentation-0.1.0-jsonpreview.json) |
| `post_error_investigation` | `1.0.0` | autonomous | §23 | [draft](./candidates/post_error_investigation-1.0.0-jsonpreview.json) |
| `security_log_self_heal` | `1.0.0` | autonomous | §23 | [draft](./candidates/security_log_self_heal-1.0.0-jsonpreview.json) |
| `unexpected_shutdown` | `1.1.0` | autonomous | None detected | [draft](./candidates/unexpected_shutdown-1.1.0-jsonpreview.json) |
| `vulscan_missing_patch` | `1.1.0` | autonomous | None detected | [draft](./candidates/vulscan_missing_patch-1.1.0-jsonpreview.json) |
| `vulscan_multi_device_split` | `1.0.0` | autonomous | §23 | [draft](./candidates/vulscan_multi_device_split-1.0.0-jsonpreview.json) |
| `windows_time_source` | `0.1.0` | shadow | None detected | [draft](./candidates/windows_time_source-0.1.0-jsonpreview.json) |

The existing v1 JSON schema and validator: [playbook-v1.schema.json](./playbook-v1.schema.json) and `implementation/autonomous_remediation/playbook_document.py`. The common operational playbook design contract remains [Jason-Playbook-Runtime-Automation-Contract.md](../Jason-Playbook-Runtime-Automation-Contract.md). The [JSON Playbook Runtime](../Jason-JSON-Playbook-Runtime.md) explicitly requires incremental migration and per-playbook acceptance, not unverified mass activation.

## Source issues requiring review

1. **BackupIQ version drift:** `docs/playbooks/Jason-BackupIQ-Datto-Endpoint-Backup.md` declares **1.3.0**, while the source registry declares **1.2.0**. The JSON draft has a registry-based `1.2.0-jsonpreview` identity but preserves and labels the document version; do **not** assert equivalence until reconciled.
2. **Missing source sections:** `dns_agent_diagnostic`, `low_disk_space`, `post_error_investigation`, `security_log_self_heal`, and `vulscan_multi_device_split` lack canonical Section 23 in their source. `drmm_recent_alert_reconciliation` lacks Sections 20–23. Drafts explicitly retain `missing_in_source_needs_author_review`; they do not fabricate owner approval or acceptance.
3. **EDR/AV lineage:** The registered `datto_edr_av` source is Python at `implementation/autonomous_remediation/datto_edr_av_playbook.py`. The JSON source-preserving draft uses the corresponding human playbook at `docs/playbooks/Jason-Datto-EDR-AV-Diagnose-Repair.md` and retains the Python path in `legacy_registry.source_path`. It is *not* an automatic Python-to-JSON behavior port.
4. **Execution gap:** Repository inspection found `JsonPlaybookInterpreter` returning instructions and unit-test coverage, but no verified integration into Jason's current autonomous worker. Existing v1 input bindings for current ticket/client/device/alert selectors, evidence freshness and result verification are not acceptance-proven. Without those, literal declarative steps would be unsafe.
5. **Waiting/recheck mismatch:** The existing v1 document validator forbids cyclic step graphs. Long-running operational playbooks require durable rechecks; the existing shared runtime must own scheduling and resumption, not a second embedded loop.
6. **Live acceptance unknown:** GitHub registry autonomy flags describe source intentions, not independently verified current durable promotions and end-to-end behavior. The [October 28 Development & Release Control Board](https://github.com/al-teamaot-com/jason/issues/526) reported production health as requiring fresh host revalidation.

## Next controlled acceptance steps

1. Run the repository's **canonical** `validate_playbook_document` with each JSON candidate and compare exact registered capability names. Retain the current disabled preview status.
2. Reconcile source-version and missing-section issues *in documentation first*, without inventing automation authority.
3. Define exact provider-target and evidence-fact bindings via **existing** Central Orchestrator, shared ticket-work-start lifecycle and verified Autotask/DRMM identities. Do not interpolate arbitrary commands or URLs.
4. Prove a bounded real JSON-driven workflow for **one** low-risk playbook in shadow against controlled synthetic and live-read scenarios. Include negative evidence, cross-client rejection, waiting/retry persistence, duplicate suppression, terminal readback, and proof that no new write occurs.
5. Only after true runtime parity and verified acceptance, consider exact-version activation using Jason's existing Release Manager and separate owner-granted autonomy promotion. Preserve existing production playbook as rollback baseline until parity is proven.
6. Use the source snapshot and per-file blob references to detect future Markdown/registry drift rather than silently replacing reviewed JSON.

## Hard boundaries

- `direct_provider_access=false`
- No ad hoc shell, PowerShell or arbitrary provider URL execution from JSON.
- No new ticket, RMM, Entra, DNS, network, host, security or backup permissions from this conversion.
- No disruption, service restart, network reset, user logoff, reboot, or silent customer notification.
- No crossing tenant/company boundaries, no missing-approval fallback, and no production deployment as part of draft authoring.
