# Project Jason — Current Resume Point

**Updated:** 2026-09-08  
**Status:** The preferred technician conversational architecture is now **ChatGPT Business as the primary conversational surface with Jason exposed through a governed MCP/tool boundary**. The existing Teams/OpenClaw/Jason production topology remains valid until deliberately changed and re-verified; the new MCP path is the active engineering workstream and is not yet production-proven.  
**Canonical purpose:** Human-readable resume point for current work. Current production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

Future sessions should read, in order:

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. this file
4. `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`
5. `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`
6. `docs/roadmaps/ChatGPT-Jason-MCP-Migration-Plan.md`
7. `docs/sessions/ChatGPT-Business-MCP-Architecture-Pivot-2026-09-08.md`
8. `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
9. `docs/control/DOCUMENTATION-REGISTER.md`
10. `docs/control/HOW-TO-DOCUMENT-JASON.md`
11. current Git and System Registry/host evidence before asserting live production state

Conversation memory is context only. It is not authority.

## Current architecture direction — 2026-09-08

The accepted preferred technician path is:

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

The durable operating principle is:

> **ChatGPT reasons. Jason governs and executes.**

A ChatGPT tool call is a request for governed execution, not authority.

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

## Why the architecture changed

The Teams-centered conversational workstream increasingly required Jason to reproduce capabilities already supplied effectively by a mature conversational runtime: natural multi-turn dialogue, follow-up context, tool selection, iterative reasoning, and answer synthesis.

The project proved several useful mechanisms — provider documentation knowledge, native tool calling, meaningful capability-derived tools, complete collection reads, deterministic evidence analysis — but the overall pattern remained unnecessarily complex because Jason was still being asked to imitate the normal ChatGPT experience.

The project owner selected ChatGPT Business + Jason MCP as the initial redesign because it should:

- provide the most fluid technician experience;
- maximize value from existing ChatGPT Business seats;
- reduce duplicate OpenAI API reasoning calls;
- reduce custom conversational code;
- preserve Jason's constitutional authority/governance model;
- make provider expansion capability/resource-driven rather than question-driven.

## Cost rule

For the ChatGPT Business path, the default is **one AI brain per interaction**.

The technician's ChatGPT session handles ordinary conversation, context, reasoning, tool selection, comparison, and synthesis.

Jason should **not** invoke a second OpenAI API model merely to interpret or restate the same request.

Jason-side hosted-model calls remain allowed when a specific governed capability genuinely requires them. When required, use the least-cost suitable model by policy and escalate only when justified.

Deterministic work should remain inside Jason where practical, including:

- pagination;
- exact counts;
- filtering;
- grouping;
- distinct values;
- bounded lists;
- governed joins/correlation;
- other mechanical large-dataset operations.

ChatGPT Business subscription usage and OpenAI API usage are separate cost domains; Jason-side model cost must remain independently measurable.

## Active workstream

The active P0 workstream is:

**MCP-001 — ChatGPT Business + Jason read-only MCP foundation**

Immediate sequence:

1. verify current ChatGPT Business custom MCP/app requirements and supported authentication patterns;
2. define the Jason MCP service/component contract;
3. define System Registry registration/lifecycle requirements for the MCP service;
4. build a read-only MCP adapter over the existing capability/resource catalog and Central Orchestrator;
5. expose a small meaningful tool set generated from governed capability metadata;
6. prove MCP cannot invoke connectors/providers directly;
7. prove identity, scope, client isolation, evidence, audit, secret isolation, and fail-closed behavior;
8. prove deterministic complete-collection analysis through MCP;
9. configure/publish a limited ChatGPT Business pilot only after local proof;
10. measure technician fluidity, tool reliability, latency, and duplicate Jason-side API spend;
11. add a second provider and prove cross-provider reasoning;
12. simplify/retire legacy conversational components only after the MCP replacement is proven.

The detailed plan is:

`docs/roadmaps/ChatGPT-Jason-MCP-Migration-Plan.md`

## Components to preserve

Do not redesign or discard these merely because the conversational surface changes:

- Central Orchestrator;
- capability/resource registry/catalog;
- identity and authority services;
- execution policy and approval services;
- provider/connector boundaries;
- OpenBao/secrets architecture;
- evidence/provenance/audit systems;
- deterministic collection analysis;
- provider documentation/schema knowledge where useful;
- usage/cost ledger;
- System Registry;
- Teams transport for retained secondary roles;
- OpenClaw components that retain independently justified value.

## Components to stop expanding by default

Until MCP is evaluated, do not add non-critical complexity to components whose main purpose is to recreate normal ChatGPT conversation behavior inside Jason, including:

- custom semantic conversation routers;
- custom investigation decision state machines;
- question-specific routing;
- phrase maps;
- duplicate full conversation memory;
- increasingly elaborate prompt rules compensating for missing native agent behavior;
- duplicate model calls that re-reason a request already reasoned by the ChatGPT session.

Existing production components remain in place until governed replacement/retirement criteria are met.

## Microsoft Teams role

Teams remains a valid and useful secondary interface.

Preferred future roles:

- approvals;
- notifications;
- proactive messages;
- concise operational requests;
- fallback/secondary technician access.

Do not continue treating Teams as the preferred place to recreate a full ChatGPT-quality technician conversational experience.

### Existing Teams production evidence remains valid

The dedicated `jason-teams-gateway` remains the proven ordinary inbound Teams transport owner under ADR-009 until current observed state says otherwise.

Historical/operational references remain:

- `docs/decisions/ADR-009-Direct-Microsoft-Teams-Ingress.md`
- `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`
- `docs/sessions/Teams-Conversation-Working-Baseline-Proof-2026-08-19.md`
- `docs/operations/Runbook-Teams-Integration.md`

The MCP pivot does not erase those records and is not itself evidence that production topology changed.

## OpenClaw role

OpenClaw remains deployed infrastructure at the time of this architecture decision and may still support approved secondary functions.

It is no longer the preferred primary technician conversational brain.

Possible retained roles include:

- proactive/outbound transport;
- secondary interfaces;
- specialist automation/tooling;
- compatibility during migration.

Its final role is intentionally deferred until the MCP pilot demonstrates what remains necessary.

OpenClaw must not bypass Jason identity, authority, policy, approvals, Central Orchestrator, provider governance, secrets, evidence, or audit boundaries.

## Provider/integration direction

New integrations should continue to expand Jason's observable/action world without teaching Jason question-specific workflows.

Preferred integration ingredients:

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

Provider documentation/schema is descriptive knowledge only. It does not automatically grant execution authority for newly documented provider operations.

## MCP tool rules

The future model-facing MCP surface should expose meaningful governed tools derived from Jason capability/resource metadata.

Prefer concepts such as:

- search managed endpoints;
- read endpoint;
- read endpoint audit/inventory;
- search alerts;
- search sites;
- search/read Autotask resources;
- read Microsoft 365 identity/license/sign-in state;
- deterministic analyze/filter/count/group/list over governed evidence.

Do not create tools such as:

- `count_windows_10_devices`;
- `find_user_logged_into_50282`;
- phrase-specific workflow handlers;
- unrestricted HTTP/provider tools;
- direct connector handles.

## Security/authority proving requirements before pilot publication

The MCP path is not production-ready until it proves:

1. supported caller/workspace authentication;
2. Jason principal/organization binding before execution;
3. client/tenant isolation;
4. capability-specific authorization;
5. no credential exposure to ChatGPT;
6. read-only initial surface;
7. policy/approval separation for future actions;
8. bounded structured evidence;
9. provenance/audit for every governed execution;
10. resource/rate limits and abuse controls;
11. rapid disable/revocation/rollback;
12. Central Orchestrator remains sole execution coordinator.

## Consequential actions

Do not expose production write/action tools during the first MCP proving phase.

When actions are added later, ChatGPT may request them but Jason must enforce normal:

- identity-first authorization;
- scope;
- risk classification;
- policy;
- approval;
- preconditions;
- idempotency;
- evidence;
- audit;
- rollback/recovery expectations.

Access to the ChatGPT Business workspace or Jason MCP app alone never grants action authority.

## Current production/runtime caution

This document records the **target direction and current workstream**, not a claim that the MCP service is deployed.

Before asserting current production state, inspect:

- current Git;
- System Registry declared/observed/verified state;
- current host/container/service evidence;
- relevant deployment/verification records.

The current Teams/OpenClaw/Jason environment must remain recoverable during the MCP pilot.

## Known prior conversational lessons that must not be rediscovered

1. Do not solve arbitrary technician questions with phrase-specific code.
2. Do not treat `AOT-50282` or any other proving question as the architecture goal.
3. Provider collection completeness and pagination matter for exact counts/lists.
4. Model-facing excerpts are not substitutes for deterministic complete-data analysis.
5. Meaningful tool descriptions are superior to opaque operation references for model tool selection.
6. Live provider documentation/schema can improve integration knowledge but does not grant authority.
7. Model/tool prompt rules cannot compensate indefinitely for an unsuitable conversational architecture.
8. The Jason reasoning layer should not duplicate work already performed by the technician's ChatGPT session.
9. Governance controls belong in deterministic Jason boundaries, not hidden in conversational prompt behavior.
10. New provider integration should be plumbing/capability registration, not new question logic.

## Governing records for the pivot

- `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`
- `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`
- `docs/roadmaps/ChatGPT-Jason-MCP-Migration-Plan.md`
- `docs/sessions/ChatGPT-Business-MCP-Architecture-Pivot-2026-09-08.md`

## Next safe action

Begin MCP-001 by verifying the current ChatGPT Business custom MCP/app connection and authentication requirements, then design the smallest read-only Jason MCP component that routes exclusively through existing governed capability/Central Orchestrator boundaries.

Do not begin by deleting Teams/OpenClaw or rewriting provider connectors.

## Documentation-complete condition for this pivot

A future competent human or AI session must be able to determine without chat history:

- why the primary conversational architecture changed;
- why ChatGPT Business was chosen;
- what ChatGPT owns versus what Jason owns;
- why the change is constitutionally acceptable;
- how duplicate API/model cost is controlled;
- what roles Teams and OpenClaw retain;
- what existing Jason components remain authoritative;
- what custom conversational components are candidates for later retirement;
- what security/identity requirements block MCP production publication;
- what the exact next implementation sequence is;
- how to preserve the current production path during migration; and
- which records govern the decision, architecture, roadmap, and evidence.
