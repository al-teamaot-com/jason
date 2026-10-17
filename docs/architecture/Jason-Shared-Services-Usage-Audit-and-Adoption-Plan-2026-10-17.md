# Jason shared-services adoption and usage-based migration plan

**Recorded:** 2026-10-17 | **Tracker:** [TODO-ARCH-001 / #1535](https://github.com/al-teamaot-com/jason/issues/1535) | **Disposition:** Read-only plan, **blocked for development** until current production and Teams prerequisites are accepted.

## Scope and evidence

This is a **GitHub source/architecture audit**, not a complete measurement of live workflow frequency. On the reviewed main branch, `implementation/autonomous_remediation/playbook_registry.json` contains **16** enabled playbook definitions (**14 labelled production/autonomous; 2 labelled pilot/shadow**). Registry declarations do not independently prove live operation. The existing `docs/playbooks/Jason-Playbook-Runtime-Automation-Contract.md` enumerates **18** common playbook responsibilities. Eight additional cross-domain families bring the preliminary inventory to **26 responsibilities**, **not 26 missing/new services**.

Existing shared machinery includes `autonomous_remediation/{playbook_runtime.py,attention_scheduler.py,targeted_recheck.py}`, `runtime_service/src/jason_runtime/{autonomy_worker_runtime.py,technical_notes.py,managed_ticket_notes.py,universal_teams_approval.py}`, `orchestrator/{service.py,governed_execution_ledger.py,approval_delivery.py,approval_continuation.py,evidence_sanitization.py,evidence_interpreter.py,governed_evidence_cache.py}`, `kernel/client_boundaries` and governed provider adapters. The runtime worker is ~7,785 lines and procurement Teams flow ~3,082 lines; this indicates coupling risk **but not proof of duplicated functionality**.

Bounded repository code searches find the symbol `ApprovalRequestService` in 15 files, `SQLiteGovernedExecutionLedger` in 17, `TargetedWake` in 8 and `sanitize_evidence` in 12 **including definition/test files**. These counts measure source references **not production execution frequency**. The existing model `usage_ledger` records model calls and cannot alone count Autotask notes, approval decisions and retries. Live per-workflow invocation counts were not available from the read-only Jason status response.

## How to rank by actual usage

Collect a **30-day** tenant-scoped read-only baseline where available: per-capability and per-workflow invocation count; distinct consuming workflows and client tenants; initiating channel; approval, delivery, retry and failure frequency; duplicate write/notification attempts; runtime cost/latency; incident evidence; and exact deployed version. Treat unavailable values as **unknown**, never infer production counts from code search.

Priority among *eligible* work should reflect **breadth of use, frequency, security/customer/financial impact, observed defect reduction, proven duplicate logic, and bounded migration cost**. Support/P0 incidents, approval and dependency holds always override category rank. Provisional usage: **H** = mandatory or likely multi-workflow; **M** = repeatable but narrower; **L** = future/dependency-gated; these are **not measured frequencies**.

## Individual playbook responsibilities (18)

| ID | Behavior | Existing implementation / consumer evidence | Estimated breadth | Adoption decision |
| --- | --- | --- | --- | --- |
| PB01 | Trigger admission | `autonomous_remediation/autonomous_queue_worker.py; playbook_matching.py` | H | Existing shared gate; verify all playbook entrypoints (#770) |
| PB02 | Queue ownership | `autonomous_queue_worker.py; runtime/autonomy_worker_runtime.py` | H | Verify one durable owner per ticket (#770) |
| PB03 | Active-work capacity | `autonomous_remediation/attention_scheduler.py; WorkLedger` | H | Use central slot accounting; approval-pending frees slot (#770) |
| PB04 | Ticket work start | `runtime/autonomy_worker_runtime.py; Autotask work lifecycle` | H | Unify status/claim behavior only where divergent (#190/#770) |
| PB05 | Device/CI/user/site association | `connectors/resource_convergence.py; orchestrator/canonical_entity_correlation.py` | H | Reuse canonical match before diagnostics and verify before closure (#190) |
| PB06 | Tenant/provider boundary | `kernel/client_boundaries; orchestrator/service.py` | H | Mandatory existing tenant and authority gates (#1100) |
| PB07 | Persisted state | `runtime/autonomy_worker_runtime.py; SQLiteOperationalWorkStore` | H | Versioned migration adapters, never reset active jobs (#770) |
| PB08 | Evidence fingerprint | `runtime worker; orchestrator/governed_execution_ledger.py` | H | Align definitions for dedupe/idempotency, not blindly share incompatible keys (#605) |
| PB09 | Duplicate suppression | `runtime/managed_ticket_notes.py; runtime worker` | H | Reuse cross-origin semantic dedupe; verify closed #605 live adoption |
| PB10 | Waiting/rechecks | `autonomous_remediation/targeted_recheck.py; SQLiteTargetedWakeStore` | H | Adopt durable targeted wake; exact approval context (#607) |
| PB11 | Bounded retries | `attention_scheduler.py; targeted_recheck.py; runtime worker` | H | Standard retry shape, retain provider-specific rate limits (#607/#770) |
| PB12 | Correlation/job tracking | `orchestrator/governed_execution_ledger.py; work stores` | H | Carry exact IDs across requests, jobs, notes and resumes (#1100) |
| PB13 | Authority/disruption gates | `orchestrator/service.py; approval_requests.py` | H | Existing Central Orchestrator, not local permission decisions (#1468) |
| PB14 | Dependency handling | `targeted_recheck.py; TODO release bridge (different work domain)` | H | Share evidence contract, not the operational/engineering queues (#1196/#770) |
| PB15 | Technician documentation | `runtime/technical_notes.py; managed_ticket_notes.py` | H | Canonical note renderer; preserve special managed-note semantics (#605) |
| PB16 | Human-review handoff | `runtime/autonomy_worker_runtime.py; playbook contract` | H | One documented state and escalation readback (#190/#770) |
| PB17 | Terminal state readback | `runtime/autonomy_worker_runtime.py; Autotask adapters` | H | Independent Autotask ticket/CI verification before resolution (#190) |
| PB18 | Monitoring/telemetry | `runtime worker; usage_ledger; Grafana standards` | M | Need workflow counters; model-ledger cannot measure all actions (#1100) |

## Cross-system shared-service families (8)

| ID | Family | Existing implementation / consumer evidence | Estimated breadth | Adoption decision |
| --- | --- | --- | --- | --- |
| XS01 | Universal approvals | `connectors/src/jason_connectors/approval_requests.py; runtime universal_teams_approval.py; procurement flows` | H | Reuse #1468/#1440; wait for verified Teams P0; no competing approver |
| XS02 | Approval continuation/recovery | `orchestrator/approval_continuation.py; approval_recovery.py; playbooks` | H | Use durable single-use exact-scope resume (#607) |
| XS03 | Notification and audience routing | `runtime/teams_message_send.py; autonomous_completion_notification.py; autotask_client_notification.py` | H | Verify approved Teams and client delivery patterns (#697; #1468), do not merge audience policies |
| XS04 | Identity, tenant boundaries, secrets | `kernel/client_boundaries; Core Services Specification` | H | Use shared identity/authorization/secrets contracts; retain vendor adapters (#1100) |
| XS05 | Evidence integrity/source-of-truth | `orchestrator/evidence_sanitization.py; evidence_interpreter.py; canonical_entity_correlation.py` | H | Consolidate verified evidence/readback, avoid incorrect upstream masking (#436) |
| XS06 | Discovery and evidence caching | `orchestrator/governed_evidence_cache.py; provider_capability_discovery.py` | M | Measure repeated reads first; honor freshness, tenant/authority (#1510) |
| XS07 | Versions, releases and retirement | `Release Manager; #1078 and #866` | H for production | Keep current #1078 P0; full upgrades/retirement later (#866/#960) |
| XS08 | Cross-channel session continuation | `existing Teams flows; planned Jason Everywhere` | L | Channel-neutral contract; defer new voice/portal features (#1475) |

**Inventory control:** 18 playbook responsibilities + 8 cross-system families = **26**. First classify each as *already shared/verify*, *real adoption gap*, *legitimate domain-specific difference*, *missing contract*, or *unknown*. Do not write a replacement for a functioning central service.

## Migration waves: usage and risk before implementation effort

| Wave | Execution gate | Target reuse / action | Existing owner(s) |
| --- | --- | --- | --- |
| 0 — evidence | **NOW, read-only only** | Consumer-to-service inventory; source/version mapping; gather lawful production counters; classify missing metrics/true divergence | #1535 / architecture #1100 |
| 1 — preserve active P0 | **No added workstream** | Existing Production/Release Manager hardening, autonomous engineering readmission, Universal Teams approval/transport and business-result verification | #1078, #1196, #1440, #1468, #1493 |
| 2 — frequent ticket work | After wave 1 verified, existing architecture and concurrency gates clear | Select one representative eligible workflow; adopt central CI association, notes, waits, retry/approval resume, handoff, readback. Expand to other playbooks only after live parity | #190, #607, #605 (closed; adoption check), #770 |
| 3 — shared business/governance | After safe ticket migration and measured usage evidence | Reuse universal approval, role policy, notification audiences, event/evidence verification across procurement, QuickBooks, support and services; keep domain policy and transport adapters separate | #1468, #697 (closed), #436 |
| 4 — provider reuse | After confirmed measurable repeated reads and protected core readiness | Capability discovery, evidence cache/freshness, authoritative source reconciliation; no unauthorized cross-tenant cache reuse | #1510, #436, #1100 |
| 5 — platform evolution | Separately gated / lower urgency | Shared immutable version upgrade, dependency-safe retirement; channel-neutral Teams/voice/portal sessions when separately approved | #1078, #866, #960, #1475 |

### Bounded migration protocol for each selected consumer

1. Identify **original producer and exact consumers**, observed frequency, policy, tenant scope, current production build/version and relevant historical state. Confirm a real duplication or adoption gap before choosing code work.
2. Choose **the existing owning service**, not a second control plane; document versioned contract, idempotency key, identity/approval boundaries, data sensitivity, failure/timeout semantics, and old-client compatibility.
3. Add adapters for old callers; prove negative tests (wrong tenant, unauthorized/expired/replayed approval, changed payload, missing device association, provider timeout, duplicate webhook, worker restart, offline endpoint, partial/indeterminate write).
4. Shadow/dry-run *reads* or decisions where safe; **never duplicate live writes**. Introduce a reversible per-consumer flag/canary. Measure identical classification and evidence outcomes versus the old path.
5. Promote only through ordinary scoped PR, CI, Release Manager, exact commit approval and independently grounded production acceptance. Preserve in-flight tickets/approvals and compare receipts, notes, client communications and final Autotask state.
6. Retire legacy code only after accepted replacement, **zero active dependencies**, resolved pending jobs, documented rollback retention and #866's governed retirement criteria. Unknown = fail closed.
7. Update the owning original issue, the central inventory, and TODO/historical records. **PR merged != production accepted**.

### Acceptance tests / proof

- All 26 rows have named authoritative service ownership, current consumer inventory, *source-observed* and *live-verified* status, availability of metrics, migration necessity, and expected contractual differences.
- First canary demonstrates **no duplicate approval, provider write, Autotask note or notification**, same client/tenant policy and terminal state, exact restart-safe workflow state, independent readback, and a working rollback.
- Regression for all relevant registered playbooks and any migrated procurement/Teams flow; no new privileged execution, secrets, production changes, or client visibility broadened.
- For each later wave, measured call reduction/behavioral equivalence, one authoritative service per function and adoption proven by actual production consumers, rather than merely publishing a library.
- Keep the original domain owners (#190, #607, #1468, #436, #1510, #1078, #866, #1475); this issue coordinates cross-consumer **adoption only**. No parallel scheduler and no duplicate scope.

## Related non-disruptive P0 causal reconciliation use case (read-only)

[October 17, 2026 P0 Support List audit](../operations/Jason-P0-Incident-Correlation-Read-Only-Audit-2026-10-17.md) establishes 23 historical P0 rows, only 22 distinct recorded IDs (two unrelated records share `SUPPORT-OPS-046`), and two linked issues (#1317/#1313) closed on GitHub while Support rows remain Open. These facts justify **evidence-first incident correlation and status reconciliation** within existing self-heal #635 and Resolution Memory #951, not a separate incident/ticket/repair controller. Root-cause clusters remain hypotheses until independent fresh detector evidence confirms them.

**Non-impact sequencing:** Read-only inventory and cross-referencing now; defer code/adoption/automatic P0 state or ticket mutations until the active Production Manager, TODO worker and Universal Teams Approver acceptance gates permit it. Future consumer testing must include a real shared-cause case, an unrelated negative case, a reused Support ID, tenant/client segregation, recurrence and independent post-fix original-detector readback. Preserving current approved work is mandatory.

## Execution hold / TODO routing

**Block all new implementation/admission** until Production Manager #1078 is independently verified, engineering advancement #1196 works safely, and Universal Teams Approver #1440/#1468 with #1493 transport fix passes live approve/deny, replay/expiry and callback verification. Existing #1100/#1069 architectural gates still apply. Do not disrupt existing active work or bypass Release Manager/protected-core approval.

- **Canonical work ID:** `TODO-ARCH-001` (proposed staged backlog entry, category **Infrastructure & Engineering**, with cross-references from Security & Governance, MSP Operations, Integrations, Finance and User Experience).
- **Planning/engineering tracker:** [#1535](https://github.com/al-teamaot-com/jason/issues/1535).
- **What approval means today:** permission to inventory and record a plan **only**, not to launch code refactoring or production promotion.
