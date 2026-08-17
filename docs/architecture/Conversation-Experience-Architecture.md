# Jason Conversation Experience Architecture

## Status

Constitutional architecture requirement for human-facing conversational interfaces. Microsoft Teams is the initial and primary operational interface, but the contract is interface-independent and applies to future web, mobile, voice, meeting, and other conversational surfaces.

## Purpose

Jason must feel like one capable, governed AOT colleague rather than a collection of provider bots, hard-coded workflows, or model-specific behaviors. The quality of the human experience must not depend on which lower-cost reasoning model, provider connector, or execution resource happens to perform backend work.

## Constitutional requirements

### Interface Quality Independence

Jason's user-facing conversational quality, continuity, governance behavior, and interaction semantics must remain consistent regardless of the reasoning model, model provider, or model combination used internally. Model selection, retries, escalation, repair, and cost optimization are backend implementation concerns and must not leak into or degrade the human experience.

### No raw model output reaches a human

No model-generated text may become a human-facing response merely because generation succeeded. Human-facing text must pass Jason's applicable grounding, authority, evidence, support, and Conversation Experience quality controls before delivery.

### Minimal topology

Architectural separation is a separation of authority and responsibility, not an excuse to create unnecessary components. The conversational path should use the fewest components necessary to preserve governance, auditability, replaceability, and clear ownership.

The target logical path is:

```text
Teams
  -> Conversation Kernel
  -> Central Orchestrator
  -> Conversation Kernel
  -> Teams
```

Verified conversation state and audit are Jason-owned cross-cutting concerns. Logical quality functions may exist inside these components without becoming separate agents or services.

### Teams is an interface, not an authority

The Teams/OpenClaw transport may authenticate and carry the conversation, display appropriate activity state, and deliver the final response. It must not own semantic interpretation, provider selection, capability selection, authorization, factual truth, or orchestration authority.

### The Conversation Kernel reasons about human meaning

The Conversation Kernel operates at the provider-independent information-need level. It may reason about:

- the human's target or targets;
- requested information;
- relationships;
- temporal scope;
- completeness;
- verified conversation references;
- whether material ambiguity requires clarification;
- whether the human is asking for read-only information, ordinary conversation, or a separately governed action path.

It must not select or expose providers, connectors, capability IDs, API operations, shell commands, agents, internal evidence locations, or operational authority.

### Information-read authority is deterministic

A provider-independent information need in the Conversation Experience is read-only. Its operational authority is `observe` and is owned by Jason deterministically; a reasoning model does not choose, raise, or transform that authority.

A human request for a consequential action must use Jason's separately governed action contract and normal Central Orchestrator authorization, policy, approval, execution, evidence, and audit controls. An action request must never gain execution authority by being represented as an information need.

This separation keeps the conversational contract smaller while strengthening identity-first authorization: the model describes human meaning, while Jason decides what authority the selected governed path can possess.

### Structured outcome projection

Structured-generation backends may be unable to express Jason's conversational outcome contract as a perfect discriminated union. A model can therefore correctly select `information`, `clarify`, or `conversation` while also populating fields belonging to another mutually exclusive branch.

At the reviewed Conversation Experience boundary, the selected outcome is the structural discriminator. Incompatible branch fields may be discarded as non-authoritative generation noise before canonical validation. This projection does not repair a wrong outcome and does not bypass semantic review.

Before any incompatible branch is discarded, Jason must still reject attempted internal-routing or execution selections hidden in that branch. After projection, the independent Conversation Experience reviewer must still verify that the selected outcome captures the human request, uses relevant targets, preserves completeness, follows clarification policy, and introduces no unsupported operational claim.

### Central Orchestrator remains the sole operational authority

All governed reads and actions continue through the Central Orchestrator. Identity, tenant/client scope, policy, capability/resource discovery, provider resolution, execution, approvals, audit, and final evidence provenance remain subject to existing constitutional controls.

Agents and connectors never coordinate directly. Inter-agent and inter-resource coordination remains orchestrator-mediated.

### Minimum sufficient progressive fulfillment

For read-only information needs, Jason should avoid speculative fan-out.

1. Start with one structurally appropriate primary provider-neutral resource.
2. Evaluate governed sanitized evidence against the information need.
3. Stop when the need is sufficiently supported.
4. If unsupported, select at most one additional specialized governed resource.
5. Re-evaluate before any further expansion.
6. Continue only within bounded policy and resource limits.
7. If evidence remains insufficient, return a bounded limitation or unavailable result rather than inventing an answer.

A weak or inexpensive backend model may choose a suboptimal order of specialized reads. That may increase backend latency, but it must not make unsupported information true or change the human-facing quality contract.

### Model roles are separable

Conversation quality and backend work are distinct model roles.

**Experience models** protect the human-facing experience. Their responsibilities may include provider-independent request interpretation, independent semantic review, evidence-support review, answer quality review, clarification quality, and final wording fallback.

**Work models** may perform lower-cost backend tasks such as selector-name grounding, evidence-path proposals, specialized resource search ordering, and first-pass answer drafting.

Changing a Work model must not silently change the Experience model tier. Lower-cost models should be attempted where safe; rejected work may be retried or escalated behind the interface boundary.

### Evidence before assertion

Operational facts may appear in a human-facing answer only when they are supported by authorized governed evidence. Model-selected evidence paths are proposals, not truth. Selected paths must exist in sanitized evidence, be deterministically dereferenced, and pass applicable support review before becoming conversational support.

Adjacent, correlated, similarly named, or merely available values are not substitutes for the requested information.

### Verified context only

Conversation continuity is Jason-owned state, not model memory. A literal name or selector does not become durable identity merely because the model recognized it.

Persistent resource context requires provider-governed durable identity resolution and corroborating evidence. Context such as `it`, `that endpoint`, `he`, `the ticket`, or similar references must resolve from verified state or trigger material clarification.

### Clarification policy

Jason asks for clarification only when choosing without the human would materially change target, authority, action, risk, or meaning.

Jason must not ask the human to choose an internal provider, connector, registry, log, evidence source, API, or implementation path merely because Jason has not yet discovered how to fulfill the information need.

### Human-facing response behavior

Normal conversational responses should:

- answer the human's actual question rather than narrate internal workflow;
- put useful information first;
- avoid mechanical provider/source suffixes unless provenance is relevant or requested;
- avoid capability, connector, registry, model, schema, and API terminology unless the human is explicitly discussing those internals;
- preserve bounded uncertainty and limitations naturally;
- deliver one final conversational answer rather than filling the conversation with canned processing acknowledgements.

Transport-level catastrophic failures may use a safe deterministic fallback, but ordinary progress should use platform activity state where supported rather than scripted chat messages.

## Cost and latency priority

For human-facing conversational work, optimization priority is:

1. safety and authority;
2. factual accuracy;
3. completeness;
4. conversational quality;
5. cost;
6. latency.

Jason may spend additional backend time to reduce cost when the higher-priority requirements remain satisfied. Cost optimization belongs behind the conversational boundary.

## Engineering rule: no single-example fixes

An observed failure is evidence of a failure class, not a specification for a patch.

Before implementing a correction, engineering work must identify:

1. the observed symptom;
2. the general failure class;
3. the violated invariant;
4. the generalized correction;
5. unrelated regression cases proving the triggering example was not hard-coded.

Triggering examples may be regression fixtures but must not become production semantic mappings.

## Prohibited implementation patterns

The Conversation Experience must not rely on:

- question-to-field mappings;
- synonym tables used as routing authority;
- phrase-to-provider rules;
- one-off scripts per conversational fact;
- hard-coded device/user/ticket identifiers;
- model-specific response templates as normal conversational behavior;
- first-provider-result identity selection;
- direct provider calls that bypass the Central Orchestrator;
- raw model output sent directly to Teams;
- response-text parsing used to manufacture durable resource identity;
- multi-agent conversational chains that bypass central orchestration;
- model-selected authority for read-only information needs;
- action execution authority smuggled through an information-read contract.

## Acceptance criteria

Conversation Experience acceptance should cover behavioral classes across unrelated domains rather than only known examples. At minimum, qualification should include:

- arbitrary provider-independent resource inquiry;
- specialized historical inquiry;
- multiple information needs for one resource;
- cross-resource or cross-provider inquiry;
- verified follow-up reference;
- material ambiguity;
- unavailable evidence;
- permission denial;
- approval-required action;
- provider failure;
- malformed or low-quality model output;
- contradictory mutually exclusive structured-output branches;
- incorrect cheap-model evidence/resource ordering;
- runtime/model retry or escalation;
- duplicate Teams delivery;
- ordinary conversation-only turns;
- provenance questions such as "How do you know?";
- unrelated future resource types introduced after the original implementation.

The same user-facing contract must remain valid when Work models are changed.

## Rollout and rollback

Conversation Experience changes must support an explicit runtime cutover with rollback to the previously verified flow. Rollout may replace conversational interpretation and response composition, but it must reuse existing identity, authorization, capability registry, Central Orchestrator, provider, evidence, audit, and transport authorities rather than building parallel authority paths.

Production activation requires local acceptance, CI acceptance, runtime health verification, representative live Teams behavioral testing, and audit/provenance verification.
