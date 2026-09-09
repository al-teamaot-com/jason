# Project Jason — Current Resume Point

**Updated:** 2026-09-09  
**Status:** ChatGPT Business is the preferred primary technician conversational surface, with Jason exposed through a governed read-only MCP/tool boundary. The ChatGPT/Entra/MCP path is functionally and durably proven from committed source. Command Center usage/attribution telemetry is deployed and healthy. The current workstream is documentation and System Registry reconciliation before any further runtime activation.  
**Canonical purpose:** Human-readable resume point. Current production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. this file
4. `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`
5. `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`
6. `docs/engineering/interfaces/Jason-MCP-Construction-Guide.md`
7. `docs/roadmaps/ChatGPT-Jason-MCP-Migration-Plan.md`
8. `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md`
9. `docs/sessions/ChatGPT-Business-MCP-Architecture-Pivot-2026-09-08.md`
10. `docs/sessions/ChatGPT-Jason-MCP-Durability-Acceptance-2026-09-09.md`
11. `docs/sessions/Jason-Command-Center-Usage-Attribution-Deployment-Proof-2026-09-09.md`
12. `docs/sessions/Jason-Operational-Reconciliation-Snapshot-2026-09-09.md`
13. `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
14. `docs/control/DOCUMENTATION-REGISTER.md`
15. current Git and System Registry/host evidence before asserting volatile production state

Conversation memory is context only. It is not authority.

## Active architecture

```text
Technician
    ↓
ChatGPT Business session
    ↓
ChatGPT conversation / reasoning / session context
    ↓
Jason governed MCP/tool service
    ↓
Jason identity / scope / authority / policy / approvals / audit
    ↓
Central Orchestrator
    ↓
Governed capabilities / connectors
    ↓
Approved providers
```

Durable principle:

> **ChatGPT reasons. Jason governs and executes.**

A ChatGPT tool request is a request for governed execution, not authority.

## Last durable success

### ChatGPT / Jason MCP

GitHub Issue #166 is complete.

Accepted source-built MCP checkpoint:

`727c3fa6cbcb59dab32f77632393bc5407826ed0`

Accepted live image:

`jason-mcp:source-727c3fa`

The accepted MCP surface is exactly:

- `jason_mcp_status`
- `discover_capabilities`
- `execute_read_capability`

The baseline is read-only. No write/consequential MCP tool exists. The accepted path preserves Jason identity, authority, client/scope controls, Central Orchestrator execution, provider credential isolation, evidence, provenance, and audit. Public authentication/metadata/transport acceptance and ChatGPT live tool/read acceptance were completed after source-built recreation.

### Command Center usage and attribution telemetry

Accepted live dashboard deployment checkpoint:

`ecc265ee59645154f0bc86b5aa0dc5a2e375f022`

The live observability stack includes:

- `jason-prometheus`
- `jason-grafana`
- `jason-usage-exporter.service`
- `jason-usage-attribution-exporter.service`

The live dashboard worktree remains detached and clean at the accepted deployment checkpoint.

Later telemetry source work is represented by:

`e245fef72d220cce1fea63cb811a10c8196657b8`

The scoped Showcase Telemetry validation is green at that source checkpoint. The later source has not been used to replace the accepted live dashboard worktree or activate runtime-side attribution instrumentation.

## Current workstream

The active workstream is **documentation and System Registry reconciliation**.

The architecture decision is already made. Do not resume expansion of the legacy custom conversation stack merely because older Conversation Experience tests remain in the repository. Do not perform another runtime deployment merely to make documentation match what happens to be running.

Required sequence:

1. restore the September ChatGPT/MCP governing documents to the active source lineage;
2. classify dated MCP proof records under `docs/sessions/`;
3. preserve final Issue #166 durability acceptance;
4. preserve Command Center/usage-attribution deployment proof;
5. reconcile the System Registry using J-103 lifecycle and verification rules;
6. regenerate its human-readable operational view;
7. run documentation/System Registry validation;
8. only then choose the next engineering/runtime workstream.

## Production/runtime boundary

### ChatGPT / MCP

The read-only Jason MCP service is live and functionally/durably proven. It remains an interface adapter and capability projection layer, not a second Central Orchestrator, provider client, unrestricted API proxy, secret broker, write authority, or replacement for Jason governance.

### Jason Runtime

`jason-runtime` remains the governed execution/orchestration boundary. The 2026-09-09 reconciliation snapshot observed it healthy. No runtime rebuild or restart is authorized by this documentation update.

### Teams

The direct `jason-teams-gateway` remains deployed and owns ordinary inbound Teams transport under the existing Teams architecture. Teams remains a valid secondary interface for approvals, notifications, proactive messaging, concise requests, and fallback access. Do not resume building a duplicate ChatGPT-quality conversation engine in Teams by default.

### OpenClaw

OpenClaw remains deployed for independently justified secondary functions. It is not the preferred primary technician conversational brain and must not bypass Jason identity, authority, policy, approvals, Central Orchestrator, provider governance, secrets, evidence, or audit.

### Observability

Prometheus, Grafana, the model/API usage exporter, and the usage-attribution exporter are observational surfaces. They do not grant execution authority.

## System Registry reconciliation gap

The current System Registry predates the final MCP and usage-attribution deployment state. The 2026-09-09 host reconciliation observed that the registry does not yet represent the currently running MCP and observability components.

Do not fix this by simply labeling observed processes `active`. J-103 requires stable entity identifiers, declared state, dependencies, stewardship, authority references, verification methods, evidence references, lifecycle transitions, and verification evidence.

Until reconciliation is complete, MCP-001 should remain an active engineering milestone even though its protocol, durability, OAuth, edge, and governed read behavior are functionally proven.

## Source/worktree safety

The primary worktree `/home/al/projects/jason` contains unrelated active development and must not be reset, cleaned, stashed, switched, or used as the reconciliation workspace.

The accepted live monitoring worktree `/home/al/projects/jason-dashboard-usage-telemetry-20260909` must remain at `ecc265ee59645154f0bc86b5aa0dc5a2e375f022` unless a separate governed dashboard deployment is approved.

Documentation reconciliation must use an isolated worktree/branch.

## Documentation classification correction

Several September 9 MCP proof records were historically committed on another branch beneath the retired `07-Operations/` root. Their evidence remains valuable. Their correct canonical classification is point-in-time evidence under `docs/sessions/`. Do not recreate the retired root merely to preserve those records.

## Prior lessons that must not be rediscovered

1. Do not solve arbitrary technician questions with phrase-specific code.
2. Do not reduce the architecture goal to a proving endpoint or wording.
3. ChatGPT Business owns ordinary conversational reasoning for the primary path.
4. Jason owns identity, authority, scope, policy, approvals, orchestration, provider boundaries, evidence, audit, and deterministic operational processing.
5. Do not invoke a second Jason-hosted model merely to re-reason an ordinary ChatGPT MCP request.
6. Provider collection completeness and pagination matter for exact answers.
7. Model-facing excerpts are not substitutes for deterministic complete-data analysis.
8. Provider documentation/schema is descriptive knowledge, not authority.
9. New provider integration should expand governed capabilities rather than add question logic.
10. System Registry observed state must not be promoted to verified/active without its defined lifecycle proof.

## Known remaining work

MCP identity/workspace behavior is functionally proven, but formal roadmap closure should remain conservative until System Registry reconciliation and remaining negative/isolation evidence are represented durably.

Cross-provider ChatGPT technician proof remains future work. Legacy conversational-stack simplification remains future work. Consequential MCP actions remain future work and require independent identity-first authorization, policy, approval, idempotency, precondition, evidence, audit, and recovery design.

Runtime-side usage-attribution activation remains separate from the already deployed observational dashboard/exporter surface.

## Next safe actions

1. Complete documentation reconciliation on the isolated branch.
2. Use `docs/architecture/J-103-System-Registry.md` and existing registry schemas/construction guidance to define MCP and observability registry entities.
3. Add append-only lifecycle/verification evidence only for states actually supported by 2026-09-09 proof records.
4. Regenerate `docs/operations/System-Registry-Current-Operational-State.md`.
5. Run documentation-control, registry, generated-document, and relevant deterministic tests.
6. Review the resulting diff before promotion.
7. Only after documentation and operational-state truth agree should the next runtime-side attribution or provider-expansion workstream begin.
