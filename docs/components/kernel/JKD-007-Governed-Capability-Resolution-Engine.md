# JKD-007 — Governed Capability Resolution Engine

**Status:** Proposed foundation design
**Owner:** Jason Architecture Authority
**Applies to:** Governed resolution of invokable capability requests

## 1. Purpose

The Governed Capability Resolution Engine composes existing Kernel services
to determine whether a requested capability can proceed and, when allowed,
which governed execution plan applies.

The engine answers:

> Given a capability request, what capability definition applies, which
> providers are technically eligible, and what governed execution outcome
> should be returned?

The engine resolves execution intent.

It does not execute work.

## 2. Governing Principle

Resolution is a Kernel decision.

Orchestration may request resolution and act on the returned result, but it
may not independently redefine capability identity, provider eligibility,
or execution policy.

Providers may declare technical support.

Providers may not select themselves.

The Execution Policy Engine remains authoritative for whether and how
execution may proceed.

## 3. Position in the Architecture

```text
Capability Resolution Request
    |
    v
Identity and Authority Context
    |
    v
Capability Registry
    |
    v
Execution Provider Registry
    |
    v
Execution Policy Engine
    |
    v
Governed Resolution Result
    |
    v
Orchestration
```

The engine coordinates these lookups and evaluations without absorbing
their ownership responsibilities.

## 4. Authoritative Dependencies

The engine depends on:

- JKD-006 Capability Registry for capability identity, lifecycle, contract,
  risk, execution modes, approval, evidence, isolation, and failure behavior;
- JKD-005 Execution Provider Registry for provider identity, technical
  support, health, approval, classifications, regions, limits, and features;
- JKD-004 Execution Policy Engine for the final execution-policy outcome and
  governed execution plan.

The engine may translate records between these services.

It may not redefine them.

## 5. Resolution Input

The initial resolution request includes:

- execution identity;
- correlation identity;
- canonical capability name;
- optional explicit capability version;
- tenant identity;
- optional client identity;
- requested execution mode;
- authority result;
- approval state;
- applicable risk;
- data-handling policy;
- execution budget;
- optional region preference;
- applicable policy IDs;
- whether pilot capability use is permitted;
- whether pilot provider use is permitted.

The request must not contain provider-selected authority or policy results.

## 6. Resolution Output

The initial resolution result includes:

- execution identity;
- correlation identity;
- resolved capability name and version;
- resolution outcome;
- structured reason codes;
- capability resolution status;
- eligible provider IDs;
- selected provider ID when applicable;
- Execution Policy Engine decision;
- governed execution plan when allowed;
- approval or human-action requirement when applicable;
- audit requirement;
- limitations and resolution metadata.

A result may deny or defer execution without returning a plan.

## 7. Resolution Sequence

The engine performs the initial resolution sequence in this order:

1. validate the resolution request;
2. resolve the requested capability and version;
3. confirm capability lifecycle permits the requested use;
4. confirm the requested execution mode is permitted by the capability;
5. confirm tenant and client context satisfy capability isolation rules;
6. query technically eligible execution providers;
7. translate eligible providers into execution-policy candidates;
8. invoke the Execution Policy Engine;
9. return the policy outcome and governed execution plan;
10. preserve structured reason codes and audit requirements.

The sequence is deterministic for identical inputs and registry state.

## 8. Capability Resolution Rules

When a version is explicitly requested, the engine resolves that exact
name-and-version pair.

When no version is requested, the engine resolves the current capability
version through the Capability Registry.

Pilot capability versions may be considered only when pilot use is
explicitly allowed.

Proposed, building, deprecated, suspended, and retired capability versions
are not eligible for execution resolution.

A resolved capability must permit the requested execution mode.

The engine must not infer version compatibility silently.

## 9. Provider Eligibility Rules

A provider is technically eligible only when the Execution Provider
Registry confirms that it:

- supports the resolved capability;
- supports the requested execution mode;
- supports the applicable data classification;
- satisfies the requested region when one is specified;
- has an eligible lifecycle state;
- has an eligible approval state;
- has acceptable health under the requested resolution policy.

Provider eligibility establishes technical candidacy only.

It does not establish authority or final permission to execute.

The engine translates eligible provider records into
`ExecutionCandidate` contracts for policy evaluation.

The translation is explicit and deterministic.

## 10. Policy Authority

The Execution Policy Engine remains authoritative for the final outcome.

The Resolution Engine may prepare and submit an `ExecutionRequest`, but it
may not override the resulting `ExecutionDecision`.

Allowed outcomes may include:

- allowed;
- allowed with limits;
- approval required;
- human required;
- denied.

A governed execution plan may be returned only when the policy decision
includes one.

The Resolution Engine must not synthesize its own execution plan after a
non-allowing policy outcome.

## 11. Isolation and Context Rules

When the capability requires tenant isolation, a tenant identity is
mandatory.

When the capability requires client isolation, a client identity is
mandatory.

The engine must fail closed when required context is missing or ambiguous.

The engine does not authenticate identities or grant authority.

It consumes validated identity and authority context produced by the
appropriate Kernel service.

## 12. Failure and Denial Behavior

Resolution fails closed.

The engine returns a structured non-execution result when:

- the capability is unknown;
- no eligible capability version exists;
- the capability lifecycle disallows use;
- the requested execution mode is prohibited;
- required tenant or client context is missing;
- no technically eligible provider exists;
- authority is absent;
- required approval is absent;
- data handling cannot be satisfied;
- budget or provider limits cannot be satisfied;
- policy denies or requires human action;
- a required dependency is unavailable.

The engine must not create an execution plan after any unresolved blocking
condition.

## 13. Determinism and Explainability

For identical requests and unchanged Kernel state, the engine must produce
the same resolution outcome.

Provider candidate ordering must be deterministic.

Reason codes must identify the stage at which resolution stopped or the
basis on which execution was allowed.

The initial foundation does not perform nondeterministic optimization.

Cost, quality, latency, or regional preference ranking remains governed by
existing policy behavior or future approved architecture.

## 14. Non-Responsibilities

The engine does not:

- authenticate identities;
- grant authority;
- obtain approval;
- define capabilities;
- register providers;
- determine provider health independently;
- define pricing;
- alter policy;
- execute providers;
- call external systems;
- manage secrets;
- persist audit evidence;
- orchestrate capability dependencies;
- retry executions;
- monitor execution progress;
- assemble final user responses.

## 15. Foundation Scope

The first implementation will include:

- immutable resolution request and result contracts;
- deterministic capability lookup;
- explicit version and current-version resolution;
- capability lifecycle and execution-mode checks;
- tenant and client isolation checks;
- provider candidate discovery;
- provider-to-policy candidate translation;
- Execution Policy Engine invocation;
- structured denial and approval-required outcomes;
- governed execution-plan return;
- focused Kernel tests;
- full Kernel regression coverage.

The foundation will not include:

- persistence;
- dependency graph planning;
- dynamic discovery;
- live provider execution;
- retries or fallback execution;
- optimization across cost, quality, or latency beyond policy behavior;
- audit persistence;
- Orchestration integration;
- external API exposure.

## 16. Acceptance Criteria

The foundation is acceptable when:

1. unknown capabilities fail closed;
2. version resolution is deterministic;
3. inactive capabilities do not resolve for execution;
4. prohibited execution modes are rejected;
5. required tenant and client isolation is enforced;
6. providers cannot select themselves;
7. only eligible providers become policy candidates;
8. policy remains authoritative for the final execution outcome;
9. no plan is returned for denied or unresolved requests;
10. approval-required and human-required outcomes remain explicit;
11. no provider execution or external-system logic is introduced;
12. tests pass independently of live providers;
13. documentation and implementation remain aligned.

## 17. Foundation Implementation Status

The first stateless Governed Capability Resolution Engine foundation is
implemented under:

`implementation/kernel/resolution/`

The implementation includes:

- immutable resolution request and result contracts;
- deterministic exact-version and current-version capability resolution;
- capability lifecycle and execution-mode validation;
- tenant and client isolation checks;
- explicit pilot capability and provider controls;
- provider candidate discovery through the Execution Provider Registry;
- deterministic provider-to-policy candidate translation;
- Execution Policy Engine invocation;
- structured unresolved, denied, approval-required, human-required, and
  resolved outcomes;
- governed execution-plan return only when supplied by policy;
- deterministic provider ordering;
- focused JKD-007 tests;
- full Kernel regression coverage.

The Resolution Engine is stateless and contains no repository.

The implementation does not include:

- persistence;
- dependency graph planning;
- dynamic discovery;
- live provider execution;
- retries or fallback execution;
- optimization beyond existing policy behavior;
- audit persistence;
- Orchestration integration;
- external API exposure.

## 18. References

- `03-Components/Kernel/JKD-004-Execution-Policy-Engine.md`
- `03-Components/Kernel/JKD-005-Execution-Provider-Registry.md`
- `03-Components/Kernel/JKD-006-Capability-Registry.md`
- `architecture/adr/ADR-0009-Governed-Capability-Resolution-Engine.md`
