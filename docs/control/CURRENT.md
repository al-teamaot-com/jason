# Project Jason — Current Resume Point

**Updated:** 2026-09-24
**Status:** Production runtime and MCP are healthy on merged source `87f9ecd60676db46fff5b815857b62a42f6b8320` from SUPPORT-CONN-020 fix PR #252. Runtime image `sha256:207f0aa1f03b8d3f97360bcd27d0273a516247579bc34838293ac46fbf171cb1` and MCP image `sha256:f4cf7ae385a3457ff3dfce7865b3615187ac7615cd037badf4dd867c5df431e1` back the canonical production aliases. Immediate rollback aliases preserve runtime source `fe75d15304a294fe20193c5c837f9f99be74e4ee` / image `sha256:94b3c5bb3c07863f5b1836c62be91d020423be1eafd2347002f433478047c362` and MCP source `5244e9e41ac86a366fc475b37be0559919fdc968` / image `sha256:785279fe3ea25145dea7e55bd4256656999adc4bd7fc2f838cbf66877f7ba901`. Runtime and MCP remain hardened; Central Orchestrator remains authoritative; `direct_provider_access=false`; and the governed write-capability list is unchanged. Backup.net/UniView remains production-selected on `JASON_BACKUP_NET_ACCESS_PROFILE=full_access`. SUPPORT-CONN-020 corrected two governed-read contract defects: valid Autotask company ID `0` is no longer rejected, and a BackupIQ alert search with omitted `type` safely defaults to provider type `alert` while explicit values remain bounded. A validated Backup.net client boundary now maps Autotask company `0` / Atlantic Office Machines to customer UUID `08de23b9-9685-4cdf-8932-e2318bf4412a`; the provider currently reports zero Endpoint Backup assets for that customer. Live governed acceptance therefore returns successful authoritative empty collections for AOT-50282 asset search, BackupIQ alert search, and backup-history search rather than authorization/configuration failures. Durable evidence is `docs/sessions/BackupNet-SUPPORT-CONN-020-Production-Fix-2026-09-24.md`. The prior read-only credential identity remains separately preserved for rollback. The published Backup.net Public API currently advertises GET operations only, so provider credentials still do not create a Jason write/remediation capability; no Backup.net mutation capability is registered.
**Canonical purpose:** Human-readable resume point. Volatile production facts still require fresh runtime evidence before consequential change.

## Continuity control anchors

- **Extension construction control:** `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
- **Last durable success:** preserved in the governed production proof and observability sections below.
- **Production/runtime boundary:** use the recorded boundary below only as durable history; verify volatile production facts before consequential change.
- **Next safe actions:** `main` remains authoritative and branch-protected. Backup.net full-access governed reads are production-accepted for both a populated validated customer boundary and the AOT self-company boundary. For Atlantic Office Machines, a successful empty Endpoint Backup asset result means the provider currently exposes no protected asset under that exact customer; do not reinterpret that as connector failure. If an AOT endpoint is expected to be protected, investigate provider onboarding/registration or customer/asset placement through a separately governed workflow. The broader BackupIQ remediation/write work remains separate and requires provider-documented mutation operations before any Jason write capability can be registered.

## Durable operating principle

> **ChatGPT reasons. Jason governs and executes.**

ChatGPT is the primary technician conversational surface. Jason remains authoritative for identity, scope, grants, approval policy, provider isolation, Central Orchestrator execution, evidence, and audit. A ChatGPT tool call is a governed request, not provider authority.

## Security review — 2026-09-23 current state

The authoritative chronological record is `docs/sessions/2026-09-23.md`; the architectural approval/mutation rule is `docs/architecture/J-102-Governed-Approval-Architecture.md`; remaining work is `TODO-SEC-006` and `TODO-SEC-007`.

Confirmed current security-review state:

- client isolation / fail-closed evidence handling on XYZ Test Company: **PASS**; no unrelated DRMM, Datto EDR, Endpoint Backup, VulScan, DNSFilter, or Microsoft 365 evidence was queried when client/provider binding was unavailable;
- misleading `SECURITY TEST` ticket content on `T20211001.0014`: **PASS**; content was not treated as evidence/authority;
- approval replay/idempotency: **confirmed defect then production-fixed**; original duplicate notes `30506555` and `30506556`; post-fix test created only note `30506631`; replay result `deduplicated`;
- canonical approval argument binding: **PASS** at the Central Orchestrator canonical-request boundary; changed arguments are rejected with zero provider invocation;
- post-approval normalization/provider binding: **architectural gap confirmed** before remediation; unchanged semantic intent could resolve to different concrete Autotask mutations;
- dual intent/execution-plan binding: **source remediation PASS**, core commit `56b0e91fe376fb270ac521c5c1754bfa12aafdb5`, adapter-hardening commits `0ed6911` and `e41e572`, shared framework/recovery commit `bf072af`, consolidated security suite 186/186;
- production execution-plan acceptance: **PASS**; the bounded XYZ acceptance on `T20211001.0014` completed with exactly one provider attempt, exact intent/execution-plan binding, no plan mismatch, and successful post-write readback; and
- deployment reproducibility: **PASS**; clean no-cache builds, exact revision labels, hardened production deployment, rollback preservation, and live health/governance verification are established.

The execution-plan control is production-verified. Do not weaken the fail-closed adapter requirement to preserve legacy mutation behavior.

The three previously recorded IT Glue/provider-read failures were resolved during the production reconciliation work: sensitive raw evidence is classified before sanitization, flexible-asset discovery advertises the required selector contract, and the stale provider-read test imports/expectations were corrected. Full orchestrator, runtime, connector, kernel, and top-level implementation suites passed in the reconciled line before final production promotion.

### Production execution-plan rollout and XYZ acceptance — 2026-09-23

Production MCP and runtime were promoted to source revision `6e4e4c0979f3762b8dbd3b8b277850a1899deb18` using the verified candidate images:

- MCP: `jason-mcp:security-remediation-6e4e4c0`, image ID `sha256:a5f2187f451d8f2ea99481434668519dfeb376a9f339b7b860393e86f24d507c`;
- runtime: `jason-runtime:security-remediation-6e4e4c0`, image ID `sha256:adf4c9d75f226d5968117b732b6d3cc660d712a9755914bcd02bb18a8b00639a`.

Final verification: MCP container/host health HTTP 200, runtime health HTTP 200/healthy, `governed_execution=central-orchestrator`, `generic_execution_tool=true`, `direct_provider_access=false`, and 24 governed write capabilities active. Exact pre-rollout rollback containers remain preserved on the prior MCP/runtime image IDs.

A bounded live acceptance was then performed on XYZ Test Company ticket `T20211001.0014` / Autotask ID `29860`. Baseline was priority `2`, queue `29682833`, status `5`. Exactly one mutation changed priority `2 -> 3`. Acceptance correlation: `corr_mcp_action_3cfdd46df8b94ed2b64d7a03439942e9`; execution ID `exec_mcp_action_feee8d8dd733424f81948228c97e3785`; approval ID `approval_mcp_1f3bb42295ca4a9cb05ad61bf3e48aba`; intent fingerprint `efd8ed5c7064403bff41897561e10c833d97cb9d03e6ae68cffde49e5b86c8af`; execution-plan fingerprint `2cb2b9977be7d7082bc84e51c5ac119d74fe409507ef6fb069f3eab1fff355ea`. The authorized plan selected provider `autotask_ticket_update`, provider capability `autotask.ticket.update`, method `PATCH`, target `service_ticket:29860`, path `/V1.0/Tickets`, payload `{"id":29860,"priority":3}`, and no symbolic resolution.

The governed ledger ended `state=succeeded`; action/result fingerprint matched intent fingerprint; exactly one provider attempt was reported; exactly one `connector.mutation.requested`, one `connector.mutation.completed`, and one `connector.mutation.verified` event exist for the acceptance correlation; post-mutation readback verified field `priority`; independent governed post-read returned priority `3`; and no execution-plan mismatch event was recorded. The stable second preparation is therefore evidenced by successful passage through Central Orchestrator's exact fingerprint re-prepare gate before the single provider invocation.

No compensating priority restore was performed because that would have been a second provider mutation outside the one-write acceptance boundary.

### Direct ticket-update canonicalization production acceptance — 2026-09-24

`SUPPORT-CAP-019` is resolved and production-proven. Ordinary technician-friendly `service.ticket.update` requests are now canonicalized at the MCP governed-action boundary before approval reservation, intent fingerprinting, and execution-plan authorization. Exact `ticket_id` / `ticketID` / `id` selectors are reconciled fail-closed, the authoritative positive numeric Autotask ticket ID is confirmed through governed read, and only explicitly requested allowed mutable fields enter the structured provider payload. Symbolic values such as `Complete` continue through authoritative Autotask picklist resolution during execution-plan preparation; ambiguous ticket or symbolic identity fails closed.

Fix commit `17ca474de031efd87200fa46ad408f0f8a8ef14a` was merged by PR #249 as production MCP source `5244e9e41ac86a366fc475b37be0559919fdc968`. Production MCP image `sha256:785279fe3ea25145dea7e55bd4256656999adc4bd7fc2f838cbf66877f7ba901` passed deployment preflight, hardening, health, alias promotion, and governance post-check with Central Orchestrator authoritative and `direct_provider_access=false`. The production runtime remained separately pinned to source `fe75d15304a294fe20193c5c837f9f99be74e4ee`.

Bounded acceptance used OWNI7JAN25 ticket `T20260905.0004` / ID `139815`. Pre-read status was In Progress (`8`) and the latest ticket evidence stated the original VulScan finding was no longer present and the ticket was ready for completion. Exactly one governed update authorized normalized payload `{"id":139815,"status":5}` with symbolic resolution `Complete -> 5`. Provider attempts: `1`; built-in readback: verified; independent governed post-read confirmed status `5` / Complete. Execution-plan fingerprint `c2af672ccbbadb634d9079f3dea45c40ef3616e9b57bc3644d6019ca4c219121`; intent fingerprint `28ddf52db91504791cde71da36ea35a8e4ef86fea84e05023b9cb38146fa9b90`; approval `approval_mcp_fdfaab04772f469bb87925521c25a0ef`; execution `exec_mcp_action_2394b8b355f34b38bf2a9cd259015ccf`; correlation `corr_mcp_action_ec27baa18b6d495aae03627762ca3bde`.

Durable proof: `docs/sessions/Jason-Direct-Ticket-Update-Canonicalization-Production-Acceptance-2026-09-24.md`.

### Clean build and rollback readiness — 2026-09-23

Authoritative source `6e4e4c0979f3762b8dbd3b8b277850a1899deb18` produced clean no-cache candidate images without reproducing the earlier Docker overlay-chain failure:

- MCP candidate: `jason-mcp:security-remediation-6e4e4c0`, image ID `sha256:a5f2187f451d8f2ea99481434668519dfeb376a9f339b7b860393e86f24d507c`;
- runtime candidate: `jason-runtime:security-remediation-6e4e4c0`, image ID `sha256:adf4c9d75f226d5968117b732b6d3cc660d712a9755914bcd02bb18a8b00639a`;
- established MCP build base: `jason-mcp:generic-governed-8f1e864947a2`, image ID `sha256:d709ca54b66d41e22bd1f67782cd5f6d681c4337bffb359b632523762a27788a`;
- MCP rollback tag: `jason-mcp:rollback-pre-execution-plan-20260923` -> exact live image ID `sha256:9d953d3cfb580c4c470e7e6c3bc7c44086706e22cd3b95e04c88f536fe121229`; and
- runtime rollback tag: `jason-runtime:rollback-pre-execution-plan-20260923` -> exact live image ID `sha256:057a5412d9a6f5b3a8fcb01490aa26d804d6426250b64a8fcf4edd8d1abbc620`.

Candidate image source hashes for the security-critical orchestrator, recovery, Datto, and Teams files match the authoritative worktree exactly. With `--network none`, both candidate images imported their new security contracts successfully, and both rollback images imported their production entry modules successfully. The live production MCP container remained `8ba7e3cda5c7808e3340cd096b1ba9dbb320929fdbf18a717d12d1edf219b8ef` on the approval-replay image; the live runtime container remained `ad7196cdef5b1d669bf28502495db12dc987223625578b06d0e5649cc00a059c` and healthy. No live container was recreated/restarted and no provider call was made.

### Execution-plan remediation compatibility state

Current isolated remediation status on `fix/security-remediation-20260923`:

| Mutation path | Execution-plan status | Current rule |
| --- | --- | --- |
| `service.ticket.update` / Autotask ticket update | **ADAPTED + HARDENED** | Binds provider capability, method, target ticket, normalized path, payload, parameters, and symbolic resolutions; executor revalidates the opaque prepared request against the authorized plan before provider invocation. |
| `service.ticket.create` / Autotask ticket create | **ADAPTED** | Binds concrete create method/path/payload/parameters and symbolic resolutions; provider-created ticket ID is intentionally absent before the create and durable ID is verified by readback after the write. |
| `service.ticket.note.create` / Autotask internal note | **ADAPTED** | Binds the target parent ticket, method/path/payload/parameters; durable created note ID and requester attribution remain post-write readback requirements. |
| Autotask procurement mutation path | **ADAPTED** | Shared procurement adapter covers all currently registered procurement mutations and binds provider entity/operation, method/path, payload, route selectors, and durable target IDs for updates; creates verify provider-assigned IDs by readback. |
| Datto RMM component execution | **ADAPTED** | Each preparation independently verifies the managed endpoint and allowlisted component; plan binds exact endpoint, component UID/name resolution, quick-job method/path/body, allowlist, target class, and material parameters. |
| Datto RMM site-variable create/update | **ADAPTED — SECRET COMMITMENT** | The actual value remains only in ephemeral provider-private state. Persisted plan material binds a SHA-256 commitment to the exact secret value plus variable identity/masking/operation; execution re-hashes the ephemeral value before write. |
| Datto EDR scan execution | **ADAPTED** | Both preparations independently re-check exact agent/device identity, AV enablement, current scan state, and one-hour guard; plan binds exact agent, endpoint, scan type, path, and provider scan payload while excluding access token/host. |
| Datto alert resolution | **ADAPTED** | Binds exact alert and endpoint plus resolve path/action. Already-resolved state is represented as a deterministic NOOP plan; state changes between preparations cause plan mismatch and zero writes. |
| Microsoft Teams proactive message send | **ADAPTED** | Direct invoker now implements the plan contract and binds tenant, AAD target, message/card content, and send path while keeping proactive token and internal gateway hostname ephemeral. |

The shared execution-plan material now rejects non-JSON objects rather than stringifying them, rejects non-finite numbers, requires string object keys, and expands transport-secret key rejection including normalized proxy authorization, cookies, API-key headers, bearer tokens, and private-key fields. Opaque provider-private state is suppressed from dataclass `repr()` at the shared prepared-plan boundaries to reduce incidental credential/secret leakage during debugging. The provider `maximum_execution_seconds` is enforced as one absolute deadline across first preparation, independent re-preparation, and invocation; nested connector deadlines may only tighten it. Continuation/recovery approvals that do not use an MCP `approval_id` are still dual-plan-bound by Central Orchestrator after their own durable one-time guard is consumed. Indeterminate outcomes use `docs/operations/Governed-Mutation-Indeterminate-Recovery.md`; recovery retry authorization is one-time and requires fresh JKD-001 authority. These are source/test changes only; no provider write or production deployment was performed by this remediation pass.

## Operational Resolution Memory — current production state

- roadmap milestone: `RESMEM-001`; status: `active`; phase: `Reasoning Quality`;
- canonical TODO: `TODO-OPS-001`; status: **In progress**;
- production MCP image: `jason-mcp:resmem-ingest-1a5f2b2`;
- production source revision: `1a5f2b2`;
- governed aggregate health capability: `operations.resolution.summary`;
- latest post-deployment proof correlation: `corr_mcp_56b21063bfc545ccb1f054f0c167b050`;
- raw historical search/read requires authenticated current client scope and grounded incident signature;
- historical evidence explicitly grants no execution authority; normal approval/disruption/provider controls remain mandatory;
- verified ingestion requires exact ticket provenance, matching company boundary, explicit root cause/final resolution, technician confirmation, and terminal verification;
- production case count: `0`; first verified case and later materially-similar retrieval proof remain pending.

Observability is live: `jason-resolution-memory` is an `up` Prometheus target, the aggregate exporter reports store availability `1` and zero cases/client scopes, and `jason_roadmap_item_info{milestone="RESMEM-001"}` reports `status="active"`. Grafana health is `database=ok` on version `12.2.1`; the repository-provisioned `Jason Command Center` roadmap table consumes this roadmap metric. Monitoring is observational only and grants no authority.

Authoritative implementation/session record: `docs/sessions/Jason-Operational-Resolution-Memory-Integration-2026-09-18.md`.

## Current live MCP boundary

The production MCP service is `jason-mcp-pilot`.

As of the 2026-09-24 SUPPORT-CAP-019 promotion, the live MCP production image is `sha256:785279fe3ea25145dea7e55bd4256656999adc4bd7fc2f838cbf66877f7ba901`, built from source `5244e9e41ac86a366fc475b37be0559919fdc968`. The matching production runtime remains separately pinned to source `fe75d15304a294fe20193c5c837f9f99be74e4ee`. These facts supersede older MCP revision statements below where they conflict.

The currently established live MCP code/image boundary is:

- source revision reported by the production container at the 2026-09-23 security safety check: `5f89f3af82081e75e97d66e523222e5564648163`;
- image/deployment line: `jason-mcp:approval-replay-fix-5f89f3a`, deployment purpose `approval-replay-idempotency-fix`;
- mode: `governed-read-plus-actions`;
- phase: `governed-action-pilot`;
- governed execution: Central Orchestrator;
- generic governed execution tool: enabled;
- `direct_provider_access=false`;
- write tools enabled;
- active write/action capabilities include `automation.component.execute`, `service.ticket.note.create`, and `service.ticket.update`;
- Datto follow-up reads include `automation.job.read` and `automation.job.output.read`;
- Datto EDR/AV governed reads include `endpoint.security.status.read`, `endpoint.security.detection.search`, `endpoint.security.detection.read`, `endpoint.security.policy.read`, `endpoint.security.scan.history.search`, and `endpoint.security.quarantine.search`;
- all six endpoint-security reads were production-accepted against AOT-50282 on 2026-09-18;
- matching `jason-runtime` is healthy on image ID `sha256:6342f0b38abcbfdbe7545f5d5947a0c683b2a40b193c28de5b8864da68d73680`;
- write authority: `jason_exact_grant_plus_server_governed_approval_policy`;
- Datto component approval policy: `server_classified_standing_safe_or_per_run`.

The 2026-09-23 approval-replay production proof supersedes the older MCP revision statement above as the current security-review boundary. The execution-plan branch at `56b0e91...` is source-only/isolated-proof state until deployed. Continue to verify volatile runtime state before consequential change rather than assuming branch HEAD equals deployed state.

## Autotask governed proof

The bounded controlled pilot used XYZ Test Company ticket `T20191013.0001` (Autotask ticket ID `8870`). Jason changed the reversible priority from `3` to `2` through `service.ticket.update`, and a later governed read independently confirmed `priority=2`.

This proves the bounded Autotask ticket-update path, not arbitrary Autotask CRUD. Activated capabilities, exact Jason grants, provider authority, and required per-execution approval remain authoritative.

## Datto RMM governed proof — cross-chat execution and output

Controlled target:

- endpoint: `AOT-50282`;
- device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`;
- site: Atlantic Office Machines.

Controlled diagnostic component:

- `Get-DNS Settings AOT Ver 06042025-1`;
- component UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- allowlist `AOT governed diagnostic pilot`;
- variables: none.

The earlier same-day governed execution proof remains valid and is preserved at `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`; its completed job UID was `422d680b-a5ce-4473-b8e8-5d682ec85682`.

The later cross-chat proof deliberately treated the prior approval as consumed. Fresh governed reads resolved the exact endpoint and component. The AOT Owner then explicitly approved exactly one new non-disruptive diagnostic execution.

Jason executed one `automation.component.execute` request, one provider mutation, and one provider attempt. Datto accepted:

- job UID: `741a2d02-587d-4348-9f26-b4982d337732`;
- action correlation: `corr_mcp_action_d49b19600e6f4c50a60f43892af66458`;
- immediate result: `accepted`;
- immediate job state: `active`;
- `readback_verified=true`;
- `completion_verified=false` at action return because the job was asynchronous.

Jason issued no retry or second component execution. It used only `automation.job.read` until the exact job reached terminal `completed`:

- terminal read correlation: `corr_mcp_12eafe5022dc42cb8a42091be669d8cf`.

Jason then retrieved actual component StdOut through `automation.job.output.read`, bound to the exact job UID, device UID, component UID, and `stream=stdout`:

- output-read correlation: `corr_mcp_2c624f2cda234afab3be73b70906e8b0`;
- output matches: `1`;
- truncated: `false`.

The returned diagnostic data included:

- ZeroTier `192.168.193.90`;
- ZeroTier `10.148.127.90`;
- `vEthernet (NDA-External-VS)` `192.168.12.33`;
- gateway `192.168.12.1`;
- DNS `103.247.36.36`, `103.247.37.37`, `8.8.8.8`;
- Hyper-V Default Switch `172.23.176.1`.

The provider output endpoint returns a JSON array. Successful live output retrieval on `e9c7a763...` proves the bounded JSON-array transport fix is active and the previous `PROVIDER_TRANSPORT_FAILURE` is not present in this workflow.

Authoritative cross-chat/output proof: `docs/sessions/Jason-Datto-RMM-Cross-Chat-Output-Proof-2026-09-16.md`.

## Datto asynchronous execution rule

An approved Datto quick job may legitimately return `status=accepted`, `job_status=active`, `readback_verified=true`, `completion_verified=false`, and a durable `job_uid`. That is accepted asynchronous execution, not failure.

Do not issue a second provider mutation because the first job is still active. Use the returned `job_uid` with read-only `automation.job.read` until terminal state. If actual component output is required, retrieve it afterward through `automation.job.output.read` using the exact job UID, target device UID, component UID, and requested stream.

## Security boundary that remains mandatory

- `direct_provider_access=false`;
- Central Orchestrator remains the governed execution coordinator;
- provider credentials are never released to ChatGPT;
- read and write/execution identities remain separated where required;
- Datto execution remains bounded to approved component/target policy rather than arbitrary script text;
- failed authority/provider checks fail closed;
- provider actions do not retry through a broader credential;
- exact Jason grants remain mandatory;
- Datto component approval classification is server-controlled and cannot be supplied or overridden by the caller;
- `standing_safe` is reserved for explicitly classified non-disruptive diagnostics and does not require a separate per-run technician approval;
- `per_run` requires explicit technician approval for the exact execution;
- unknown, missing, or invalid component classification fails closed;
- user-disruptive actions require explicit technician approval for the exact disruptive action.

## Host reboot recovery — production control installed 2026-09-24

A 2026-09-23/24 power outage exposed that Jason's host boot path was not self-recovering even though individual containers were durable:

- OpenBao restarted initialized but sealed;
- the intentionally ephemeral IT Glue/Autotask runtime AppRole files under `/run/jason-runtime-credentials/openbao` were absent after reboot;
- `jason-runtime` therefore failed closed during OpenBao/AppRole initialization;
- `jason-mcp-pilot` had `restart=no`;
- Prometheus still referenced a disposable worktree that had been cleaned during build/worktree cleanup.

PR #223, merged as `4e3b7a4ad26c70650b78ce7b61e9408d439ed743`, added the repository-controlled boot-recovery controller, systemd service, timer, and runbook.

Current verified state:

- `jason-boot-recovery.service`: enabled; successful installed run;
- `jason-boot-recovery.timer`: enabled and active with a two-minute idempotent check;
- OpenBao: initialized, unsealed;
- IT Glue/Autotask ephemeral AppRole staging: restored with expected runtime ownership/mode;
- `jason-runtime`: running/healthy, `restart=unless-stopped`;
- `jason-mcp-pilot`: running, internal health HTTP 200, `restart=unless-stopped`;
- recovery service journal secret-pattern check: PASS;
- Prometheus: rebound to durable main-repository source and HTTP 200;
- Grafana: HTTP 200.

Security boundary: the root-only automatic unseal uses the already-retained protected initialization artifact on the same single-host pilot. This is an explicit AOT Owner pilot exception and must not be described as host-root-resistant split custody or production-grade KMS/HSM auto-unseal.

A complete host reboot after installation has **not** been performed because reboot is disruptive and requires separate explicit approval. Do not claim reboot-cycle acceptance until that test is actually performed.

Authoritative records:

- `docs/operations/Jason-Boot-Recovery.md`;
- `docs/operations/Jason-OpenBao-Initialization-and-Recovery-Record.md`;
- `docs/sessions/Jason-Boot-Recovery-Production-Acceptance-2026-09-24.md`.

## Grafana / production observability — current release accepted

The authoritative Grafana/Prometheus source remains repository-provisioned under `infrastructure/showcase`.

The production-health unit now expects the exact live MCP boundary:

- `JASON_EXPECTED_MCP_IMAGE=jason-mcp:generic-governed-26704f0600bb`;
- `JASON_EXPECTED_MCP_SOURCE_REVISION=26704f0600bbc6c48c790c9b9ff501a3b5ec3aad`.

The active Datto production scope contains exactly two server-classified `standing_safe` components:

- `Get-DNS Settings AOT Ver 06042025-1` — `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- `Check Datto EDR/AV Status AOT Ver 12122025-1` — `8cb0f063-5875-452e-88ad-2e1748ed0fd0`.

No reboot component is included in the production component scope.

The latest rollback-protected monitoring-only deployment used repository head `cefa32e9b14db97fb8c6e703ad467a9eda33c32b` and reconciled production observability to the `26704f...` MCP release.

Acceptance returned:

- `PRECHECK=PASS`;
- `SOURCE_VALIDATION=PASS`;
- `PRODUCTION_HEALTH_EXPORTER=PASS`;
- `MONITORING_CONTAINERS=PASS`;
- `CORE_ISOLATION=PASS`;
- `PROMETHEUS_PRODUCTION_HEALTH=UP`;
- `PROMETHEUS_PRODUCTION_RULES=PASS`;
- `GRAFANA_PRODUCTION_HEALTH_DASHBOARD=PASS`;
- `METRIC_CONTRACT=PASS`;
- `RUNTIME_CHANGED=NO`;
- `MCP_CHANGED=NO`;
- `OPENBAO_CHANGED=NO`;
- `PROVIDER_ACCESS=NO`;
- `PROVIDER_WRITES=NO`.

Latest monitoring deployment source: `cefa32e9b14db97fb8c6e703ad467a9eda33c32b`.

Latest monitoring rollback directory: `/tmp/jason-production-health-rollback-20260916T173323Z`.

Production MCP rollback container: `jason-mcp-pilot-rollback-20260916T172806Z`.

Final read-only live metrics returned `1` for:

- `jason_mcp_contract{check="datto_execution_profile"}`;
- `jason_mcp_contract{check="datto_execution_scope"}`;
- `jason_mcp_contract{check="image"}`;
- `jason_mcp_contract{check="source_revision"}`;
- `jason_datto_governed_execution_contract`.

Grafana returned dashboard UID `jason-governed-actions` with title `Jason Governed Actions`.

Monitoring remains observational only. It does not call Datto directly and grants no provider or execution authority.

## System Registry

Narrative proof does not itself promote System Registry lifecycle state. The prior wrap-up found no matching structured resource for this proof state and no governed registry write surface exposed to the ChatGPT session.

No registry state was invented or manually promoted. Reconcile structured truth only through the authoritative governed registry registration/verification path when available.

## Teams proactive messaging / approval workflow — production state

Governed proactive Teams text sending is production-proven through `communication.teams.message.send` with tenant isolation, exact authority, Central Orchestrator routing, and `direct_provider_access=false`. The follow-on Adaptive Card approval path successfully delivers Approve/Deny cards and receives authenticated Microsoft tenant/AAD-object interactions back through Jason. Final decision processing is currently **blocked** by external OpenAI API `429 insufficient_quota / credit_balance_exhausted`; therefore interactive Teams approval is not represented as fully accepted. `TODO-COMM-004` tracks the remaining acceptance, including exact approval correlation, structured information requests, and typed overrides. The runtime `reasoning.effort` compatibility defect discovered during testing was corrected from `minimal` to `low` in commit `811b3af`.

Authoritative session record: `docs/sessions/Jason-Governed-Teams-Proactive-Send-Proof-2026-09-18.md`.

## Current Section Goal — ACTIVE / PROCUREMENT PILOT

**Goal:** complete the governed procurement / PO lifecycle so Jason can correlate purchasing evidence, allocate ordered quantity explicitly between customer/ticket and AOT inventory, add only the approved billable quantity to the correct Autotask ticket, monitor approved vendor/requester mailbox evidence, and preserve exact approval/readback/audit linkage.

Current checkpoint:

- governed product/service/PO/PO-item/receiving actions are live;
- governed TicketCharges search/read/create/update is live and approval-gated;
- ticket candidates must be presented as `ticket number — title`;
- ordered quantity must reconcile exactly across explicit destinations;
- canonical acceptance case remains `2 ordered = 1 customer/ticket + 1 AOT inventory`, with billable quantity `1`;
- mailbox read source is implemented but intentionally dormant under v5;
- `MAIL-READ-001` is blocked pending the separate Entra application, Exchange Application RBAC `Application Mail.Read` scope, OpenBao `microsoft_graph.mail_read` identity, approved mailbox allowlist, and controlled positive/negative acceptance;
- tenant-wide Entra Graph `Mail.Read` must not be granted for this scoped design;
- `TODO-CONN-014` tracks the future `Add-Jason-Mailbox.ps1` helper;
- `direct_provider_access=false` remains required.

Authoritative checkpoint: `docs/sessions/Jason-Procurement-Mail-Read-Checkpoint-2026-09-20.md`.

## Concurrent open Section Goal — EDR/AV PILOT CLOSEOUT

**Goal:** finish the Datto EDR/AV Diagnose & Repair playbook as a governed, measurable MSP workflow without conflating product health, provider detections, contained artifacts, or confirmed compromise.

Production acceptance completed on 2026-09-18 for both the governed read backend and provider-native Datto AV scan-start capability. All six `endpoint.security.*` reads succeed through the authenticated Jason MCP path with exact DRMM UID -> EDR `deviceId` correlation. Controlled AOT-50282 acceptance also proved governed `endpoint.security.scan.start` by starting a native Quick Scan and verifying terminal scan-history ID `ba2ad23d-8cb7-4ecf-ac2d-55af309406c3`. Current hardened MCP source is `8776ac5dc56c4a22e0f86dceb780f0cff4fd70f9`.

Authoritative acceptance records:

- `docs/sessions/Jason-Datto-EDR-AV-Governed-Read-Acceptance-2026-09-18.md`;
- `docs/sessions/Jason-Datto-EDR-AV-Scan-Execution-Acceptance-2026-09-18.md`.

Current playbook state:

- lifecycle: `pilot`;
- runtime enabled: `false`;
- review status: `scan_execute_accepted_full_threat_branch_pending`;
- EDR/AV read backend: **accepted**;
- production runtime/MCP deployment: **accepted**;
- exact read-only authority grants: **accepted**;
- Grafana/Prometheus closeout: **accepted** — exporter active, Prometheus target `up=1`, Grafana dashboard UID `jason-playbook-control-center` provisioned;
- governed provider-native Datto AV scan execution: **accepted**;
- complete remediation/scan/recurrence acceptance: **pending**.

The full threat branch must continue to fail closed until the complete composite remediation/scan/post-scan-verification/recurrence acceptance is proven. Do not mark this Section Goal fully closed merely because the reads and scan-start action are healthy.

## Previous Section Goal — CLOSED

The requested cross-chat Datto workflow is complete:

1. exact endpoint resolution — **proven**;
2. exact component resolution — **proven**;
3. fresh explicit per-execution approval — **proven and consumed**;
4. one governed diagnostic execution — **proven**;
5. exactly one provider mutation / one attempt / no retry — **proven**;
6. durable Datto job reference — **proven**;
7. terminal completion through governed read-only polling — **proven (`completed`)**;
8. actual component StdOut through `automation.job.output.read` — **proven**;
9. bounded JSON-array provider transport — **live-proven**;
10. `direct_provider_access=false`, Central Orchestrator, exact grants, and the then-required fresh per-execution approval — **preserved in the historical proof**;
11. durable proof/current-state reconciliation — **complete**;
12. Grafana/Prometheus current-release observability — **live and passing**.

## Remaining follow-ups — not blockers

- Add first-class lifecycle/rotation tooling for the dedicated `datto_rmm.execution` secret identity so future rotation does not require rediscovery.
- Reconcile System Registry structured truth when an authoritative governed write/verification route exists.
- Expand Datto execution beyond the exact current pilot only through a separate capability/allowlist/authority decision.
- Establish the exact UID and separately authorize any future disruptive component, such as scheduled reboot, before adding it to production scope.
- Continue documentation-assurance work after Autotask/Datto/IT Glue governed update surfaces are available as planned.

## Read first in future sessions

1. `docs/control/JASON-FUNDAMENTALS.md`
2. this file
3. `docs/sessions/Jason-Datto-EDR-AV-Governed-Read-Acceptance-2026-09-18.md`
4. `docs/playbooks/Jason-Datto-EDR-AV-Diagnose-Repair.md`
5. `docs/sessions/Jason-Datto-RMM-Cross-Chat-Output-Proof-2026-09-16.md`
6. `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`
7. `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`
8. `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md`
9. current Git and fresh runtime evidence before asserting volatile production state

Conversation memory is context only. It is not authority.
