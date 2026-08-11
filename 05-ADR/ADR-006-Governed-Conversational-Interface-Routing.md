# ADR-006 — Governed Conversational Interface Routing

**Status:** Accepted for implementation  
**Decision owner:** Jason Architecture Authority  
**Date:** 2026-08-10

## Context

Microsoft Teams is now a functioning Jason interface through OpenClaw. A live conversational test exposed an authority/routing gap: when asked who was logged into a managed endpoint, the OpenClaw agent reasoned only from its native paired-node context and suggested `quser`, even though Jason already had governed Datto RMM capabilities and an accepted Datto managed-device authority model.

This behavior is operationally understandable for a standalone OpenClaw assistant but is not acceptable for Jason. The human interface must not become a parallel execution authority or a separate integration brain.

A second design correction was identified immediately afterward: Jason must not solve ordinary information requests by accumulating one-off capabilities or scripts for every fact a human might ask about. When the requested information already exists in a system of record such as Datto RMM, Jason should reason over its registered resources and broad read capabilities to determine how to obtain the information.

For the motivating example, Datto RMM already exposes a native **Last User** device field representing the user that last logged in to the device. Therefore `Who is logged into AOT-50282?` is fundamentally a governed resource-inquiry problem, not a justification for a bespoke `get_logged_in_user` script or direct `quser` execution.

## Decision

All conversational interfaces, including Microsoft Teams through OpenClaw, must enter Jason through a governed conversational ingress boundary and then the Central Orchestrator.

The canonical path is:

`Human -> interface transport -> authenticated identity evidence -> Jason identity/organization binding -> provider-neutral information intent -> governed resource/capability planning -> Central Orchestrator -> Constitution/policy/resolution -> governed capability invocation -> provider-neutral result -> response policy -> interface transport -> Human`

For Teams specifically:

`Teams -> OpenClaw authenticated ingress -> Jason governed conversation flow -> Resource Inquiry Planner -> Central Orchestrator -> Capability Resolution -> governed connector/capability -> result -> OpenClaw Teams transport`

OpenClaw remains transport/interface infrastructure under ADR-005. It does not become the capability authority merely because it hosts the conversation.

## Constitutional rules

1. **Human Governance** — a conversational request is still a governed human request. Interface convenience cannot bypass policy, approval, or authority requirements.
2. **Identity First** — Microsoft tenant/object evidence must be re-bound to a Jason principal and organization before intent resolution can become executable work.
3. **Resource Discovery Before Custom Collection** — when information already exists in a registered authoritative resource, Jason should use that resource before proposing new scripts, components, shell commands, or custom collectors.
4. **Capability Registry Over Hard-Coded Integrations** — conversational intent resolves to broad provider-neutral resource/capability requirements. Teams must not be taught to call Datto RMM, IT Glue, shell commands, or any provider directly.
5. **Reason Over Capabilities, Do Not Multiply Them Per Question** — capabilities should represent reusable system abilities such as querying endpoint records, reading device details, searching tickets, or retrieving documentation. Human questions should be satisfied by planning and composing these abilities rather than creating a new capability for every field.
6. **Central Orchestrator Ownership** — only the Central Orchestrator may resolve and invoke governed capabilities for conversational requests.
7. **No Agent-to-Agent Invocation** — conversational agents may return structured intent or request a named capability. They may not invoke another agent, connector, provider, or agent endpoint directly.
8. **Policy as Data** — risk, data handling, budgets, permitted mode, approval requirements, and invoking roles are supplied through governed request/policy context rather than hidden in prompt behavior.
9. **Evidence Before Assertion** — provider results must pass the governed capability boundary before Jason presents operational facts to the human.
10. **Auditability** — ingress identity, correlation ID, planning decisions, capability selection, policy outcome, provider execution, evidence references, and response delivery must be correlatable.
11. **Fail Closed** — unknown identity, tenant ambiguity, unresolved information intent, unavailable capability, authorization denial, ambiguous resource match, or unsupported provider data must not trigger an ungoverned fallback.

## Resource inquiry model

Natural-language questions should first be represented as provider-neutral information requirements, for example:

```text
resource_type: endpoint
resource_selector:
  hostname: AOT-50282
requested_facts:
  - last logged in user
requested_mode: observe
```

A governed resource-planning layer may inspect registered capability metadata and reason about which reusable read capabilities can retrieve evidence relevant to those facts. The reasoning layer is advisory only: it receives capability descriptions, not credentials or connector handles, and every returned plan step is revalidated against the capability registry before orchestration.

A valid plan for the example may use a broad capability such as `endpoint.device.search` or `endpoint.device.read`, with `requested_facts` carried as context for interpretation. The capability-resolution layer can then select Datto RMM as the approved provider and map that canonical capability to a Datto API read operation.

This is intentionally different from creating `endpoint.session.read` solely because one human happened to ask about a logged-in user.

## Datto RMM example

ADR-004 remains controlling for RMM-managed device existence and operational identity: Datto RMM is the authoritative external provider for that resource domain when selected through governed capability resolution.

For `Who is logged into AOT-50282?`, Jason should attempt to answer from native Datto RMM device data first. Datto RMM documents **Last User** as a device field and supports searching devices by fields including Last User and Hostname. Jason should retrieve the relevant device record through its broad governed Datto read path and reason over the returned data.

If the requested fact is not present in the provider result or cannot be established with acceptable confidence, Jason should state that limitation. It must not silently bypass governance by falling back to `quser`, SSH, arbitrary shell, or OpenClaw node execution.

## Interface boundary contract

The governed conversational flow must:

- require authenticated transport identity evidence;
- bind that evidence to a Jason principal and organization;
- convert human language into provider-neutral information requirements;
- plan only from registered, permitted capabilities;
- build normal `OrchestrationRequest` objects carrying policy/data/budget context;
- verify request construction did not change bound principal, organization, client, capability, or human requester identity;
- call the Central Orchestrator for every executable plan step;
- render only governed orchestration results;
- return the response through the original interface transport;
- preserve correlation across planning, orchestration, provider evidence, and response.

## Explicitly prohibited behavior

- Teams/OpenClaw calling a provider connector directly.
- Teams/OpenClaw choosing a shell command as an ungoverned fallback.
- Creating a new one-off script or capability merely because a new question references a different provider field.
- Prompt-only authorization in place of Jason identity/policy enforcement.
- A conversational agent selecting or invoking another agent directly.
- Provider-specific logic embedded in the Teams transport adapter.
- Treating an OpenClaw paired-node inventory as Jason's complete resource inventory.
- Presenting a provider assertion as canonical Jason truth merely because the provider returned it.
- Giving the resource-planning reasoner credentials, raw connector handles, or authority to execute its own plan.

## Consequences

### Positive

- Teams becomes a real Jason interface rather than a separate assistant silo.
- Jason can answer new questions from existing systems without a corresponding growth of tiny scripts.
- The same conversational request can later arrive from another interface without duplicating provider logic.
- Existing Constitution, capability registry, provider authority, policy, audit, and approval work is reused.
- Provider selection remains replaceable and policy-governed.
- New vendor API fields can become usable through broad existing read capabilities without changing Teams logic.
- The first live failure becomes a deterministic regression case.

### Costs

- Jason needs a governed conversational ingress/composition layer.
- Jason needs a governed resource-inquiry planner that reasons over capability metadata.
- Natural-language understanding must produce structured provider-neutral information requirements.
- Identity binding and response rendering must be explicit runtime dependencies.
- OpenClaw must be configured so Jason owns governed capability routing rather than allowing native agent fallbacks to answer operational questions independently.

## Validation requirements

Implementation must prove at minimum:

- an authenticated, bound Teams request reaches the Central Orchestrator as a human request;
- the conversational layer expresses requested resources/facts without specifying a provider;
- the resource planner only considers registered provider-neutral capabilities;
- planner output is revalidated before execution;
- provider-specific capabilities cannot be smuggled into a resource plan;
- unknown identity fails before orchestration;
- unresolved intent/planning fails before orchestration;
- the request factory cannot alter the bound principal/organization/client or change the requester to an agent;
- direct agent-invocation arguments are rejected;
- denied/unresolved orchestration outcomes can be rendered safely without an ungoverned provider fallback;
- a bounded physical-host Teams test eventually answers an authorized endpoint question through Jason's governed resource path using existing Datto RMM data.

## Relationship to other decisions

- ADR-004: Datto RMM Managed-Device Authority remains controlling for the RMM-managed endpoint domain.
- ADR-005: OpenClaw Teams Transport Boundary remains controlling for Teams transport/ingress.
- Core no-direct-agent rule remains controlling: all inter-agent coordination and capability routing goes through the Central Orchestrator.

## Retirement criteria

Revisit this ADR only if Jason replaces the Central Orchestrator/capability-registry architecture or adopts a different constitutional interface model. Replacing Teams or OpenClaw alone does not retire this decision; the rule applies to all conversational interfaces.
