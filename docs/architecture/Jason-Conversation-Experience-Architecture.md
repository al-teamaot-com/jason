# Jason Conversation Experience Architecture

## Status

Approved architectural direction for implementation. Microsoft Teams is the first and primary human interface, but the design is interface- and model-independent.

## Purpose

Jason must feel like one capable, context-aware AOT teammate regardless of which reasoning model, provider, connector, or internal capability satisfies a request. Cost optimization, retries, model escalation, provider discovery, evidence acquisition, and implementation details are backend concerns. They must not leak into or reduce the quality of the human conversation.

## Minimal topology

The conversational topology is deliberately small:

```text
Teams
  -> Conversation Kernel
  -> Central Orchestrator
  -> Conversation Kernel
  -> Teams
```

Verified conversation state and audit evidence are Jason-owned cross-cutting state. Identity, policy, approvals, evidence controls, System Registry truth, and provider resolution remain governed controls, not additional conversational authorities.

Architectural separation is separation of authority and responsibility, not an excuse to create unnecessary services or agents.

## Responsibility boundaries

### Teams interface adapter

Teams is a transport and presentation boundary. It may:

- receive authenticated conversation input;
- preserve conversation/message identity;
- show appropriate activity/progress state;
- present normal messages or governed approval cards;
- deliver the final Jason response.

Teams must not own semantic interpretation, provider routing, capability selection, authorization decisions, or factual response generation.

### Conversation Kernel

The Conversation Kernel owns the human interaction. It may:

- maintain and consume bounded, verified conversation context;
- interpret the target and information/outcome the human actually needs;
- resolve references to already verified entities;
- ask clarification only for material ambiguity;
- represent one turn as conversation, clarification, or provider-independent information needs;
- use one or more replaceable reasoning backends;
- retry or escalate model reasoning behind the same contract;
- synthesize natural responses from validated evidence;
- enforce the Conversation Experience Contract before a response is released.

The Conversation Kernel must not select or expose providers, connectors, API paths, shell commands, target agents, or low-level capability implementation details as part of human intent interpretation.

### Central Orchestrator

The Central Orchestrator remains Jason's sole execution and coordination authority. It is responsible for:

- identity-first authorization and tenant/client scope;
- policy and governance gates;
- capability/resource discovery;
- provider resolution;
- minimum-sufficient evidence acquisition;
- action approvals and execution;
- retries, timeouts, escalation, and failure handling;
- audit/event evidence;
- final governed execution results.

Agents and connectors never coordinate directly. They return structured results or expose named capabilities to the Central Orchestrator.

## Information-need contract

The Conversation Kernel describes **what** the human needs, not **how** to obtain it.

A provider-independent information need contains, at minimum:

- target kind;
- target reference grounded in the current message or verified conversation entity;
- requested information or outcome in natural language;
- requested authority;
- temporal scope;
- completeness requirement;
- material relationship when applicable.

It does not contain provider IDs, connector IDs, capability IDs, API operations, provider fields, scripts, or agents.

## Progressive fulfillment

Jason must prefer progressive evidence acquisition over speculative source fan-out.

For a read request:

1. start with the registered primary resource access that structurally matches the target;
2. obtain governed evidence through the Central Orchestrator;
3. evaluate whether the information need is supported;
4. only if a genuine evidence gap remains, discover and invoke the minimum additional specialized governed resource required;
5. stop when the requested bounded answer is sufficiently supported.

This prevents a language model from guessing several internal sources up front and keeps provider/resource discovery behind the orchestration boundary.

## Model independence and cost

The Conversation Kernel uses a common structured reasoning interface. Models are replaceable implementation details.

Backend policy should optimize in this order:

1. safety and authority;
2. factual accuracy;
3. answer completeness;
4. conversational quality;
5. cost;
6. latency.

Lower-cost/local reasoning should be attempted first when appropriate. Jason may retry, repair, or escalate to a stronger approved backend when bounded validation or quality checks fail. The user should not see which backend was used or how many attempts occurred unless operational diagnostics are explicitly requested.

A slower correct response is acceptable when it materially reduces cost without creating an unreasonable user experience.

## Conversation Experience Contract

Every human-facing Teams response must satisfy these invariants:

- answer the human's actual request rather than narrating Jason's internal workflow;
- give useful information first;
- maintain natural verified conversation references such as "it", "he", "that ticket", and "those alerts";
- do not ask the human to choose an internal provider, registry, evidence source, capability, or API;
- clarify only when choosing would materially change target, authority, action, risk, or meaning;
- do not expose raw model output, JSON/schema failures, connector exceptions, or orchestration internals;
- distinguish naturally among unavailable evidence, inaccessible authority, temporary service failure, and approval requirements;
- keep provider provenance internally and present it when useful or requested rather than appending it mechanically to every response;
- never make a factual assertion without governed supporting evidence;
- never allow a model-generated action to bypass Central Orchestrator validation and approval.

No raw model output is a human-facing response. Model output is always a proposal subject to Jason validation and experience controls.

## Failure-class engineering rule

An observed failure is evidence of a failure class, not a specification for a patch.

Before implementing a corrective change, engineering must identify:

1. the observed symptom;
2. the general failure class;
3. the violated architectural invariant;
4. the generalized correction at the proper abstraction level;
5. unrelated regression cases proving the triggering example was not special-cased.

The triggering example may be retained as a regression fixture but must never become the production design target.

## Acceptance strategy

Conversation acceptance must evaluate classes of behavior across unrelated domains, including:

- explicit resource inquiries;
- follow-up pronouns and verified context;
- person-to-device and device-to-person pivots;
- cross-provider information needs;
- multi-fact questions;
- legitimate ambiguity;
- unavailable evidence;
- permission denial;
- approval-required actions;
- provider outage;
- model timeout or malformed structured output;
- rejected unsupported model claims;
- runtime restart and context restoration;
- duplicate Teams delivery;
- concurrent conversation turns;
- long-running governed work;
- provenance/explanation questions;
- cancellation or change of intent.

The same Conversation Experience Contract applies regardless of which approved reasoning backend is active.

## Migration direction

Existing dynamic conversation work that is already provider-independent, bounded, auditable, and useful should be reused, especially verified conversation state, identity binding, Central Orchestrator execution, evidence sanitization, capability registry truth, provider resolution, and transport security.

The current pattern in which the conversational model directly chooses low-level capabilities is transitional and should not be expanded. New implementation should move intent interpretation upward to provider-independent information needs and move resource/capability selection downward behind the Central Orchestrator boundary.
