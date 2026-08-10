# ADR-006 — Governed Conversational Interface Routing

**Status:** Accepted for implementation  
**Decision owner:** Jason Architecture Authority  
**Date:** 2026-08-10

## Context

Microsoft Teams is now a functioning Jason interface through OpenClaw. A live conversational test exposed an authority/routing gap: when asked who was logged into a managed endpoint, the OpenClaw agent reasoned only from its native paired-node context and suggested `quser`, even though Jason already had governed Datto RMM capabilities and an accepted Datto managed-device authority model.

This behavior is operationally understandable for a standalone OpenClaw assistant but is not acceptable for Jason. The human interface must not become a parallel execution authority or a separate integration brain.

## Decision

All conversational interfaces, including Microsoft Teams through OpenClaw, must enter Jason through a governed conversational ingress boundary and then the Central Orchestrator.

The canonical path is:

`Human -> interface transport -> authenticated identity evidence -> Jason identity/organization binding -> provider-neutral intent -> named capability -> Central Orchestrator -> Constitution/policy/resolution -> governed capability invocation -> provider-neutral result -> response policy -> interface transport -> Human`

For Teams specifically:

`Teams -> OpenClaw authenticated ingress -> Jason governed conversation flow -> Central Orchestrator -> Capability Resolution -> governed connector/capability -> result -> OpenClaw Teams transport`

OpenClaw remains transport/interface infrastructure under ADR-005. It does not become the capability authority merely because it hosts the conversation.

## Constitutional rules

1. **Human Governance** — a conversational request is still a governed human request. Interface convenience cannot bypass policy, approval, or authority requirements.
2. **Identity First** — Microsoft tenant/object evidence must be re-bound to a Jason principal and organization before intent resolution can become executable work.
3. **Capability Registry Over Hard-Coded Integrations** — conversational intent resolves to a provider-neutral named capability. Teams must not be taught to call Datto RMM, IT Glue, shell commands, or any provider directly.
4. **Central Orchestrator Ownership** — only the Central Orchestrator may resolve and invoke governed capabilities for conversational requests.
5. **No Agent-to-Agent Invocation** — conversational agents may return structured intent or request a named capability. They may not invoke another agent, connector, provider, or agent endpoint directly.
6. **Policy as Data** — risk, data handling, budgets, permitted mode, approval requirements, and invoking roles are supplied through governed request/policy context rather than hidden in prompt behavior.
7. **Evidence Before Assertion** — provider results must pass the governed capability boundary before Jason presents operational facts to the human.
8. **Auditability** — ingress identity, correlation ID, capability selection, policy outcome, provider execution, evidence references, and response delivery must be correlatable.
9. **Fail Closed** — unknown identity, tenant ambiguity, unresolved capability intent, unavailable capability, authorization denial, ambiguous resource match, or unsupported provider data must not trigger an ungoverned fallback.

## First bounded implementation slice

The first acceptance slice is a read-only endpoint-session/state question equivalent to:

`Who is logged into AOT-50282?`

The conversational layer should resolve a provider-neutral capability such as `endpoint.session.read`. The capability registry/resolution engine, not Teams, determines whether an approved provider can satisfy that capability.

ADR-004 remains controlling for RMM-managed device existence and operational identity: Datto RMM is the authoritative external provider for that resource domain when selected through governed capability resolution.

If current logged-on-session information is not available through the registered Datto capability, Jason must say that the requested fact is unavailable through the currently authorized capabilities. It must not silently bypass governance by falling back to `quser`, SSH, arbitrary shell, or OpenClaw node execution.

## Interface boundary contract

The governed conversational flow must:

- require authenticated transport identity evidence;
- bind that evidence to a Jason principal and organization;
- resolve human language into a provider-neutral named capability and structured arguments;
- build a normal `OrchestrationRequest` carrying policy/data/budget context;
- verify the request factory did not change bound principal, organization, client, capability, or human requester identity;
- call the Central Orchestrator exactly once;
- render only the governed orchestration result;
- return the response through the original interface transport;
- preserve one correlation ID across the orchestration and response path.

## Explicitly prohibited behavior

- Teams/OpenClaw calling a provider connector directly.
- Teams/OpenClaw choosing a shell command as an ungoverned fallback.
- Prompt-only authorization in place of Jason identity/policy enforcement.
- A conversational agent selecting or invoking another agent directly.
- Provider-specific logic embedded in the Teams transport adapter.
- Treating an OpenClaw paired-node inventory as Jason's complete resource inventory.
- Presenting a provider assertion as canonical Jason truth merely because the provider returned it.

## Consequences

### Positive

- Teams becomes a real Jason interface rather than a separate assistant silo.
- The same conversational request can later arrive from another interface without duplicating provider logic.
- Existing Constitution, capability registry, provider authority, policy, audit, and approval work is reused.
- Provider selection remains replaceable and policy-governed.
- The first live failure becomes a deterministic regression case.

### Costs

- Jason needs a governed conversational ingress/composition layer.
- Natural-language intent resolution must produce structured provider-neutral capability requests.
- Identity binding and response rendering must be explicit runtime dependencies.
- OpenClaw must be configured so Jason owns governed capability routing rather than allowing native agent fallbacks to answer operational questions independently.

## Validation requirements

Implementation must prove at minimum:

- an authenticated, bound Teams request reaches the Central Orchestrator as a human request;
- the conversational layer requests a named capability and does not specify a provider;
- unknown identity fails before orchestration;
- unresolved intent fails before orchestration;
- the request factory cannot alter the bound principal/organization/client or change the requester to an agent;
- direct agent-invocation arguments are rejected;
- denied/unresolved orchestration outcomes can be rendered safely without an ungoverned provider fallback;
- a bounded physical-host Teams test eventually answers an authorized endpoint question through Jason's governed resource path.

## Relationship to other decisions

- ADR-004: Datto RMM Managed-Device Authority remains controlling for the RMM-managed endpoint domain.
- ADR-005: OpenClaw Teams Transport Boundary remains controlling for Teams transport/ingress.
- Core no-direct-agent rule remains controlling: all inter-agent coordination and capability routing goes through the Central Orchestrator.

## Retirement criteria

Revisit this ADR only if Jason replaces the Central Orchestrator/capability-registry architecture or adopts a different constitutional interface model. Replacing Teams or OpenClaw alone does not retire this decision; the rule applies to all conversational interfaces.
