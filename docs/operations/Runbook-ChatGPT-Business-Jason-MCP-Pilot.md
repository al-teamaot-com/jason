# Runbook — ChatGPT Business + Jason MCP Governed Operations

**Status:** Active operational runbook  
**Updated:** 2026-09-16  
**Owner:** Platform Owner  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`  
**Current state:** `docs/control/CURRENT.md`  
**Final Datto proof:** `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`

## Purpose

Operate Jason through ChatGPT Business without bypassing Jason identity, authority, policy, approvals, Central Orchestrator execution, provider containment, evidence, or audit.

This runbook does not itself grant provider or business authority.

## Durable principle

> **ChatGPT reasons. Jason governs and executes.**

The ChatGPT app/MCP surface is an interface to Jason governance. It is not a direct provider client, secret broker, or alternate source of authority.

## Current production boundary

The bounded live governed-action deployment proven on 2026-09-16 uses:

- MCP container: `jason-mcp-pilot`;
- deployed code source: `8f1e864947a2e6e79bf47d3de14daacde7d73144`;
- image: `jason-mcp:generic-governed-8f1e864947a2`;
- image ID: `sha256:d709ca54b66d41e22bd1f67782cd5f6d681c4337bffb359b632523762a27788a`;
- mode: `governed-read-plus-actions`;
- execution coordinator: Central Orchestrator;
- `direct_provider_access=false`;
- active action capabilities: `automation.component.execute`, `service.ticket.note.create`, `service.ticket.update`;
- action authority: `jason_exact_grant_plus_per_execution_approval`.

Repository documentation commits may be newer than the deployed code source. Always distinguish current Git HEAD from the exact deployed image/code source.

## Pre-change rules

Before a consequential MCP or provider-facing change:

1. identify the exact current live image/container and rollback asset;
2. identify the exact intended Git source commit;
3. use a clean isolated worktree;
4. validate the changed source/test boundary;
5. preserve provider credential isolation;
6. preserve `direct_provider_access=false`;
7. preserve Central Orchestrator as the execution coordinator;
8. preserve exact grants and required per-execution approval for actions;
9. do not change unrelated services merely because MCP changed;
10. do not print or copy secret material into evidence/output.

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
10. record durable proof without secrets.

A ChatGPT confirmation prompt does not replace Jason authority. General approval for one action does not authorize a different target, component, argument, or disruptive side effect.

## User-disruptive actions

Jason must not autonomously perform user-disruptive operations such as reboot/shutdown, forced logoff, terminating user applications/processes, disconnecting network/VPN, or restarting services that interrupt active work.

Such operations require explicit technician approval for the exact disruptive action. When impact is uncertain, treat the action as disruptive and require approval.

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
- allowlist `AOT governed diagnostic pilot`.

The historical first execution attempt was rejected with HTTP 403. The dedicated execution identity was later corrected without falling back to the read identity or broadening arbitrary execution authority.

The final explicitly approved production proof created exactly one Datto quick job on one provider attempt. Immediate readback returned:

- result `status=accepted`;
- `job_status=active`;
- `readback_verified=true`;
- `completion_verified=false`;
- durable `job_uid=422d680b-a5ce-4473-b8e8-5d682ec85682`.

Read-only `automation.job.read` later returned terminal status `completed` for that exact job.

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

A monitoring-only refresh should use:

```bash
JASON_REPO_ROOT="$PWD" infrastructure/showcase/deploy_production_health_dashboard.sh
```

The deployment script is rollback-protected and must verify core Jason container identity isolation.

## Evidence to preserve

For each governed deployment/action milestone preserve, without secrets:

- repository source commit;
- deployed image tag and image ID;
- rollback image/container identity;
- MCP status/governance snapshot;
- client-delivered tool surface when relevant;
- exact action target/scope;
- approval evidence reference;
- action correlation ID;
- provider attempt count/classification;
- durable job/resource reference when needed for readback;
- final governed readback correlation/result;
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
- rollback identity cannot be established;
- proposed provider permission change exceeds the approved least-privilege scope.

## Current acceptance conclusion

The bounded ChatGPT → Jason MCP → Central Orchestrator → Autotask/Datto governed-action path is operationally proven for the accepted pilots. Future provider/action expansion is a new governed change, not a continuation of the completed proof.
