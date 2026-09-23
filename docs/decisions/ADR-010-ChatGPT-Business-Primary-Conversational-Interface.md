# ADR-010 — ChatGPT Business as Primary Conversational Interface

**Status:** Accepted architecture direction  
**Date:** 2026-09-08  
**Owner:** Jason Architecture Authority  
**Supersedes:** No existing ADR in full. This decision changes the preferred conversational architecture while retaining prior Teams transport decisions as historical/secondary-channel decisions.

## Decision

Jason will adopt **ChatGPT Business as the preferred primary technician conversational interface**, with Jason exposed to ChatGPT as a governed MCP/tool service.

The preferred interaction model is:

```text
Technician
    ↓
ChatGPT Business session
    ↓
ChatGPT reasoning / conversation / session context
    ↓
Jason governed MCP/tool boundary
    ↓
Jason identity + authority + policy + approvals + audit
    ↓
Central Orchestrator
    ↓
Governed capabilities / connectors
    ↓
Datto RMM / Autotask / Microsoft 365 / IT Glue / other providers
```

The ChatGPT session is the conversational and reasoning surface. Jason remains the governing and execution authority for Jason capabilities.

Jason must not duplicate the ChatGPT conversation/reasoning layer unless a channel or workload genuinely requires a separate model invocation.

## Why this decision was made

The current Teams-centered conversational architecture has required Jason to reproduce behaviors already provided effectively by a mature conversational model runtime: natural multi-turn dialogue, context continuity, tool selection, follow-up reasoning, iterative investigation, and answer synthesis.

That duplication has increased implementation complexity, debugging cost, maintenance burden, and API cost while still producing a less-fluid technician experience than a normal ChatGPT session.

The preferred architecture instead uses the technician's existing ChatGPT Business session for the conversational intelligence already included in that product experience, while preserving Jason's constitutional strengths as the governed operational platform.

The goal is not to make ChatGPT authoritative. The goal is to stop rebuilding ChatGPT inside Jason.

## Constitutional alignment

This decision is intended to strengthen, not weaken, Jason's Constitution.

### Human Governance

Human and organizational authority remain outside the model. ChatGPT may interpret, reason, ask questions, recommend, and request tools. It does not gain business authority merely because it can request a tool.

### Independence and Capability Abstraction

ChatGPT is an interface/reasoning dependency, not the definition of Jason capabilities. Jason capabilities remain provider-neutral and replaceable. The MCP exposure is an adapter to governed capabilities, not a rewrite of those capabilities around ChatGPT terminology.

### Integration Before Innovation

This decision intentionally prefers an existing mature conversational platform over continuing to build a custom conversational agent runtime where the external platform already provides the required capability.

### Separation of Responsibilities

The primary separation becomes:

- **ChatGPT Business:** conversation, natural-language reasoning, session context, tool selection, synthesis;
- **Jason:** identity binding, authorization, scope, policy, approvals, evidence, provenance, audit, rate/cost controls, deterministic analysis, capability exposure, execution coordination;
- **Central Orchestrator:** sole governed execution coordinator;
- **Connectors/providers:** bounded external-system execution only.

### Simplicity

Custom semantic routers, bespoke conversational state machines, question-specific handlers, and Jason-hosted reasoning loops are not preferred architecture when the ChatGPT session can perform that reasoning directly.

### Modularity and Reversibility

ChatGPT Business is the preferred initial conversational surface, not an inseparable Jason dependency. Teams, web, SSH, OpenClaw, or future interfaces may remain or be added as secondary interfaces provided they preserve the same governed Jason capability boundary.

## Authority boundary

ChatGPT receives only the tools Jason intentionally exposes.

A ChatGPT tool request is a **request for governed execution**, not execution authority.

Jason remains responsible for, as applicable:

1. authenticated identity binding;
2. tenant/organization/client scope;
3. capability authorization;
4. risk classification;
5. policy enforcement;
6. approval requirements;
7. read-versus-action authority;
8. idempotency and preconditions;
9. rate/resource limits;
10. provider credential isolation;
11. Central Orchestrator routing;
12. evidence/provenance capture;
13. audit logging;
14. deterministic validation and aggregation where appropriate;
15. fail-closed behavior.

The model must never receive provider credentials merely to enable tool use.

## MCP/tool design rules

Jason's MCP surface must expose meaningful reusable operational tools derived from governed capabilities/resources.

The MCP surface must not become a parallel workflow engine.

Required rules:

- expose capabilities/resources, not question-specific handlers;
- use human/model-meaningful tool names and descriptions;
- keep provider-specific API details behind Jason's connector/provider boundary unless descriptive schema knowledge is intentionally exposed;
- do not expose opaque internal operation identifiers as the primary model-facing vocabulary;
- do not expose provider credentials;
- do not allow direct unrestricted HTTP/provider access;
- keep write/action capabilities separately governed from read capabilities;
- return structured evidence suitable for ChatGPT reasoning;
- use deterministic Jason-side operations for large collection pagination, counting, filtering, grouping, joins, and other mechanical work where sending large raw datasets to the model is unnecessary;
- preserve provenance/source attribution in tool results;
- fail closed when identity, authority, scope, policy, approval, capability resolution, or evidence requirements are not satisfied.

## Cost policy

The architecture will maximize value from existing ChatGPT Business technician sessions.

Default policy:

1. **Do not invoke a second Jason-side OpenAI model merely to restate or re-reason the same technician request.**
2. Let the ChatGPT Business session perform normal conversation, context handling, reasoning, tool selection, comparison, and synthesis.
3. Perform deterministic computation inside Jason where practical.
4. Cache stable provider documentation/schema/reference material where policy permits.
5. Use additional Jason-side hosted-model calls only when a governed capability explicitly requires one and the value justifies the cost.
6. When a Jason-side model call is required, use the least-cost model that satisfies the workload and allow policy-controlled escalation only when necessary.
7. Maintain usage/cost telemetry attributable to capability, model, technician/session where available, client scope where appropriate, and task class.
8. Support soft/hard budget controls without allowing cost controls to silently bypass constitutional safety/authority requirements.

ChatGPT Business subscription usage and OpenAI API usage remain separate cost domains. This architecture is designed to minimize duplicate API reasoning by treating the technician's ChatGPT session as the primary conversational brain.

## OpenClaw role

OpenClaw is no longer the preferred primary reasoning/orchestration layer for technician conversation under this decision.

It may remain deployed and may continue to provide useful bounded functions such as:

- secondary transport/interface capabilities;
- approved proactive/outbound workflows;
- operational tooling where independently justified;
- compatibility paths during migration.

OpenClaw must not become a bypass around Jason identity, authority, policy, approvals, Central Orchestrator execution, secrets, evidence, or audit boundaries.

OpenClaw may be reduced, repurposed, or retired later based on demonstrated need. This ADR does not require immediate removal.

## Microsoft Teams role

Teams remains a valid secondary interface and a useful communication/approval channel.

The existing direct Teams ingress work is not erased by this decision. Its evidence and security conclusions remain historically valid for that channel.

However, Teams is no longer the preferred place to recreate the full ChatGPT-quality technician conversational experience.

Future Teams behavior should favor one of these bounded roles:

- notifications;
- approvals;
- concise operational requests;
- secondary access when ChatGPT is unavailable or inappropriate;
- links/handoffs into the primary ChatGPT/Jason experience where useful.

A future decision may expand Teams again if a supported architecture can provide equivalent fluidity without reintroducing a large custom conversational stack.

## Conversation/session strategy

For the primary path, the ChatGPT Business session owns normal conversational continuity.

Jason should persist only the state Jason itself must own, such as:

- identity and authority state;
- approval/action state;
- execution correlation;
- durable resource identities when constitutionally appropriate;
- evidence/provenance/audit records;
- bounded operational continuation state that must outlive one ChatGPT tool invocation;
- policy-required memory.

Jason should not maintain a duplicate full conversational transcript/state machine merely to mirror what the ChatGPT session already knows.

## Security and privacy boundaries

Before production publication of the Jason MCP app:

- authenticate the caller/workspace identity using a supported mechanism;
- bind that identity to Jason's principal/organization model before execution;
- prove client/tenant isolation;
- expose only approved tools;
- separate read authority from consequential actions;
- preserve approval requirements for consequential actions;
- sanitize/redact model-facing evidence;
- maintain audit/provenance records for tool execution;
- verify no secrets are returned in tool schemas/results;
- define rate/resource limits and abuse handling;
- define disable/revocation/rollback controls for the MCP app.

## Migration strategy

Migration is incremental and reversible.

### Phase 0 — Freeze and preserve

- preserve current Teams/OpenClaw/Jason evidence and rollback paths;
- stop expanding custom conversational state-machine complexity except for critical fixes;
- retain existing governed connector/capability work that remains useful behind MCP.

### Phase 1 — MCP read-only foundation

- expose a minimal read-only Jason MCP service;
- authenticate ChatGPT Business users to Jason;
- publish only low-risk governed read capabilities;
- prove one-provider and cross-provider reads;
- prove provenance, audit, client isolation, and fail-closed behavior.

### Phase 2 — Technician pilot

- publish the Jason MCP app to an approved technician pilot group/workspace scope;
- validate fluid multi-turn questions in ordinary ChatGPT sessions;
- validate follow-up references and cross-tool reasoning;
- measure response quality, latency, duplicate API spend, and tool-selection reliability;
- compare the experience directly against the Teams/Jason conversational path.

### Phase 3 — Tool-surface expansion

- add Autotask, Microsoft 365, IT Glue, Datto RMM, and other governed resources incrementally;
- expose deterministic collection analysis and cross-provider evidence operations;
- keep integration registration capability/resource driven.

### Phase 4 — Governed actions

- add consequential tools only after read-only production behavior is stable;
- require identity-first authorization, risk/policy controls, approval where applicable, idempotency, preconditions, evidence, and audit;
- never infer action authority from ChatGPT access alone.

### Phase 5 — Simplification/retirement

- identify custom conversation/router/investigation components no longer required;
- retire or bypass them through explicit lifecycle decisions and tests;
- reduce OpenClaw/Teams conversational responsibilities to justified roles;
- update System Registry and operational documentation to match actual production topology.

## Components expected to remain valuable

This decision explicitly preserves the value of:

- Central Orchestrator;
- capability/resource registry/catalog;
- identity and authority services;
- execution policy and approvals;
- provider/connector boundaries;
- OpenBao/secrets architecture;
- evidence/provenance/audit systems;
- deterministic collection analysis;
- provider documentation/schema knowledge mechanisms where useful;
- usage/cost ledger;
- System Registry;
- Teams transport for its retained roles.

## Components to reconsider

The following are candidates for bypass, simplification, or retirement once MCP proves equivalent/better operation:

- custom semantic conversational routers;
- custom investigation decision state machines;
- Jason-hosted conversation loops whose primary purpose is to imitate ordinary ChatGPT interaction;
- question-specific routing/phrase maps;
- duplicate conversation-memory systems not required for governance or durable operations;
- redundant model calls that re-reason a request already reasoned by the ChatGPT session.

No component is deleted merely because this ADR exists. Retirement requires impact review, tests, current-state verification, and rollback planning.

## Alternatives considered

### OpenClaw-first primary agent

Pros: less custom agent-loop code and reuse of OpenClaw session/tool orchestration.

Cons: adds a separate agent runtime between the technician and Jason; conversational quality and behavior depend on OpenClaw; debugging and governance boundaries span more layers; still risks paying for a separate model path when technicians already have ChatGPT Business.

Decision: retain OpenClaw as optional/secondary infrastructure, not primary technician conversational brain.

### Jason-owned conversational engine

Pros: maximum implementation control.

Cons: highest engineering burden; duplicates mature conversational/agent capabilities; has already produced significant complexity and friction; increases maintenance and duplicate model cost.

Decision: do not continue as preferred architecture.

### Teams as primary conversational surface

Pros: convenient inside the technician's existing work communication tool and useful for approvals/notifications.

Cons: requires Jason to supply the conversational AI runtime itself to approach ChatGPT quality; increases API and engineering cost.

Decision: keep Teams as secondary channel rather than primary full conversational environment.

## Acceptance criteria

This decision is considered successfully implemented only when:

- a technician can use Jason from ChatGPT Business through a workspace-approved MCP/app connection;
- Jason proves authenticated identity binding before governed execution;
- the technician can perform natural follow-up and cross-provider questions without Jason question-specific handlers;
- read-only tools operate through Central Orchestrator/provider governance;
- provider credentials remain hidden;
- provenance/audit evidence is retained;
- large collection analysis does not require dumping unbounded provider payloads into ChatGPT;
- constitutional action/approval controls remain enforceable;
- duplicate Jason-side OpenAI API reasoning is absent by default and measurable when intentionally used;
- Teams/OpenClaw rollback/secondary roles remain documented during migration;
- System Registry reflects the actually deployed MCP service before it is called operational.

## Consequences

### Positive

- closest path to the fluidity of a normal ChatGPT conversation;
- maximizes value of existing ChatGPT Business seats;
- potentially substantial reduction in duplicate API/model spend;
- less custom conversational code;
- simpler provider expansion model;
- clearer constitutional separation between intelligence and authority;
- improved replaceability of front-end/transport layers.

### Negative / risks

- increased reliance on ChatGPT Business and MCP/app platform behavior for the preferred interface;
- Jason must implement and operate a high-quality, secure MCP boundary;
- Business workspace controls may be less granular than some Enterprise controls and must be validated during pilot design;
- secondary channels still require separate interaction design;
- migration creates a period where old and new conversational paths coexist;
- tool schema quality becomes important because ChatGPT reasoning quality depends on what Jason exposes;
- API/platform changes in ChatGPT/MCP require stewardship monitoring.

## Revisit triggers

Revisit this ADR if:

- ChatGPT Business cannot provide the required MCP/app capability or identity controls;
- workspace governance proves insufficient for AOT's risk model;
- measured user experience is materially worse than the current/alternative channel;
- cost exceeds the Teams/OpenAI architecture after realistic pilot measurement;
- a future OpenAI/OpenClaw/Teams capability provides a simpler equivalent architecture;
- constitutional boundaries cannot be enforced reliably through the MCP path.
