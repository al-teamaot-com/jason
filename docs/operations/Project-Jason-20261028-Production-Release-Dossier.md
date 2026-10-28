# October 28, 2026 — Governed full-scope release preparation dossier

**Purpose:** Review and integration evidence only. Stage A source was merged through PR #2127, but no production deployment, additional protected-main merges, Production Manager promotion, freeze exception, provider write or capability activation is authorized by this document.

**Generated UTC:** 2026-10-28T21:58:31+00:00
**Last independently observed live runtime/MCP revision:** `b40c2f4a47e60e31e2241e4a4d55759242c2b580` (both containers matched in read-only Docker inspection).
**Protected-main source baseline:** `1586dd9da10c23d7988d684a7c0b254c6353bef1` (PR #2127 Stage A merged).
**Stage A native Production Manager release candidate:** `release-1586dd9da10c23d7`, exact source `1586dd9da10c23d7988d684a7c0b254c6353bef1`, owner approval **false**. Native preproduction is pending. The first attempt was safely stopped because copying 28 GB of OpenClaw state and 3.1 GB of authority state to the 24 GB-free root disk would have exhausted space; the partial scratch was deleted and only the private preproduction scratch location was redirected to the separate local archive volume (199 GB available at start). No production container was restarted. The prior mainline `release-2a51d03464ef0d1b` PM record was `production_eligible` with owner approval false, but is superseded by this source merge; it was not deployed.

## Staged release order and immutable upstream references

1. **Reads A:** Merged PR #2127 as protected-main commit `1586dd9da10c23d7988d684a7c0b254c6353bef1`; isolated integration merge `f4a6d9563046e29bc0bfdaba984c851a66997b51`, source PR #2110 `70faec63315acbd71866322a19be2a955471e434`. Read-only company contains search and governed technician contract context. Time-entry read remains deny-by-default until native provider-specific requester authorization evidence.
2. **Routine RW B:** Current stacked PR #2128 review commit `0eca97fcc382e9090c8ea15878a18800e40fbac2` reconciles protected main after A; original integration merge `e558db52defcfeb64809b947a42d4995aa78502a`; source PR #2125 exact `151ba07dc9f5f377d7e69add70d226fd9ee48a12`. Includes Autotask controlled RW plus separate default-disabled IT Glue and Entra adapters; do not grant new roles, secrets, permissions or write activation by bundling.
3. **Windows Time JSON C:** Review PR #2129 is rebased via a clean merge onto the updated Stage B review commit `0eca97fcc382e9090c8ea15878a18800e40fbac2`. This review worktree merges source PR #2126 `3fb983c7333b89eea5a57749b63df3d27c31d4a5` over B; origin PRs #2111, #2118, #2122. JSON shadow defaults off; no site allowlist is granted by source. The 16 JSON conversion drafts remain non-executable, and the 17th `client_information_request@1.0.0` is independently governed and explicitly excluded from those drafts.
4. **Client questions:** Source PR #2123 is already included in baseline main. Its owner-approved text is not authorization to send. Client notifications stay disabled until controlled end-to-end acceptance, policy permission and separate explicit activation.
5. The operator must issue a **distinct, SHA-bound approval** after the candidate is merged to protected main and PM exact-image review is complete. No PR, draft or source commit is a deploy permit.

## Mandatory review of unrelated protected-main changes

Protected main is **36 git commits** ahead of the last-known-good live revision. It now includes the source-only PR #2127 merge. All commits are in scope for any normal full-main Production Manager release, whether or not the owner intended only one feature:

- `1586dd9da | Integrate governed Autotask read repairs from PR #2127`
- `f4a6d9563 | Integrate Autotask governed reads with 2026-10-28 protected main`
- `2a51d0346 | Merge pull request #2123 from al-teamaot-com/feature/client-question-library-round1-20261028`
- `47a27b84f | Document isolated Datto test-registry acceptance and retain PM freeze`
- `7b474885a | Implement governed Round 1 client information request lifecycle (disabled by default)`
- `70faec633 | docs(release): record candidate integration and concurrent PR coordination`
- `70086a7a4 | merge(preprod): reconcile Autotask read candidate with current main`
- `6a6b84465 | Merge remote-tracking branch 'origin/main' into feature/client-question-round1-engineering-20261028`
- `9ccd99465 | Merge pull request #2124 from al-teamaot-com/fix/kfs-session-safe-diagnostics-20261028`
- `2d4e15307 | Merge branch 'main' into fix/kfs-session-safe-diagnostics-20261028`
- `ff8f3d1a4 | Merge pull request #2115 from al-teamaot-com/fix/aot-routine-technician-rw-20261028`
- `1fb26713d | Classify actual KFS session network and response read failures safely`
- `79aad875c | Merge branch 'main' into fix/aot-routine-technician-rw-20261028`
- `2f24d88ad | Merge pull request #2120 from al-teamaot-com/feature/aot-entra-standard-user-create-20261028`
- `2f05c3d9d | Merge branch 'main' into feature/aot-entra-standard-user-create-20261028`
- `8d26d8408 | Merge pull request #2119 from al-teamaot-com/feature/aot-itglue-routine-rw-20261028`
- `48450d0b0 | Document source-only Round 1 client question package and PM release boundary`
- `46e966670 | Test Round 1 client question content and fail-closed disabled state`
- `57c814a39 | Stage 120 owner-approved client information questions and reusable support footer (no activation)`
- `9f07a6132 | Merge remote-tracking branch 'origin/main' into fix/aot-routine-technician-rw-20261028`
- `4abcf3ea9 | docs(release): production handoff and mandatory live read acceptance gates`
- `7c9fc2af9 | Implement source-only governed standard Entra user creation`
- `239f110e4 | test(preprod): reject missing or production Autotask credential sources`
- `6e8eb670a | Add source-only governed IT Glue configuration notes mutation adapter`
- `afb8428df | merge(preprod): reconcile Autotask read candidate with current main`
- `1b8fc4a8d | Merge remote-tracking branch 'origin/main' into fix/aot-routine-technician-rw-20261028`
- `ada153ce8 | docs(preprod): record isolated 74-test acceptance and live provider gates`
- `a3d9d1dad | Test routine write rejects unapproved capability/provider class`
- `ba01eb1bb | Add opt-in AOT routine Autotask technician write authority`
- `f74a704ee | fix(preprod): deny cross-client selectors before contract reads`
- `5fb2ff096 | docs(preprod): record live time-entry and contract permission metadata`
- `8221b042f | test(docs): verify staff contract scoping and document preproduction gates`
- `d0d4111aa | fix(preprod): preserve existing owner contract read selection`
- `18113c9c3 | fix(preprod): allow trusted AOT staff scoped contract reads with exact observe authority`
- `8fd221ad6 | test(preprod): cover company partial search and ticket time-entry request boundaries`
- `ee61a4be0 | fix(preprod): use bounded contains search for Autotask company name`

The **37 changed paths** on protected main since LKG are:

- `config/client_communications/information_requests_round1.json`
- `docs/operations/AOT-Client-Information-Requests-Round1.md`
- `docs/operations/AOT-Routine-Autotask-RW-Pilot.md`
- `docs/operations/AOT-Routine-ITGlue-Configuration-Notes-RW-20261028.md`
- `docs/operations/AOT-Standard-Entra-User-Create-20261028.md`
- `docs/operations/Autotask-Read-Repair-Preproduction-20261028.md`
- `docs/operations/Autotask-Read-Repair-Production-Handoff-20261028.md`
- `docs/operations/KFS-Live-Session-Read-Error-Taxonomy-20261028.md`
- `docs/playbooks/Jason-Client-Information-Requests-Round1.md`
- `implementation/autonomous_remediation/playbook_registry.json`
- `implementation/connectors/it_glue/configuration_note_update.py`
- `implementation/connectors/kyocera_kfs/client.py`
- `implementation/connectors/microsoft_graph/standard_user_create.py`
- `implementation/connectors/microsoft_graph/test_standard_user_create.py`
- `implementation/connectors/microsoft_graph/test_user_directory.py`
- `implementation/connectors/tests/test_it_glue_configuration_note_update.py`
- `implementation/connectors/tests/test_kyocera_kfs_connector.py`
- `implementation/mcp_service/src/jason_mcp/server.py`
- `implementation/mcp_service/tests/test_contract_client_context.py`
- `implementation/orchestrator/autotask_information_authorizer.py`
- `implementation/orchestrator/provider_read_argument_adapter.py`
- `implementation/orchestrator/provider_read_authority.py`
- `implementation/orchestrator/tests/test_aot_technician_routine_write_authority.py`
- `implementation/orchestrator/tests/test_autotask_information_authorizer.py`
- `implementation/orchestrator/tests/test_autotask_preproduction_read_repairs.py`
- `implementation/runtime_service/src/jason_runtime/aot_routine_write_authority.py`
- `implementation/runtime_service/src/jason_runtime/approved_client_messages.py`
- `implementation/runtime_service/src/jason_runtime/autonomy_worker_composition.py`
- `implementation/runtime_service/src/jason_runtime/autonomy_worker_runtime.py`
- `implementation/runtime_service/src/jason_runtime/autotask_client_notification.py`
- `implementation/runtime_service/src/jason_runtime/client_information_requests.py`
- `implementation/runtime_service/src/jason_runtime/composition.py`
- `implementation/runtime_service/tests/test_aot_routine_write_authority.py`
- `implementation/runtime_service/tests/test_client_information_requests_engine.py`
- `implementation/runtime_service/tests/test_client_information_requests_round1.py`
- `tools/autotask_preprod_credential_gate.py`
- `tools/tests/test_autotask_preprod_credential_gate.py`

## Exact integration diff inventory

- Read repair adds or modifies **8 paths**.
- RW coordination adds or modifies **26 paths** relative to Reads A.
- Windows Time source merge adds or modifies **30 paths** relative to RW B.
- This staged candidate index differs from the last-known-good source in **88 distinct paths**; the complete list follows. This is a **source-impact inventory**, not a verified production container manifest:

- `.dockerignore`
- `.github/workflows/aot-routine-rw.yml`
- `config/client_communications/information_requests_round1.json`
- `deploy/openbao/config/jason-itglue-configuration-notes-write-policy.hcl`
- `deploy/openbao/config/jason-microsoft-graph-onboarding-password-policy.hcl`
- `deploy/openbao/config/jason-microsoft-graph-user-create-policy.hcl`
- `docs/operations/AOT-Client-Information-Requests-Round1.md`
- `docs/operations/AOT-Routine-Autotask-RW-Pilot.md`
- `docs/operations/AOT-Routine-ITGlue-Configuration-Notes-RW-20261028.md`
- `docs/operations/AOT-Routine-RW-Production-Readiness-20261028.md`
- `docs/operations/AOT-Standard-Entra-User-Create-20261028.md`
- `docs/operations/Autotask-Read-Repair-Preproduction-20261028.md`
- `docs/operations/Autotask-Read-Repair-Production-Handoff-20261028.md`
- `docs/operations/KFS-Live-Session-Read-Error-Taxonomy-20261028.md`
- `docs/operations/Project-Jason-20261028-Production-Release-Dossier.md`
- `docs/playbooks/Jason-Client-Information-Requests-Round1.md`
- `docs/playbooks/json/MIGRATION-REVIEW-2026-10-28.md`
- `docs/playbooks/json/WINDOWS-TIME-GOVERNED-READ-PILOT.md`
- `docs/playbooks/json/WINDOWS-TIME-RELEASE-CANDIDATE-2026-10-28.md`
- `docs/playbooks/json/candidates/backupiq_endpoint_backup-1.2.0-jsonpreview.json`
- `docs/playbooks/json/candidates/datto_edr_av-1.3.0-jsonpreview.json`
- `docs/playbooks/json/candidates/disk_bad_block_event_7-1.0.0-jsonpreview.json`
- `docs/playbooks/json/candidates/dns_agent_diagnostic-1.0.0-jsonpreview.json`
- `docs/playbooks/json/candidates/drmm_recent_alert_reconciliation-1.0.0-jsonpreview.json`
- `docs/playbooks/json/candidates/gpt_insights_tech_assist-0.2.1-jsonpreview.json`
- `docs/playbooks/json/candidates/idle_log_off-1.1.0-jsonpreview.json`
- `docs/playbooks/json/candidates/jason_activity_log-1.0.0-jsonpreview.json`
- `docs/playbooks/json/candidates/low_disk_space-1.1.0-jsonpreview.json`
- `docs/playbooks/json/candidates/offline_ticket_context_augmentation-0.1.0-jsonpreview.json`
- `docs/playbooks/json/candidates/post_error_investigation-1.0.0-jsonpreview.json`
- `docs/playbooks/json/candidates/security_log_self_heal-1.0.0-jsonpreview.json`
- `docs/playbooks/json/candidates/unexpected_shutdown-1.1.0-jsonpreview.json`
- `docs/playbooks/json/candidates/vulscan_missing_patch-1.1.0-jsonpreview.json`
- `docs/playbooks/json/candidates/vulscan_multi_device_split-1.0.0-jsonpreview.json`
- `docs/playbooks/json/candidates/windows_time_source-0.1.0-jsonpreview.json`
- `docs/playbooks/json/migration-status-2026-10-28.json`
- `implementation/autonomous_remediation/playbook_registry.json`
- `implementation/connectors/core/openbao_secrets.py`
- `implementation/connectors/it_glue/configuration_note_update.py`
- `implementation/connectors/kyocera_kfs/client.py`
- `implementation/connectors/microsoft_graph/standard_user_create.py`
- `implementation/connectors/microsoft_graph/test_standard_user_create.py`
- `implementation/connectors/microsoft_graph/test_user_directory.py`
- `implementation/connectors/tests/test_it_glue_configuration_note_update.py`
- `implementation/connectors/tests/test_kyocera_kfs_connector.py`
- `implementation/mcp_service/src/jason_mcp/server.py`
- `implementation/mcp_service/tests/test_contract_client_context.py`
- `implementation/orchestrator/autotask_information_authorizer.py`
- `implementation/orchestrator/onboarding_request_attestation.py`
- `implementation/orchestrator/provider_read_argument_adapter.py`
- `implementation/orchestrator/provider_read_authority.py`
- `implementation/orchestrator/routine_write_client_scope.py`
- `implementation/orchestrator/tests/test_aot_technician_routine_write_authority.py`
- `implementation/orchestrator/tests/test_autotask_information_authorizer.py`
- `implementation/orchestrator/tests/test_autotask_preproduction_read_repairs.py`
- `implementation/orchestrator/tests/test_onboarding_request_attestation.py`
- `implementation/orchestrator/tests/test_routine_write_client_scope.py`
- `implementation/runtime_service/src/jason_runtime/aot_routine_write_authority.py`
- `implementation/runtime_service/src/jason_runtime/approved_client_messages.py`
- `implementation/runtime_service/src/jason_runtime/autonomy_worker_composition.py`
- `implementation/runtime_service/src/jason_runtime/autonomy_worker_runtime.py`
- `implementation/runtime_service/src/jason_runtime/autotask_client_notification.py`
- `implementation/runtime_service/src/jason_runtime/client_information_requests.py`
- `implementation/runtime_service/src/jason_runtime/composition.py`
- `implementation/runtime_service/src/jason_runtime/routine_rw_credentials.py`
- `implementation/runtime_service/src/jason_runtime/routine_rw_registration.py`
- `implementation/runtime_service/src/jason_runtime/routine_rw_runtime.py`
- `implementation/runtime_service/src/jason_runtime/routine_rw_scope.py`
- `implementation/runtime_service/src/jason_runtime/windows_time_json_shadow_evidence.py`
- `implementation/runtime_service/src/jason_runtime/windows_time_source_shadow.py`
- `implementation/runtime_service/src/jason_runtime/windows_time_source_shadow_composition.py`
- `implementation/runtime_service/tests/test_aot_routine_write_authority.py`
- `implementation/runtime_service/tests/test_client_information_requests_engine.py`
- `implementation/runtime_service/tests/test_client_information_requests_round1.py`
- `implementation/runtime_service/tests/test_composition.py`
- `implementation/runtime_service/tests/test_json_playbook_migration_candidates.py`
- `implementation/runtime_service/tests/test_routine_rw_credentials_and_invokers.py`
- `implementation/runtime_service/tests/test_routine_rw_production_composition.py`
- `implementation/runtime_service/tests/test_routine_rw_registration.py`
- `implementation/runtime_service/tests/test_routine_rw_release_environment_contract.py`
- `implementation/runtime_service/tests/test_routine_rw_scope.py`
- `implementation/runtime_service/tests/test_windows_time_json_shadow_evidence.py`
- `infrastructure/jason-mcp/production-deploy.sh`
- `infrastructure/jason-runtime/Dockerfile`
- `infrastructure/jason-runtime/compose.yaml`
- `infrastructure/jason-runtime/production-deploy.sh`
- `tools/autotask_preprod_credential_gate.py`
- `tools/tests/test_autotask_preprod_credential_gate.py`

## Verifications performed on isolated source

- Read repair: clean merge against protected main, focused Autotask adapter and preproduction gate tests passed.
- Routine RW branch: clean merge against read repair; local focused provider-scope, attestation, credential, runtime and Autotask adapter tests passed; no provider writes.
- Windows Time branch: clean merge against routine RW with `composition.py` and `compose.yaml` auto-reconciled; original main's client-question registry was added to the JSON migration-test scope analysis as a specifically *unconverted* 17th playbook.
- Focused JSON playbook, governed evidence and adapter suites passed after registry reconciliation; extended worker/composition/RW/client-questions suite passed in an isolated worktree.
- The source PR #2126's original CI failure was confined to documentation-impact section and concurrency review declaration on the PR body; this integration must have its own correct declarations and exact-SHA full CI.
- `git diff --cached --check` will be required to pass after this dossier is staged; it is not evidence of runtime/provider acceptance.

## Outstanding hard gates — do not bypass

**Autotask:** Provide dedicated isolated preproduction read-only identity and credential mount with no production credential reuse; its metadata gate currently rejects the missing directory. Prove authorized partial-name and contract reads, cross-client negative cases, native TimeEntries positive/negative impersonation on populated ticket, and release acceptance ticket-count/pagination/exact-read. Keep time-entry gate off if provider authority is unproven.

**IT Glue / Entra:** Dedicated least-privilege IT Glue configuration-notes write key and separate Entra Graph User.Create app/test tenant, private OpenBao credentials and explicit exact-client grants do not exist in accepted end-to-end state. Run positive and negative readback canaries only in an independently authorized test organization/tenant; do not substitute live client accounts or force provision new roles without external approval. Keep both profiles off.

**Client questions:** Verify exact approved content, same-company recipients, write/notification restrictions, durable idempotency, and client-authored reply resume in a controlled test ticket. No unapproved external client notifications.

**Windows Time:** Build exact source/runtime image with preview JSON path and off-by-default flag. For a separately authorized single-site pilot, allowlist only Riggins Datto site `17065ca1-dfdf-4c6b-95c7-8a8a5f5dc14a`. After permitted deployment, gather at least two consecutive existing 15-minute worker cycles with zero writes, site isolation, legacy parity and durable evidence. No pilot activation before exact-SHA release approval.

**Release governance:** Fresh independent PM root health/CCC, LKG container and host-unit manifest, circuit breaker, no current transaction, exact image digests, all CI and vulnerability/permissions gates, full pre/post foundational Autotask and Jason capability canaries, acceptance receipt, protected-main promotion, and explicit owner exact-SHA authorization. Active production freeze and unattended incident hold remain in force.

## Recommended decision

**HOLD promotion**. Review the isolated stacked integration PRs, rerun exact-head CI, resolve independent credential/provider acceptance and deployment-control blockers, then ask Owner for one exact-SHA authorized release at a time. GitHub merge and local unit tests are not proof of deployed functional capability.
