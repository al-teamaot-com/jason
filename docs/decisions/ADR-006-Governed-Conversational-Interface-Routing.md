# ADR-006 — Governed Conversational Interface Routing

**Status:** Accepted and active  
**Decision owner:** Jason Architecture Authority  
**Date:** 2026-08-10  
**Updated:** 2026-08-15

## Context

Microsoft Teams exposed an authority/routing gap during early live use: a question about a managed endpoint was answered from interface-local/OpenClaw context even though Jason already had governed Datto RMM capabilities and an accepted managed-device authority model.

That failure established a provider-neutral rule that remains independent of the transport implementation: a human interface must not become a parallel execution authority or a separate integration brain.

A second correction followed immediately. Jason must not solve ordinary information requests by accumulating one-off capabilities or scripts for every fact a human might ask about. When the information already exists in an authoritative registered resource such as Datto RMM, Jason should reason over registered capabilities/resources and obtain the evidence through the Central Orchestrator.

For example, Datto RMM exposes a native **Last User** device field. `Who is logged into AOT-50282?` is therefore a governed resource inquiry, not justification for a bespoke `get_logged_in_user` script or direct `quser` execution.

## Decision

All conversational interfaces must enter Jason through a governed ingress boundary and then the Central Orchestrator.

The canonical provider-neutral path is:

`Human -> interface transport -> authenticated identity evidence -> Jason identity/organization binding -> provider-neutral information/action intent -> governed resource/capability planning -> Central Orchestrator -> Constitution/policy/resolution -> governed capability invocation -> provider evidence -> deterministic response policy -> interface transport -> Human`

For ordinary Microsoft Teams conversations after the 2026-08-15 cutover:

`Teams -> direct Jason Teams Gateway -> signed trusted ingress -> Jason governed conversation flow -> Resource Inquiry Planner -> Central Orchestrator -> Capability Resolution -> governed connector/capability -> evidence/result -> direct Teams response`

ADR-009 controls the current inbound Teams transport. Replacing Teams/OpenClaw/direct-gateway implementation details does not retire this ADR; the governed routing rule applies to every conversational interface.

## Constitutional rules

1. **Human Governance** — a conversational request is a governed human request. Interface convenience cannot bypass policy, approval, or authority.
2. **Identity First** — authenticated transport identity must be re-bound to a Jason principal and organization before intent becomes executable work.
3. **Resource Discovery Before Custom Collection** — use registered authoritative resources before proposing new scripts, shell commands, components, or collectors.
4. **Capability Registry Over Hard-Coded Integrations** — conversational intent resolves to broad provider-neutral capability/resource requirements. The interface must not be taught to call Datto RMM, IT Glue, a shell, or any provider directly.
5. **Reason Over Capabilities, Do Not Multiply Them Per Question** — capabilities represent reusable system abilities, not one-off questions or fields.
6. **Central Orchestrator Ownership** — only the Central Orchestrator may resolve and invoke governed capabilities for conversational requests.
7. **No Agent-to-Agent Invocation** — agents may return structured intent or request a named capability; they may not invoke another agent, connector, provider, or agent endpoint directly.
8. **Policy as Data** — risk, data handling, budgets, permitted mode, approval requirements, and invoking roles are explicit governed request/policy context.
9. **Evidence Before Assertion** — provider results must pass the governed capability boundary before Jason presents operational facts.
10. **Auditability** — identity, correlation, planning, capability selection, policy outcome, provider execution, evidence, and response delivery must be correlatable.
11. **Fail Closed** — unknown identity, tenant ambiguity, unresolved intent, unavailable capability, authorization denial, ambiguous resource match, or unsupported evidence must not trigger an ungoverned fallback.

## Resource inquiry model

Natural-language questions are first represented as provider-neutral information requirements, for example:

```text
resource_type: endpoint
resource_selector:
  hostname: AOT-50282
requested_facts:
  - last logged in user
requested_mode: observe
```

A governed resource-planning layer may inspect registered capability metadata and reason about which reusable read capabilities can retrieve evidence relevant to those facts. The reasoning layer is advisory only: it receives bounded capability descriptions, not credentials or connector handles, and every returned plan step is revalidated against the capability registry before orchestration.

A valid plan may use broad capabilities such as `endpoint.device.search` or `endpoint.device.read`. Capability resolution then selects an approved provider such as Datto RMM and maps the canonical capability to a provider operation.

This is intentionally different from creating a new capability solely because one human asked about a different device field.

## Canonical-fact qualification and ambiguity

When multiple eligible canonical facts share a generic human anchor but differ by qualifiers, Jason must not allow a generic model or longest-alias heuristic to silently choose between them.

The deterministic qualification sequence is:

1. derive eligible canonical facts from governed read capability metadata;
2. identify recognition language shared by multiple eligible facts;
3. require that shared anchor in the human request;
4. identify candidate-specific discriminating language;
5. resolve only when exactly one candidate is discriminated;
6. classify a shared anchor without a unique discriminator as ambiguous;
7. classify conflicting discriminators as ambiguous; and
8. stop ambiguity before generic language reasoning, capability planning, or orchestration.

The result is tri-state: `not_applicable`, `resolved`, or `ambiguous`.

Current examples:

- internal/private/local IP -> `LAN IP address`;
- public/external/internet-facing IP -> `WAN IP address`;
- bare IP -> ambiguous;
- conflicting internal/public qualifiers -> ambiguous.

Qualification selects only a governed canonical fact. It does not select a provider, provider field, connector, authorization result, evidence pointer, or operational value.

Ambiguity returns a bounded stateless `clarification_required` result when Jason can identify active competing governed canonical facts. The result is non-executable and stops before request construction, Central Orchestrator execution, provider access, or model guessing. A complete follow-up request remains required until a separately governed continuation mechanism exists.

Historical proofs:

- `docs/sessions/Teams-Canonical-Fact-Qualifier-Proof-2026-08-14.md`;
- `docs/sessions/Teams-Governed-Ambiguity-Clarification-Proof-2026-08-14.md`.

## Datto RMM example

ADR-004 remains controlling for RMM-managed device existence and operational identity when Datto RMM is selected through governed capability resolution.

For `Who is logged into AOT-50282?`, Jason should attempt to answer from native Datto RMM device data first. If the requested fact is not present or cannot be established with acceptable evidence, Jason should state the limitation. It must not silently fall back to `quser`, SSH, arbitrary shell, or interface-local node execution.

The 2026-08-15 direct Teams gateway production proof confirmed this pattern end to end: a Teams request for the last user and current problems on `AOT-50282` returned Datto-backed evidence through the direct gateway and Jason runtime without an OpenClaw model trajectory.

Proof: `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`.

## Interface boundary contract

A governed conversational flow must:

- require authenticated transport identity evidence;
- bind that evidence to a Jason principal and organization;
- convert human language into provider-neutral information/action requirements;
- plan only from registered, permitted capabilities;
- build normal governed orchestration requests carrying policy/data/budget context;
- verify request construction did not change the bound principal, organization, client, capability, or human requester identity;
- call the Central Orchestrator for every executable plan step;
- render only governed orchestration/evidence results;
- return the response through the original interface transport; and
- preserve correlation across ingress, planning, orchestration, provider evidence, and response.

## Explicitly prohibited behavior

- Interface transport calling a provider connector directly.
- Interface transport choosing a shell command as an ungoverned fallback.
- Creating a one-off script/capability merely because a new question references a different provider field.
- Prompt-only authorization in place of Jason identity/policy enforcement.
- A conversational agent selecting or invoking another agent directly.
- Provider-specific logic embedded in the Teams transport adapter.
- Treating any interface-local inventory as Jason's complete resource inventory.
- Presenting a provider assertion as canonical Jason truth merely because the provider returned it.
- Giving a planning reasoner credentials, raw connector handles, or authority to execute its own plan.
- Allowing an interface model to answer operational questions independently when the turn is Jason-owned.

## Validation requirements

Implementation must prove at minimum:

- an authenticated, bound conversational request reaches the Central Orchestrator as a human request;
- requested resources/facts are expressed without preselecting a provider;
- resource planning considers only registered provider-neutral capabilities;
- planner output is revalidated before execution;
- provider-specific capabilities cannot be smuggled into a plan;
- unknown identity fails before orchestration;
- unresolved intent/planning fails before orchestration;
- ambiguous canonical facts stop before generic model reasoning/orchestration;
- qualified facts resolve only from governed eligible canonical facts;
- qualifier resolution does not select provider fields or operational values;
- request construction cannot alter bound identity/organization/client authority;
- direct agent-invocation arguments are rejected;
- denied/unresolved outcomes render safely without an ungoverned provider fallback; and
- a physical-host interface test can answer an authorized endpoint question through governed Datto RMM evidence.

## Relationship to other decisions

- ADR-004 — Datto RMM Managed-Device Authority controls the managed endpoint domain.
- ADR-005 — OpenClaw Teams Transport Boundary remains relevant to approved outbound/proactive Teams transport, not ordinary inbound Teams ingress.
- ADR-007 — Teams proactive messaging and exact-message/processing-feedback requirements remain relevant; transport-specific inbound implementation is superseded by ADR-009.
- ADR-009 — Direct Microsoft Teams Ingress Gateway controls the current ordinary inbound Teams transport and exclusive-ownership boundary.
- Core no-direct-agent rule remains controlling: all inter-agent coordination and capability routing goes through the Central Orchestrator.

## Retirement criteria

Revisit this ADR only if Jason replaces the Central Orchestrator/capability-registry architecture or adopts a different constitutional interface model. Replacing Teams, OpenClaw, or the direct gateway alone does not retire the provider-neutral governed conversational-routing decision.
