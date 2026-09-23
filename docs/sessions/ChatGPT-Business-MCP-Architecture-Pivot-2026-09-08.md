# ChatGPT Business + Jason MCP Architecture Pivot — 2026-09-08

**Classification:** Durable session/decision evidence  
**Date:** 2026-09-08  
**Status:** Architecture direction accepted; implementation not yet production-proven

## Context

The Jason conversational workstream had reached a point where significant custom engineering was being spent reproducing normal conversational-agent behavior inside the Teams/Jason runtime path.

Experiments included increasingly capable model-driven read loops, native tool calling, meaningful capability-derived tools, provider documentation knowledge, complete collection reads, and deterministic evidence analysis. These experiments improved individual failure modes but continued to expose a structural problem: Jason was still being asked to reproduce a fluid ChatGPT-like conversation runtime while also carrying its real responsibilities for identity, authority, policy, evidence, and execution.

The project owner requested a full reconsideration of the technician → Jason → OpenClaw/Teams process with one practical requirement: the experience should be as fluid as a normal ChatGPT conversation.

## Alternatives considered

### 1. OpenAI/ChatGPT-first, Jason governance layer

Technician conversation/reasoning occurs in the OpenAI/ChatGPT environment. Jason exposes governed tools/capabilities and retains identity, authority, approvals, audit, provenance, secrets, provider governance, and execution.

### 2. OpenClaw-first agent

OpenClaw owns technician session/agent orchestration and uses Jason as the governed execution/tool service.

### 3. Jason owns the full conversational agent stack

Jason continues building its own conversation state, reasoning loops, semantic routing, and tool orchestration over providers.

## Decision

The project owner selected the **ChatGPT Business + Jason MCP** form of option 1 as the initial architecture to pursue.

The primary reason is that AOT already pays for ChatGPT Business technician seats. Using the technician's existing ChatGPT session as the conversational/reasoning layer should:

- produce the most fluid technician experience;
- reduce custom conversation-engineering burden;
- reduce duplicate OpenAI API reasoning calls;
- preserve Jason's constitutional governance/execution strengths;
- simplify new provider/tool expansion;
- permit Teams and OpenClaw to remain as secondary/optional infrastructure rather than forcing them to carry the entire conversational experience.

## Agreed operating model

```text
Tech's ChatGPT Business session
        ↓
ChatGPT conversation / context / reasoning / tool selection
        ↓
Jason MCP app/service
        ↓
Jason identity / authority / policy / approvals / audit
        ↓
Central Orchestrator
        ↓
Governed capabilities / connectors
        ↓
Providers
```

The key design statement is:

> One AI brain per interaction whenever practical.

For the ChatGPT Business path, ChatGPT is the conversational brain and Jason is the governed operational toolset. Jason should not automatically invoke a second hosted model simply to interpret or synthesize the same request again.

## Constitutional interpretation

The pivot does not delegate Jason authority to ChatGPT.

The accepted boundary is:

- ChatGPT may reason and request tools;
- Jason determines whether the requested capability exists;
- Jason establishes identity and scope;
- Jason enforces authority and policy;
- Jason obtains approvals when required;
- Jason controls provider credentials;
- Central Orchestrator coordinates execution;
- Jason captures evidence/provenance/audit;
- consequential action authority remains human-defined and deterministic.

This aligns with the Constitution's Human Governance, Independence and Capability Abstraction, Integration Before Innovation, Separation of Responsibilities, Simplicity, Modularity/Reversibility, Auditability, and Trust principles.

## Cost conclusion

ChatGPT Business subscription and OpenAI API usage are separate cost domains.

The preferred architecture is designed to maximize the value of the Business subscription by avoiding duplicate Jason-side model calls for ordinary conversation and tool use.

Jason-side model calls remain available where a specific governed capability genuinely benefits from them. The default remains least-cost-first and policy-controlled escalation rather than unconditional model use.

## Teams conclusion

Teams remains valuable for:

- approvals;
- notifications;
- proactive messages;
- concise operational requests;
- secondary/fallback access.

The existing direct Teams gateway work remains valid evidence and should not be destroyed during migration. However, Teams is no longer the preferred target for recreating a full ChatGPT-quality conversational experience.

## OpenClaw conclusion

OpenClaw remains deployed and may retain justified functions, but it is not the preferred primary technician reasoning layer under the new direction.

Its future role will be evaluated after the MCP pilot. It may remain useful for transport, proactive/outbound behavior, compatibility, specialist automation, or it may be reduced/retired if no longer necessary.

## What is retained from prior work

The pivot does not discard the parts of Jason that are central to its purpose:

- Central Orchestrator;
- capability/resource registry and provider-neutral contracts;
- identity/authority;
- execution policy/approvals;
- provider/connector boundaries;
- OpenBao/secrets;
- evidence/provenance/audit;
- deterministic large-collection analysis;
- provider documentation/schema knowledge where useful;
- usage/cost ledger;
- System Registry;
- Teams/OpenClaw components with justified secondary roles.

## What should stop expanding

Until the MCP architecture is evaluated, do not continue adding non-critical complexity to components whose main purpose is to recreate a normal ChatGPT conversational experience inside Jason, including:

- custom semantic routers;
- custom conversational state machines;
- question-specific handlers;
- phrase maps;
- duplicate conversation memory;
- redundant model-to-model handoffs;
- increasingly elaborate prompt rules compensating for missing native conversation behavior.

Existing production components remain until governed replacement/retirement criteria are satisfied.

## Immediate next workstream

The next engineering workstream is **Jason MCP read-only foundation for ChatGPT Business**:

1. verify current ChatGPT Business custom MCP/app requirements and authentication options;
2. define MCP server component and System Registry contract;
3. expose existing read-only governed capabilities through MCP;
4. prove Central Orchestrator remains the sole execution path;
5. prove identity, client isolation, secrets protection, evidence, and audit;
6. publish to a limited AOT ChatGPT Business pilot;
7. measure conversational fluidity, tool reliability, latency, and Jason-side API cost;
8. add a second provider and prove cross-provider reasoning;
9. expand only after the foundation is stable;
10. simplify/retire legacy conversational components only after replacement proof.

## Governing records created with this pivot

- `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`
- `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`
- `docs/roadmaps/ChatGPT-Jason-MCP-Migration-Plan.md`
- `docs/control/CURRENT.md` updated to make this the active resume point.
