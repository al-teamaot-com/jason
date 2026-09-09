# Project Jason — Current Resume Point

**Updated:** 2026-09-09  
**Status:** ChatGPT Business is the preferred primary technician conversational surface, with Jason exposed through a governed read-only MCP/tool boundary. The ChatGPT/Entra/MCP path is functionally and durably proven from committed source. Command Center usage/attribution telemetry is deployed and healthy. The MCP, public edge, and observability topology is now represented and verified in the governed System Registry. MCP-001 is complete; the next technician-experience workstream is the remaining MCP-002 identity/workspace isolation proof.  
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
9. `docs/operations/System-Registry-Current-Operational-State.md`
10. `docs/sessions/ChatGPT-Business-MCP-Architecture-Pivot-2026-09-08.md`
11. `docs/sessions/ChatGPT-Jason-MCP-Durability-Acceptance-2026-09-09.md`
12. `docs/sessions/Jason-Command-Center-Usage-Attribution-Deployment-Proof-2026-09-09.md`
13. `docs/sessions/Jason-Operational-Reconciliation-Snapshot-2026-09-09.md`
14. `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
15. `docs/control/DOCUMENTATION-REGISTER.md`
16. current Git and fresh host evidence before asserting volatile production state

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

### System Registry reconciliation

The 2026-09-09 MCP and observability reconciliation is represented by governed registry entities and append-only verification events.

The current generated operational view contains `31` registered entities with effective lifecycle counts:

- `verified=14`
- `configured=4`
- `registered=13`

New verified topology includes:

- `resource.aws-zerotier-relay`
- `component.jason-mcp`
- `component.jason-usage-exporter`
- `component.jason-usage-attribution-exporter`
- `component.jason-prometheus`
- `component.jason-grafana`
- `deployment.jason-chatgpt-mcp-observability-pilot`

The new deployment is modeled as an extension of the previously verified single-host pilot rather than rewriting the historical Teams/OpenClaw deployment declaration.

MCP-001 — ChatGPT Business + Jason read-only MCP foundation — is therefore complete.

## Current workstream

The active technician-experience workstream is **MCP-002 — ChatGPT Business identity/workspace binding pilot**.

The positive path is already proven: ChatGPT authenticates through Entra, discovers the intended three-tool read-only surface, and completes governed live reads.

The remaining work is to preserve durable negative/isolation evidence for the identity/workspace boundary before calling MCP-002 complete. This should use the existing read-only service and must not introduce a write surface or direct provider bypass.

Do not resume expansion of the legacy custom conversation stack merely because older Conversation Experience tests remain in the repository.

Do not perform a runtime rebuild merely because later attribution instrumentation exists in source. Runtime-side attribution activation remains a separate governed decision.

## Production/runtime boundary

### ChatGPT / MCP

The read-only Jason MCP service is live, source-durable, publicly accepted, and represented as a verified System Registry component. It remains an interface adapter and capability projection layer, not a second Central Orchestrator, provider client, unrestricted API proxy, secret broker, write authority, or replacement for Jason governance.

### Public edge

The existing AWS Caddy/ZeroTier relay is represented as `resource.aws-zerotier-relay` and verified from the September 8/9 edge and MCP acceptance evidence. It remains the public ingress relay for the separately named Teams and MCP routes.

### Jason Runtime

`jason-runtime` remains the governed execution/orchestration boundary. The 2026-09-09 reconciliation snapshot observed it healthy. No runtime rebuild or restart was required by the documentation or System Registry reconciliation.

### Teams

The direct `jason-teams-gateway` remains deployed and owns ordinary inbound Teams transport under the existing Teams architecture. Teams remains a valid secondary interface for approvals, notifications, proactive messaging, concise requests, and fallback access. Do not resume building a duplicate ChatGPT-quality conversation engine in Teams by default.

### OpenClaw

OpenClaw remains deployed for independently justified secondary functions. It is not the preferred primary technician conversational brain and must not bypass Jason identity, authority, policy, approvals, Central Orchestrator, provider governance, secrets, evidence, or audit.

### Observability

Prometheus, Grafana, the model/API usage exporter, and the usage-attribution exporter are now represented as verified observational components in the System Registry. They do not grant execution authority.

## System Registry reconciliation state

The MCP and current observability topology reconciliation is complete for the evidence available on 2026-09-09.

The registry deliberately records these entities as `configured` baseline declarations with append-only transitions to effective `verified` state. It does not call them `active`; `verified` means the registered verification method is satisfied by governed evidence.

The reconciliation does not claim that unrelated logical providers, capabilities, identity bindings, or governance gates are verified merely because the physical topology is healthy.

The generated human view remains subordinate to the machine-readable registry and lifecycle history.

## Source/worktree safety

The primary worktree `/home/al/projects/jason` contains unrelated active development and must not be reset, cleaned, stashed, switched, or used as the reconciliation workspace.

The accepted live monitoring worktree `/home/al/projects/jason-dashboard-usage-telemetry-20260909` must remain at `ecc265ee59645154f0bc86b5aa0dc5a2e375f022` unless a separate governed dashboard deployment is approved.

Documentation/System Registry reconciliation uses isolated Git branches and does not require touching either protected worktree.

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

MCP-002 remains active until negative/isolation behavior for the ChatGPT/Entra/workspace identity boundary is durably proven.

MCP-003 cross-provider ChatGPT technician proof remains planned.

MCP-004 legacy conversational-stack simplification remains planned.

Consequential MCP actions remain future work and require independent identity-first authorization, policy, approval, idempotency, precondition, evidence, audit, and recovery design.

Runtime-side usage-attribution activation remains separate from the already deployed observational dashboard/exporter surface.

## Next safe actions

1. Validate the isolated System Registry reconciliation branch with repository CI, including schema/lifecycle tests and generated-document freshness.
2. Keep documentation PR #169 separate from the registry reconciliation so authority/evidence changes remain reviewable in sequence.
3. After the documentation and registry branches are accepted in order, execute the remaining MCP-002 negative/isolation proof using the existing read-only MCP surface.
4. Preserve evidence for unknown/unbound identity, invalid tenant/workspace context, missing authority, and client/scope isolation to the extent those cases can be safely exercised in the current Business/Entra pilot.
5. Do not introduce write tools while completing MCP-002.
6. Only after MCP-002 is closed should MCP-003 cross-provider technician proof become the primary technician-experience workstream.
