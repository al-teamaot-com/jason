# Project Jason — Current Resume Point

**Updated:** 2026-09-08  
**Status:** Preferred technician architecture is **ChatGPT Business as the primary conversational surface with Jason exposed through a governed MCP/tool boundary**. The existing Teams/OpenClaw/Jason production topology remains valid until deliberately changed and re-verified. MCP-001 is the active engineering workstream and is not yet production-proven.  
**Canonical purpose:** Human-readable resume point. Current production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. this file
4. `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`
5. `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`
6. `docs/engineering/interfaces/Jason-MCP-Construction-Guide.md`
7. `docs/engineering/interfaces/ChatGPT-Business-MCP-Platform-Constraints-2026-09-08.md`
8. `docs/roadmaps/ChatGPT-Jason-MCP-Migration-Plan.md`
9. `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md`
10. `docs/sessions/ChatGPT-Business-MCP-Architecture-Pivot-2026-09-08.md`
11. `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
12. `docs/control/DOCUMENTATION-REGISTER.md`
13. current Git and System Registry/host evidence before asserting live production state

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
Datto RMM / Autotask / Microsoft 365 / IT Glue / other approved providers
```

Durable principle:

> **ChatGPT reasons. Jason governs and executes.**

A ChatGPT tool call is a request for governed execution, not authority.

## Why this changed

The Teams-centered conversational path increasingly required Jason to reproduce mature conversational-agent behavior: natural multi-turn dialogue, context continuity, tool selection, iterative reasoning, and answer synthesis.

Recent work proved useful mechanisms such as provider documentation knowledge, native tool calling, meaningful capability-derived tools, complete collection reads, and deterministic evidence analysis, but the architecture still asked Jason to imitate ChatGPT while also carrying Jason's real responsibilities.

The selected redesign uses AOT's existing ChatGPT Business sessions for normal conversation/reasoning and keeps Jason focused on constitutional governance and execution.

## Constitutional boundary

Jason remains responsible for:

- authenticated identity binding;
- organization/client scope;
- capability authorization;
- risk/policy enforcement;
- approvals;
- read-versus-action authority;
- idempotency/preconditions/resource limits;
- provider credential isolation;
- Central Orchestrator execution;
- evidence/provenance;
- audit;
- deterministic analysis;
- fail-closed behavior.

Do not move these controls into ChatGPT prompts or rely on ChatGPT app access as authority.

## Cost rule

For the ChatGPT Business path, use **one AI brain per interaction whenever practical**.

The technician's ChatGPT session handles ordinary conversation, context, reasoning, tool selection, comparison, and synthesis.

Jason should not invoke a second hosted model merely to reinterpret or restate the same request.

Jason-side model calls remain allowed only when a specific governed capability genuinely requires them. Use the least-cost suitable model by policy and escalate only when justified.

Keep mechanical work deterministic inside Jason where practical: pagination, exact counts, filtering, grouping, distinct values, bounded lists, and governed joins/correlation.

## Verified ChatGPT Business MCP constraints — 2026-09-08

Official OpenAI documentation was re-checked before implementation planning. Current constraints that materially affect design:

- full MCP/developer mode is available to ChatGPT Business on ChatGPT web;
- the feature is beta and may change;
- Business admins/owners control developer mode and publication;
- Business does not currently provide the same per-user/per-app RBAC controls as Enterprise/Edu;
- ChatGPT connects to **remote MCP servers**, not directly to a local-only server;
- for private/on-prem/local MCP servers, OpenAI currently recommends **Secure MCP Tunnel** rather than exposing the service directly to the public Internet;
- OAuth/OIDC designs should support refresh tokens / `offline_access` if persistent connectivity is required;
- custom MCP servers no longer need artificial `search` and `fetch` tools;
- Business app tool/metadata updates currently require recreate/republish behavior and approved tool definitions are effectively frozen snapshots;
- custom MCP apps are currently web-only, not mobile;
- ChatGPT can use multiple apps in one prompt;
- ChatGPT write confirmations are supplemental and do not replace Jason's own action governance.

Supporting research record:

`docs/engineering/interfaces/ChatGPT-Business-MCP-Platform-Constraints-2026-09-08.md`

## Active workstream

**MCP-001 — ChatGPT Business + Jason read-only MCP foundation**

Completed architecture/documentation steps:

- accepted ADR-010;
- defined J-104 target architecture;
- defined MCP construction guidance;
- created migration roadmap;
- created pilot runbook;
- verified current ChatGPT Business/MCP platform constraints against official OpenAI documentation;
- set MCP-001 active in `docs/roadmaps/Jason-Roadmap-Status.json`.

## Next implementation sequence

1. Choose the smallest supported remote-connectivity pattern for the Jason host, investigating OpenAI Secure MCP Tunnel first.
2. Define the concrete Jason MCP service component contract and System Registry entity/schema usage.
3. Implement a read-only MCP adapter over the existing capability/resource catalog and Central Orchestrator.
4. Expose a small, stable, model-friendly tool set generated from governed capability metadata.
5. Prove MCP cannot call connectors/providers directly.
6. Prove identity, scope, client isolation, secret isolation, evidence, audit, and fail-closed behavior locally.
7. Prove deterministic complete-collection analysis through MCP.
8. Configure supported authentication/OAuth behavior.
9. Publish only to a limited ChatGPT Business pilot after local proof.
10. Measure technician fluidity, tool reliability, latency, and duplicate Jason-side API spend.
11. Add a second provider and prove cross-provider reasoning.
12. Simplify/retire legacy conversational components only after replacement proof.

## Components to preserve

Do not redesign or discard these merely because the conversational surface changes:

- Central Orchestrator;
- capability/resource registry/catalog;
- identity and authority services;
- execution policy and approvals;
- provider/connector boundaries;
- OpenBao/secrets architecture;
- evidence/provenance/audit systems;
- deterministic collection analysis;
- provider documentation/schema knowledge where useful;
- usage/cost ledger;
- System Registry;
- Teams transport for retained secondary roles;
- OpenClaw components with independently justified value.

## Components to stop expanding by default

Until MCP is evaluated, do not add non-critical complexity to components whose main purpose is to recreate normal ChatGPT conversation behavior inside Jason:

- custom semantic conversation routers;
- custom investigation decision state machines;
- question-specific routing or phrase maps;
- duplicate full conversation memory;
- elaborate prompt rules compensating for missing native agent behavior;
- duplicate model calls that re-reason a request already reasoned by the ChatGPT session.

Existing production components remain until governed replacement/retirement criteria are met.

## Teams role

Teams remains a valid secondary interface for approvals, notifications, proactive messages, concise operational requests, and fallback access.

The existing direct Teams gateway work remains valid evidence. The MCP pivot does not itself change production topology.

Key historical/current references:

- `docs/decisions/ADR-009-Direct-Microsoft-Teams-Ingress.md`
- `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`
- `docs/sessions/Teams-Conversation-Working-Baseline-Proof-2026-08-19.md`
- `docs/operations/Runbook-Teams-Integration.md`

## OpenClaw role

OpenClaw remains deployed infrastructure at the time of this decision and may retain justified secondary functions such as proactive/outbound transport, specialist tooling, or migration compatibility.

It is not the preferred primary technician conversational brain.

OpenClaw must not bypass Jason identity, authority, policy, approvals, Central Orchestrator, provider governance, secrets, evidence, or audit boundaries.

## Provider/integration direction

New integrations should expand Jason's observable/action world without teaching Jason question-specific workflows.

Preferred ingredients:

```text
governed connector
+ credential reference
+ capability/resource manifest
+ live provider documentation/schema source where useful
+ pagination/completeness behavior
+ deterministic analysis support
+ evidence/provenance/audit
+ governance/lifecycle metadata
```

Provider documentation/schema is descriptive knowledge only. It does not automatically grant execution authority.

## MCP tool rules

Expose meaningful governed tools derived from Jason capability/resource metadata.

Prefer concepts such as endpoint search/read, endpoint audit/inventory, alerts, sites, Autotask resources, Microsoft 365 identity/license/sign-in state, and deterministic evidence analysis.

Do not create phrase-specific tools, unrestricted HTTP/provider tools, direct connector handles, or opaque internal operation IDs as the primary model vocabulary.

## Initial security boundary

The first MCP pilot is read-only.

Before publication prove:

1. supported caller/workspace authentication;
2. Jason principal/organization binding before execution;
3. client/tenant isolation;
4. capability-specific authorization;
5. no credential exposure to ChatGPT;
6. bounded structured evidence;
7. provenance/audit for every governed execution;
8. resource/rate limits and abuse controls;
9. rapid disable/revocation/rollback;
10. Central Orchestrator remains sole execution coordinator.

Consequential actions remain a later workstream and retain all normal Jason authority, policy, approval, precondition, idempotency, evidence, audit, and recovery requirements.

## Production/runtime caution

This document records the target direction and active engineering workstream, not a claim that MCP is deployed.

Before asserting current production state, inspect current Git, System Registry declared/observed/verified state, current host/container/service evidence, and relevant deployment records.

The current Teams/OpenClaw/Jason environment must remain recoverable during the MCP pilot.

## Prior conversational lessons that must not be rediscovered

1. Do not solve arbitrary technician questions with phrase-specific code.
2. Do not reduce the architecture goal to a proving endpoint/question.
3. Provider collection completeness and pagination matter for exact counts/lists.
4. Model-facing excerpts are not substitutes for deterministic complete-data analysis.
5. Meaningful tool descriptions are superior to opaque operation references.
6. Live provider documentation/schema can improve knowledge but does not grant authority.
7. Prompt rules cannot compensate indefinitely for an unsuitable conversational architecture.
8. Jason should not duplicate work already performed by the technician's ChatGPT session.
9. Governance belongs in deterministic Jason boundaries, not hidden in conversational behavior.
10. New provider integration should be plumbing/capability registration, not new question logic.

## Governing records for this pivot

- `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`
- `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`
- `docs/engineering/interfaces/Jason-MCP-Construction-Guide.md`
- `docs/engineering/interfaces/ChatGPT-Business-MCP-Platform-Constraints-2026-09-08.md`
- `docs/roadmaps/ChatGPT-Jason-MCP-Migration-Plan.md`
- `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md`
- `docs/sessions/ChatGPT-Business-MCP-Architecture-Pivot-2026-09-08.md`

## Next safe action

Investigate and select the remote connectivity/authentication pattern for a read-only Jason MCP service, with OpenAI Secure MCP Tunnel as the first candidate for the on-prem Jason host. Then define the smallest MCP server component that routes exclusively through existing governed capability/Central Orchestrator boundaries.
