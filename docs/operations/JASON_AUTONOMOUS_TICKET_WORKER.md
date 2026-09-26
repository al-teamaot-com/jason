# Jason Autonomous Ticket Worker - Production Operations

**Production status:** Active  
**Activated:** 2026-09-25  
**Production revision at initial activation:** `aaa536cef3e10edac8a1cc41595caee19be570c6`  
**Current documented production revision:** `6499a3d2a2fb67b0fdda797e8f5a901097033bbb`  
**Workload principal:** `jason-autonomy-worker`

## Purpose

The autonomous ticket worker lets Jason discover and work eligible Autotask tickets without waiting for a technician to start each workflow. It is intentionally bounded by the same governance rules used for interactive Jason work. The worker does not create authority; it consumes previously approved playbook authority through governed capabilities.

Current discovery queues are:

- Help Desk I (`29682833`)
- Help Desk II (`29682969`)
- Monitoring Alert (`8`)
- Jason (`29683489`) for already-owned work

The default active-work limit is two. Tickets that are waiting, blocked, approval-pending, complete, or escalated do not consume an active slot.

## Current production autonomous scope

As of 2026-09-26, all ten production playbooks in the current registry have a separately promoted autonomous safe branch. This does **not** mean every remediation branch is autonomous. Each resolver is limited to the exact source-controlled capability set and its documented stop conditions.

| Playbook | Version | Autonomous production scope | Important gated boundary |
| --- | --- | --- | --- |
| `datto_edr_av` | 1.3.0 | health diagnosis plus one bounded standing-safe repair and independent verification | threat-response, clean uninstall, reboot, and other disruptive actions |
| `dns_agent_diagnostic` | 1.0.0 | DNS Agent/DNSFilter diagnostic component and evidence note | repair/install branch |
| `security_log_self_heal` | 1.0.0 | Quick Test, at most one Self-Heal, independent Quick Test verification | alert/SOC side-effect cleanup and unrelated security-ticket closure |
| `post_error_investigation` | 1.0.0 | read-only POST recurrence/device-role diagnostic | firmware/hardware change and automatic closure |
| `unexpected_shutdown` | 1.0.0 | 30-day recurrence and same-site ±15-minute physical-device correlation | automatic closure and any disruptive remediation |
| `backupiq_endpoint_backup` | 1.0.0 | DRMM plus Backup.net/UniView asset/alert classification | reinstall, clean install, policy/retention change, restore/delete, automatic closure |
| `low_disk_space` | 1.0.0 | read-only disk baseline, device-role, and storage-risk diagnostic | file deletion/cleanup; servers remain human-reviewed |
| `vulscan_missing_patch` | 1.0.0 | exact-KB extraction and DRMM patch-state classification | patch approval, forced install, Windows Update repair, reboot, automatic closure |
| `disk_bad_block_event_7` | 1.0.0 | Event ID 7/bad-block alert recovery and read-only storage evidence collection | physical-disk mapping, alert resolution, disk repair, completion |
| `idle_log_off` | 1.0.0 | endpoint/alert diagnostic and monitor/plumbing-failure classification | setter remains per-run approval because it has future user-session impact |

The EDR/AV health branch remains the most complete autonomous remediation branch. The other promoted playbooks intentionally stop at the exact safety boundary documented in their playbook files.

A ticket must pass all deterministic admission gates before Jason can claim it:

1. The ticket matches the health-only `Antivirus status` trigger.
2. It is not a `Security Threat detected` ticket.
3. An active Autotask configuration item is attached.
4. The CI company matches the ticket company.
5. The CI `referenceNumber` exactly matches the governed Datto RMM device UID.
6. The CI hostname exactly matches the governed Datto hostname, case-insensitively.
7. The endpoint is online when admitted.
8. The exact playbook version is durably promoted for autonomous execution.
9. Every required capability is separately authorized for `jason-autonomy-worker`.
10. Every executable Datto component used by the autonomous branch is approved as standing-safe.

Datto device identity normalization accepts the canonical `resource_id` field and the provider-native `uid` / `deviceUid` representations. This is normalization only; the exact UID and hostname equality checks remain mandatory.

## Allowed autonomous actions for the EDR/AV health branch

After all gates pass, Jason may:

1. Move the ticket to the Jason queue.
2. Set the ticket to In Progress and use Remote Support as the work type.
3. Run `Check Datto EDR/AV Status AOT Ver 12122025-1`.
4. If authoritative output does not prove `Status=Healthy`, run exactly one standing-safe `Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024` attempt.
5. Re-run the health component.
6. Write an internal Autotask note with the result.
7. Mark the ticket Complete only after authoritative output proves `Status=Healthy` and the Autotask connector verifies the post-write provider state.

The worker does not infer success from job submission, stale output, a generic exit code, or model interpretation alone.

## Hard stops and approval boundaries

The autonomous worker must not perform the following without separate explicit authority:

- reboot, shutdown, forced logoff, or other noticeable user-disruptive action;
- generic PowerShell execution;
- a clean EDR/AV uninstall;
- threat-response remediation from a `Security Threat detected` ticket;
- client-facing communication;
- work on an offline endpoint;
- work when CI/device identity is missing, inactive, cross-company, ambiguous, or mismatched;
- redispatch a job because a poll/read failed;
- continue after stale or unknown job state;
- expand its own capability grants, playbook promotion, component standing-safe status, or target scope.

When uncertainty exists about whether an action is disruptive, it is treated as disruptive and approval is required.

## Standing authority in production

The production workload principal is `jason-autonomy-worker` and uses Autotask API Resource `29682930` (Jason ReadWrite) for autonomous ticket mutations. It does not impersonate the technician who previously discussed a ticket.

Operational execute grants are bounded to:

- `automation.component.execute`
- `service.ticket.note.create`
- `service.ticket.update`

Required read grants include exact ticket, CI, resource, endpoint, automation-job, and output reads needed for deterministic admission and verification. The runtime cannot create or broaden these grants.

Current operational durable promotions are:

- `datto_edr_av@1.3.0` — `pbauto_d754251d9ae140fe9a3fa11b090eaf49`
- `dns_agent_diagnostic@1.0.0` — `pbauto_1220425a8fe24bfb8b7215203894c6c8`
- `security_log_self_heal@1.0.0` — `pbauto_cef78c667da94c32abdd4b5c1cf3b264`
- `post_error_investigation@1.0.0` — `pbauto_85ae7847089548dc95403fba2a307529`
- `unexpected_shutdown@1.0.0` — `pbauto_f7d432db2bfc4800aa7897917a3cee57`
- `backupiq_endpoint_backup@1.0.0` — `pbauto_e7f4424d9d334031aff1a1308266b41c`
- `low_disk_space@1.0.0` — `pbauto_34c69f767b964547ba92e130ee3d2bba`
- `vulscan_missing_patch@1.0.0` — `pbauto_dc728e1460844ab0aad7ef791d9738cb`
- `disk_bad_block_event_7@1.0.0` — `pbauto_198a735413704d18bc45ce233beea25f`
- `idle_log_off@1.0.0` — `pbauto_49092826d1744f41b5b07e2aabd2b1b0`

Standing-safe Datto components used by autonomous resolvers remain independently governed in the durable component-approval registry. Generic PowerShell remains per-run and is rejected for autonomous execution. A playbook promotion never makes a component standing-safe by itself.

## Runtime and persistent state

Production runtime settings include:

- `JASON_AUTONOMY_WORKER_ENABLED=true`
- `JASON_DATTO_COMPONENT_EXECUTION_AUTONOMY_ENABLED=true`
- default worker interval: 60 seconds
- default maximum active work items: 2

Worker state is persisted in:

`/var/lib/jason/openclaw/autonomy-operational-work.sqlite3`

This ledger prevents completed or already-dispatched steps from being repeated after a restart. Do not delete worker-state rows as routine operations. A row may be removed only to recover from a proven worker-state defect after the underlying code defect has been fixed and the affected provider state has been independently verified.

## Ticket lifecycle

For a newly discovered eligible ticket:

`DISCOVERED -> ADMISSION -> CLAIMED -> DIAGNOSING -> REMEDIATING (optional) -> VERIFYING -> COMPLETE`

A ticket can instead transition to waiting, blocked, or escalation states. Offline-at-admission is treated as transient and is not persisted as a permanent block. The ticket is reconsidered when later queue reconciliation sees the endpoint online.

Tickets already in the Jason queue remain eligible for resume/reconciliation under the same gates.

## Safety and verification model

The worker is fail-closed. Key invariants are:

- exact ticket/company/CI/device binding before mutation;
- no direct provider bypass;
- one governed execution plan per mutation;
- bounded remediation attempts;
- no mutation authority derived from ticket text, email, logs, endpoint output, web content, or model-generated text;
- authoritative post-action verification before completion;
- durable audit and work-state evidence;
- no autonomous privilege expansion.

## Production acceptance and activation record

The generic autonomous execution substrate was first proven on 2026-09-25 with a controlled XYZ Test Company Autotask internal-note mutation using `jason-autonomy-worker`, exactly one provider POST, and independent post-write readback.

The operational EDR/AV worker was then activated under a separate durable promotion. Its first real production reconciliation selected ticket `T20260921.0015` for `gai-lt2820`. That pass exposed an evidence-normalization defect: the internal governed Datto path returned provider-native `uid` while the worker expected canonical `resource_id`. No endpoint remediation occurred. CI and Datto identity were independently verified to match, and the endpoint was offline.

PR #349 corrected identity normalization while preserving exact UID and hostname checks. The fix was merged and deployed at revision `aaa536cef3e10edac8a1cc41595caee19be570c6`. The runtime was verified healthy with autonomy enabled. The one false blocked ledger row for ticket ID `140792` was removed after the defect was fixed. On reevaluation, the offline device correctly produced no permanent worker-state row and no provider mutation.

## Operator checks

When validating production behavior, confirm all of the following before concluding the worker is healthy:

- `jason-runtime` container health is `healthy`;
- the source revision is the intended production revision;
- `JASON_AUTONOMY_WORKER_ENABLED=true`;
- `JASON_DATTO_COMPONENT_EXECUTION_AUTONOMY_ENABLED=true`;
- the durable playbook promotion is active and matches the exact playbook version/capability set;
- required Datto components are standing-safe;
- generic PowerShell remains per-run;
- the SQLite work ledger shows only expected active/waiting/terminal items;
- Autotask ticket state and Datto job/output evidence agree with the ledger.

## Expansion procedure for additional autonomous playbooks

A new playbook is not autonomous merely because source metadata says `autonomous`. Before unattended production use, each playbook/version must have:

1. deterministic trigger and exclusion rules;
2. exact provider-neutral identity gates;
3. explicit allowed capabilities;
4. disruptive-action classification;
5. standing-safe component review where component execution is used;
6. bounded retry/remediation behavior;
7. authoritative success criteria and readback verification;
8. tests for ambiguity, stale evidence, poisoned evidence, duplicate identity, offline targets, and failure/retry paths;
9. controlled production acceptance;
10. separate durable owner promotion for that exact playbook version and capability set.

Client-facing communications remain separately governed even when the technical remediation playbook is autonomous.

### Durable promotion administration

Source metadata is nomination, not authority. Each autonomous playbook/version still requires a separate durable promotion in `playbook-autonomy.sqlite3` for its exact policy ID and allowed-capability set.

The preferred path is the authenticated owner-only MCP promotion control. If a newly deployed MCP admin control is not yet present in the current ChatGPT tool catalog, the repository also provides the bounded operator utility `python -m jason_mcp.autonomy_admin <playbook_id> --approved-by <owner-id>`. This utility is a control-plane fallback only: it performs no provider access, accepts only an owner identifier already present in `JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES`, reads the source-controlled production playbook registry, refuses any playbook not already marked `autonomy.activation=autonomous`, derives the exact version/policy/capability scope from that registry, writes the normal immutable promotion store, and appends a local JSONL audit event including the registry SHA-256 fingerprint.

The operator utility must not be used to bypass an unfinished acceptance gate. Changing source metadata to `autonomous` remains a reviewed/merged source change; the utility cannot make a shadow playbook autonomous on its own.

## Related source and documentation

- `implementation/runtime_service/src/jason_runtime/autonomy_worker_runtime.py`
- `implementation/runtime_service/src/jason_runtime/autonomy_worker_composition.py`
- `implementation/runtime_service/src/jason_runtime/datto_component_execution.py`
- `implementation/runtime_service/src/jason_runtime/autotask_ticket_update.py`
- `implementation/orchestrator/autotask_information_authorizer.py`
- `implementation/mcp_service/src/jason_mcp/autonomy_admin.py`
- `docs/architecture/JASON_AUTONOMOUS_QUEUE_OPERATING_MODEL.md`
- `docs/sessions/Jason-Autonomous-Ticket-Worker-2026-09-25.md`


## 2026-09-26 production expansion checkpoint

The 2026-09-26 expansion completed the safe autonomous branch for every production playbook currently registered. Significant production proofs included:

- the autonomous Autotask ticket-update preparation defect was corrected in PR #356 so `jason-autonomy-worker` uses the intended API-user path rather than a human trusted-principal binding;
- POST ticket `T20260923.0075` / `VZ-HYPER-V` was successfully claimed and diagnosed after that fix, then escalated because the endpoint was protected/recurring;
- BackupIQ ticket `T20260925.0003` / `APD-50399` was classified as an inactive/offline endpoint from exact DRMM and provider asset evidence, with no reinstall attempted;
- VulScan ticket `T20260925.0001` / `GAI-DT2850` exposed a normalized patch-evidence shape defect. PR #361 corrected the worker to consume `evidence.data.patches`; rerun then correctly classified `KB5124008` and `KB5126052` as `NOT_APPROVED` and performed no approval/install/reboot action;
- Low Disk Space, Disk Event ID 7, and Idle Log Off were promoted only for read-only/diagnostic branches. Cleanup, physical-disk mapping, and the Idle Log Off setter remain gated exactly as documented.

The current operating principle is now: Jason may automatically start and carry a matching ticket through the exact promoted safe branch, but it must stop at the first unapproved or disruptive boundary. No ticket-by-ticket owner approval is required merely to begin an already-promoted safe branch.

## Automatic owner promotion workflow

Technicians may create and improve playbooks without receiving authority to make them autonomous. For a production playbook whose source registry nominates an autonomous safe branch, the runtime can detect that the exact durable promotion is missing and submit a Teams owner-approval card.

The owner card is bound to the exact playbook version, policy ID, allowed capability set, source path, review status, and canonical registry-entry fingerprint. An authenticated configured owner may Approve, Deny, or Request Changes. Approval mechanically creates the exact durable `PlaybookAutonomyApproval`; it does not broaden any capability, component, or remediation branch beyond the reviewed source scope.

A changed fingerprint invalidates the old review scope. A non-owner response, copied card payload, typed approval text, or Teams membership cannot create autonomy authority.
