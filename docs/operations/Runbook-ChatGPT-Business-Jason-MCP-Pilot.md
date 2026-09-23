# Runbook — ChatGPT Business + Jason MCP Governed Operations

**Status:** Active operational runbook  
**Updated:** 2026-09-16  
**Owner:** Platform Owner  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`  
**Current state:** `docs/control/CURRENT.md`  
**Datto execution proof:** `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`  
**Cross-chat/output proof:** `docs/sessions/Jason-Datto-RMM-Cross-Chat-Output-Proof-2026-09-16.md`

## Purpose

Operate Jason through ChatGPT Business without bypassing Jason identity, authority, policy, approvals, Central Orchestrator execution, provider containment, evidence, or audit.

This runbook does not itself grant provider or business authority.

## Durable principle

> **ChatGPT reasons. Jason governs and executes.**

The ChatGPT app/MCP surface is an interface to Jason governance. It is not a direct provider client, secret broker, or alternate source of authority.

## Current production boundary

The bounded live governed-action deployment proven on 2026-09-16 uses:

- MCP container: `jason-mcp-pilot`;
- deployed code source: `26704f0600bbc6c48c790c9b9ff501a3b5ec3aad`;
- image: `jason-mcp:generic-governed-26704f0600bb`;
- mode: `governed-read-plus-actions`;
- execution coordinator: Central Orchestrator;
- `direct_provider_access=false`;
- generic governed execution tool: enabled;
- active action capabilities include `automation.component.execute`, `service.ticket.note.create`, and `service.ticket.update`;
- Datto follow-up reads include `automation.job.read` and `automation.job.output.read`;
- action authority: `jason_exact_grant_plus_server_governed_approval_policy`;
- Datto approval policy: `server_classified_standing_safe_or_per_run`.

Repository documentation/observability commits may be newer than the deployed MCP code source. Always distinguish Git branch HEAD from the exact deployed image/code source.

## Pre-change rules

Before a consequential MCP or provider-facing change:

1. identify the exact current live image/container and rollback asset;
2. identify the exact intended Git source commit;
3. use a clean isolated worktree;
4. validate the changed source/test boundary;
5. preserve provider credential isolation;
6. preserve `direct_provider_access=false`;
7. preserve Central Orchestrator as the execution coordinator;
8. preserve exact grants and the server-governed approval policy;
9. preserve fail-closed Datto classification: `standing_safe` only for explicitly classified non-disruptive diagnostics, `per_run` for disruptive/state-changing execution, and explicit approval for `per_run`;
10. do not change unrelated services merely because MCP changed;
11. do not print or copy secret material into evidence/output.

## MCP deployment sequence

For an approved MCP-only source promotion:

1. **Observe** current MCP image/container, public binding, action surface, governance status, and rollback asset.
2. **Pin** the exact approved Git source commit.
3. **Build** a candidate from the authoritative `infrastructure/jason-mcp/Dockerfile` using a positively established base image.
4. **Validate** the changed contract/tests before touching the live container.
5. **Preserve rollback** by retaining the current image and timestamped container.
6. **Reconstruct launch** from current non-secret Docker metadata; do not guess mounts/network/port/user/restart policy.
7. **Start candidate** without restarting unrelated runtime/OpenBao/provider services.
8. **Verify health/auth/transport** and the delivered ChatGPT tool surface.
9. **Verify governance**: Central Orchestrator, `direct_provider_access=false`, exact write/action profile.
10. **Run a harmless governed read** as post-deployment smoke proof.
11. **Do not run a provider mutation merely as a generic smoke test.** A mutation requires its own exact authority and approval.
12. **Record** source SHA, image ID, rollback identity, health/governance proof, and any separately approved live action evidence.

## MCP rollback

If candidate acceptance fails:

1. remove/stop only the failed candidate as needed;
2. restore the exact preserved MCP rollback container/image;
3. verify public health/auth/transport;
4. verify the expected authorized tool surface;
5. verify Central Orchestrator and `direct_provider_access=false`;
6. run one harmless governed read;
7. record rollback evidence.

Do not destroy provider credentials or roll back unrelated services unless separate evidence shows those components were changed.

## Capability discovery

Discovery/registration is not execution authority.

A read/action may proceed only when the capability is active and currently exposed, the authenticated requester has the required Jason authority, client/tenant scope matches, provider authority independently permits the operation, and any required approval is valid for the exact request.

`discover_capabilities.operation` is exact registry metadata, not a natural-language synonym. An exact object lookup may legitimately be supported through a `search` capability.

## Governed action sequence

For any bounded action:

1. perform the smallest governed pre-read needed to establish target/state;
2. resolve exact target identifiers through Jason rather than accepting ambiguous model inference;
3. confirm the action capability is active;
4. confirm requester exact grant/role eligibility;
5. obtain the required approval for the exact action/target/arguments;
6. execute only through the governed action surface;
7. respect provider attempt limits and do not retry through broader credentials;
8. capture bounded action result and correlation ID;
9. perform governed readback/job verification;
10. retrieve bounded provider output only through an active governed read capability when required;
11. record durable proof without secrets.

A ChatGPT confirmation prompt does not replace Jason authority. General approval for one action does not authorize a different target, component, argument, retry, or disruptive side effect. For `per_run` actions, a consumed per-execution approval must not be reused in a later chat or later execution. `standing_safe` Datto diagnostics rely on server classification and task authority rather than a consumable per-run approval.

## User-disruptive actions

Jason must not autonomously perform user-disruptive operations such as reboot/shutdown, forced logoff, terminating user applications/processes, disconnecting network/VPN, or restarting services that interrupt active work.

Such operations require explicit technician approval for the exact disruptive action. When impact is uncertain, treat the action as disruptive and require approval.

## Datto component approval classification

Datto component approval mode is server-controlled policy, not a caller argument.

- `standing_safe`: an exact, pre-classified, non-disruptive diagnostic component. A technician request to investigate/check/troubleshoot provides task authority; Jason does not require an additional per-run approval prompt.
- `per_run`: a disruptive or state-changing component. Explicit technician approval is required for that exact execution before orchestration/provider execution.
- unknown, missing, invalid, or mismatched classification: fail closed.

The caller cannot promote a `per_run` component to `standing_safe`. Exact Jason grant, target scope, component identity, variables, provider identity, Central Orchestrator routing, one-attempt limits, and audit remain authoritative regardless of approval mode.

Current production `standing_safe` Datto components:

- `Get-DNS Settings AOT Ver 06042025-1` — UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- `Check Datto EDR/AV Status AOT Ver 12122025-1` — UID `8cb0f063-5875-452e-88ad-2e1748ed0fd0`.

No reboot component is currently in production scope.

## Autotask accepted state

The bounded controlled proof used XYZ Test Company ticket `T20191013.0001` and changed priority `3` → `2` through `service.ticket.update`. A later governed read independently confirmed `priority=2`.

Do not repeat that mutation merely to prove the path again. This proof does not grant arbitrary Autotask CRUD.

## Datto RMM accepted state

Controlled endpoint:

- `AOT-50282`;
- device UID `69571572-83f7-1e33-9cdf-01717d4e74a4`.

Controlled diagnostic component:

- `Get-DNS Settings AOT Ver 06042025-1`;
- component UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- allowlist `AOT governed diagnostic pilot`;
- variables: none.

The historical first execution attempt was rejected with HTTP 403. The dedicated execution identity was later corrected without falling back to the read identity or broadening arbitrary execution authority.

The original completed governed execution proof used job `422d680b-a5ce-4473-b8e8-5d682ec85682`.

A later cross-chat proof on source `e9c7a763...` deliberately did not reuse the earlier approval. After a fresh explicit AOT Owner approval, Jason created exactly one new Datto quick job on one provider attempt:

- `job_uid=741a2d02-587d-4348-9f26-b4982d337732`;
- action correlation `corr_mcp_action_d49b19600e6f4c50a60f43892af66458`;
- immediate result `status=accepted`;
- immediate `job_status=active`;
- `readback_verified=true`;
- `completion_verified=false` while asynchronous.

Read-only `automation.job.read` later returned terminal `completed` for that exact job. The terminal read correlation was `corr_mcp_12eafe5022dc42cb8a42091be669d8cf`.

Jason then used `automation.job.output.read` with the exact job UID, device UID, component UID, and `stream=stdout`. The governed read returned one untruncated output record; output-read correlation was `corr_mcp_2c624f2cda234afab3be73b70906e8b0`. This proves the current bounded JSON-array transport/output path as well as the execution path.

## Critical Datto asynchronous-job rule

Datto quick jobs are asynchronous. An approved execution returning:

- `status=accepted`;
- `job_status=active`;
- `readback_verified=true`;
- `completion_verified=false`;
- a durable `job_uid`

is **not a failed execution**. It means Datto accepted the job and Jason verified its durable identity/readback while the provider job was still running.

When this occurs:

1. do **not** execute the component again;
2. use the returned `job_uid` with read-only `automation.job.read`;
3. poll only as needed until a terminal state is observed;
4. treat terminal `completed`/success as completion proof;
5. treat terminal failure/cancel/error as provider execution failure;
6. preserve action and final-read correlation IDs.

The component execution itself remains max one provider mutation/attempt unless a new execution is separately approved.

## Datto component-output rule

When actual component output is needed after a job has a durable identity, use `automation.job.output.read`; do not bypass Jason to call Datto directly.

For the current Datto implementation, bind the output read to all of the following exact values:

- `resource_id`: the durable Datto job UID returned by the approved execution;
- `device_uid`: the exact governed target device UID;
- `component_uid`: the exact governed component UID;
- `stream`: `stdout` or `stderr` as required.

For normal diagnostic output, first verify the job reaches a terminal state with `automation.job.read`, then retrieve `stdout`. Preserve the output-read correlation ID and truncation/match metadata. Do not treat output retrieval as authority for another execution.

The provider output endpoint may return a JSON array. Jason's shared transport accepts bounded JSON objects or arrays and continues to reject unsupported scalar responses. Source `e9c7a76318aa12b150194875726b1ba54bf6d61b` is the live-proven array-transport release.

## Datto scope rule

The current proof is bounded to the configured pilot scope. It does not authorize:

- arbitrary Datto components;
- arbitrary endpoint selection;
- arbitrary shell/script text;
- unapproved variables;
- reboot or other disruptive action;
- automatic expansion of Device Visibility/API Component Level;
- credential fallback to a broader identity.

Expand scope only through a separate capability/allowlist/authority decision.

## Production observability

Grafana/Prometheus monitoring is repository-provisioned under `infrastructure/showcase`.

The focused `Jason Governed Actions` dashboard uses secret-safe local metrics for MCP health, deployment contract, credential mounts, bounded Datto execution configuration, rollback state, and alerts. Monitoring does not call Datto or other providers directly and does not grant action authority.

The production-health exporter must recognize the exact current deployed MCP image/source. When MCP is promoted without changing the bounded execution contract, reconcile `JASON_EXPECTED_MCP_IMAGE` and `JASON_EXPECTED_MCP_SOURCE_REVISION` through the repository-provisioned production-health unit and then run the existing monitoring-only deployment. Do not restart/recreate MCP merely to update observability expectations.

A monitoring-only refresh should use:

```bash
JASON_REPO_ROOT="$PWD" infrastructure/showcase/deploy_production_health_dashboard.sh
```

The deployment script is rollback-protected and must verify core Jason container identity isolation. It may restart the observability exporter and refresh Prometheus/Grafana, but it must not restart/recreate Jason runtime, Jason MCP, OpenBao, or provider-facing services.

## Evidence to preserve

For each governed deployment/action milestone preserve, without secrets:

- repository source commit;
- deployed image tag and image ID when established;
- rollback image/container identity when relevant;
- MCP status/governance snapshot;
- client-delivered tool surface when relevant;
- exact action target/scope;
- approval evidence reference;
- action correlation ID;
- provider attempt count/classification;
- durable job/resource reference when needed for readback;
- final governed readback correlation/result;
- output-read correlation/result when output is part of the goal;
- relevant tests/acceptance output;
- documentation/Grafana reconciliation state.

## System Registry

Narrative proof must not be treated as System Registry lifecycle promotion. Update structured registry truth only through its authoritative governed registration/verification path. If no write path is exposed, leave registry state unchanged and document the gap rather than inventing state.

## Stop conditions

Stop expansion or promotion if:

- authenticated identity/scope cannot be established;
- direct provider access becomes possible from ChatGPT;
- provider credentials or secrets reach ChatGPT;
- MCP bypasses Central Orchestrator;
- action capability becomes reachable without exact grant/required approval;
- provider failure retries through a broader identity;
- post-action durable state/job result cannot be verified;
- required component output cannot be retrieved through the governed path when output is part of the proof;
- rollback identity cannot be established for a consequential deployment;
- proposed provider permission change exceeds the approved least-privilege scope.

## Current acceptance conclusion

The bounded ChatGPT → Jason MCP → Central Orchestrator → Datto workflow is operationally proven across chats for exact target/component resolution, historical fresh per-execution approval, one-attempt component execution, terminal readback, and actual component StdOut retrieval. The current production policy additionally supports server-classified `standing_safe` diagnostics without a separate per-run approval while preserving `per_run` approval for disruptive or state-changing execution. Future provider/action expansion is a new governed change, not a continuation of the completed proof.

## AOT employee access and JIT identity enrollment

ChatGPT Business workspace publication is the outer application-distribution boundary. Jason remains the authoritative identity and authorization boundary after the custom app is invoked.

An authenticated Microsoft user may be automatically enrolled into Jason only when all of the following are true:

1. the Entra access token validates for Jason's fixed AOT tenant and MCP resource/scope;
2. Microsoft Graph resolves the exact authenticated Entra object ID;
3. the directory account is enabled;
4. the authoritative `userPrincipalName` belongs to `teamaot.com` or `teamaom.com`;
5. no conflicting active Jason identity exists for the deterministic Entra-derived principal.

Eligible first-time users receive a durable Microsoft-object-to-Jason identity binding and an active `human` Jason identity in organization `aot`. They receive **no individual authority grants during enrollment**.

This intentionally maps first-time AOT employees to the existing **RO (Read Only)** baseline. JKD-001 already evaluates `organization:aot` grants in addition to principal-specific grants; the organization currently supplies the approved shared observe-only provider-read baseline. Tech, Admin, and Owner are explicit elevations through separately governed authority grants and must never be inferred from email domain, Microsoft group membership, ChatGPT workspace membership, title, or conversational request.

The accepted role direction remains:

- **Owner** — highest AOT Jason authority, still subject to high-risk controls and explicit approval policy;
- **Admin** — operational administration without constitutional/governance-policy ownership or self-elevation;
- **Tech** — scoped operational read/action authority for approved capabilities and resources;
- **RO** — observe-only baseline; cannot execute, mutate, approve, or self-elevate.

Fail closed for disabled accounts, missing/invalid UPNs, external/guest UPNs, non-AOT domains, Microsoft directory failure, identity conflicts, or inactive bindings.

The MCP server does not independently receive a trustworthy ChatGPT Business workspace-membership claim in the Microsoft token. Workspace membership is therefore enforced by ChatGPT Business app publication/distribution, while Jason independently enforces the AOT Microsoft identity/domain and Jason role/authority boundary. Do not treat either layer as a substitute for the other.
