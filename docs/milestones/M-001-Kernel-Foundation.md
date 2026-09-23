# M-001 — Kernel Foundation

**Version:** 0.1.0
**Status:** Complete
**Owner:** Jason Architecture Authority
**Completion evidence:** CAP-001 governed Kernel integration

## 1. Purpose

This milestone declares the first stable Jason Kernel foundation complete.

The Kernel is the governed decision boundary for capability identity, provider eligibility, execution policy, and capability resolution. Future capabilities shall consume these services rather than recreate or bypass them.

This milestone does not declare Jason production-ready. It establishes a tested architectural baseline on which governed capabilities can be built.

## 2. Completed Kernel foundation

The milestone includes the following governed Kernel components and boundaries:

- **JKD-001 — Identity and Authority Service**: bounded execution context and authority validation foundation;
- **JKD-002 — Evidence and Memory Service**: canonical architecture for evidence, case history, decision lineage, and outcome preservation;
- **JKD-003 — Secrets Broker**: provider-neutral governed secret-resolution boundary;
- **JKD-004 — Execution Policy Engine**: deterministic execution decisions and governed execution plans;
- **JKD-005 — Execution Provider Registry**: provider identity, lifecycle, health, approval, capability, classification, and region metadata;
- **JKD-006 — Capability Registry**: canonical capability identity, lifecycle, governance metadata, version resolution, and discovery;
- **JKD-007 — Governed Capability Resolution Engine**: stateless composition of capability resolution, provider discovery, and execution policy.

The executable Kernel foundation currently includes in-memory implementations for execution policy, execution providers, capabilities, capability resolution, and supporting client-boundary services.

## 3. Proven end-to-end behavior

CAP-001 — Professional Ticket Investigation proves that a real governed capability can consume the Kernel before beginning business work.

The canonical sequence is:

```text
CAP-001 Investigation Request
        |
        v
Execution Context Validation
        |
        v
JKD-007 Governed Capability Resolution Engine
        |
        +--> JKD-006 Capability Registry
        |
        +--> JKD-005 Execution Provider Registry
        |
        +--> JKD-004 Execution Policy Engine
        |
        v
Governed Execution Plan
        |
        v
CAP-001 Investigation Workflow
        |
        v
Evidence Collection and Read-Only Recommendation
```

This proves that:

1. authority is evaluated before governed resolution;
2. capability identity is canonical and versioned;
3. capabilities do not select their own providers;
4. providers do not select themselves;
5. policy remains authoritative for the execution outcome and plan;
6. denied or unresolved requests fail closed before evidence collection;
7. successful resolution produces an auditable governed execution plan;
8. CAP-001 remains read-only and recommendation-only.

## 4. Stable Kernel API surface

The following contract families are the first stable Kernel API surface for Version 0.1:

- execution context and authority decision;
- capability definition and capability query;
- execution provider definition and candidate query;
- execution request, execution candidate, execution decision, and execution plan;
- capability-resolution request and capability-resolution result;
- data-handling policy and execution budget.

Stable means that future capabilities may depend on these contracts and their documented semantics.

Stable does not mean immutable forever. A breaking change requires:

1. an accepted Architecture Decision Record;
2. updates to each affected JKD or capability specification;
3. migration notes for callers and stored representations;
4. a contract or package version increment;
5. updated tests proving old and new behavior are handled deliberately;
6. a documented review of downstream capabilities and integrations.

Additive changes that preserve existing behavior still require tests and documentation alignment.

## 5. Architectural guarantees

The Kernel foundation establishes these guarantees:

- **Fail closed.** Missing authority, identity, isolation context, provider eligibility, approval, or policy satisfaction never becomes implicit permission.
- **Policy is authoritative.** Capabilities, providers, interfaces, and orchestrators do not override policy decisions.
- **Providers never self-select.** Provider eligibility and selection are governed outside the provider.
- **Capabilities never bypass resolution.** A capability consumes a governed result before beginning covered work.
- **Client and tenant isolation are explicit.** Isolation context is part of governed resolution, not an adapter convention.
- **Contracts are structured and versioned.** Runtime meaning is carried by defined contracts rather than prompt text or undocumented convention.
- **Decisions are explainable.** Outcomes include deterministic reason codes and policy references.
- **Execution plans are bounded.** A plan records capability, provider, mode, isolation context, budget, data handling, attempts, and policy references.
- **Kernel composition is stateless where practical.** Registries own state; composition engines compose authoritative state without creating hidden repositories.
- **Business work remains outside the Kernel.** The Kernel governs; capabilities and approved providers perform work.

## 6. Validation evidence

At milestone completion:

- 79 Kernel tests pass;
- 21 CAP-001 tests pass;
- CAP-001 resolves through the real Capability Registry, Execution Provider Registry, Execution Policy Engine, and Governed Capability Resolution Engine;
- authority denial fails closed;
- unresolved or denied capability resolution prevents evidence collection;
- successful resolution records the selected provider and policy-bound execution plan;
- the client-boundary tamper test was made deterministic and passed ten consecutive focused runs;
- the strict MkDocs build passes;
- repository whitespace validation passes.

These tests are foundation evidence, not a substitute for production pilot validation.

## 7. Intentionally deferred work

The following remain outside this milestone unless a later approved capability demonstrates that they belong in the Kernel:

- live provider execution;
- production provider credentials and configuration;
- persistent capability, provider, resolution, or policy repositories beyond current pilot stores;
- multi-capability dependency planning;
- retries and fallback execution;
- scheduling;
- dynamic discovery;
- distributed execution;
- external API exposure beyond the existing reference contract;
- full Orchestration integration;
- user interface and dashboards;
- generalized agent runtime;
- automatic learning promotion;
- production operational approval.

Deferred work shall not be added to the Kernel merely because it is broadly useful. A real governed capability must demonstrate the need and correct architectural ownership.

## 8. Extension rule

Future work should extend Jason in this order:

1. use an existing approved platform capability when it is dependable and sufficient;
2. use the stable Kernel contracts and services;
3. add a governed capability or provider adapter outside the Kernel;
4. change the Kernel only when operating evidence shows that the shared boundary is incomplete;
5. document that change through the required architectural process.

The default question is no longer, “What Kernel component should be added?”

The default question is, “What governed capability should use the Kernel next?”

## 9. Version declaration

**Jason Kernel Foundation v0.1.0** is the first stable governed Kernel baseline.

Future capabilities shall extend this architecture rather than redefine it. Breaking Kernel changes require an ADR, affected-component updates, migration notes, tests, and a semantic version increment.

## 10. References

- `01-Foundation/J-002-Constitution.md`
- `03-Components/Kernel/JKD-001-Identity-and-Authority-Service.md`
- `03-Components/Kernel/JKD-002-Evidence-and-Memory-Service.md`
- `03-Components/Kernel/JKD-003-Secrets-Broker.md`
- `03-Components/Kernel/JKD-004-Execution-Policy-Engine.md`
- `03-Components/Kernel/JKD-005-Execution-Provider-Registry.md`
- `03-Components/Kernel/JKD-006-Capability-Registry.md`
- `03-Components/Kernel/JKD-007-Governed-Capability-Resolution-Engine.md`
- `03-Components/Capabilities/CAP-001-Professional-Ticket-Investigation.md`
- `04-Standards/J-401-Adaptive-Build-Method.md`
- `04-Standards/J-402-Capability-Definition-of-Done.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
- `05-ADR/ADR-001-Vertical-Slice-First.md`
