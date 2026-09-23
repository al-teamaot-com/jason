# ADR-0006 — Execution Policy Engine

**Status:** Accepted

## Context

Jason requires a single governed decision point for determining how a capability is executed.

Without a central execution policy, interfaces, workflows, agents, and connectors may independently choose deterministic code, local AI, hosted AI, or human action. That would duplicate policy, create inconsistent data handling, weaken tenant isolation, and make model failover difficult to govern.

Jason also requires cost attribution so the organization can evaluate cost per task, compare execution paths, and optimize for useful outcomes rather than token volume.

## Decision

Introduce JKD-004, the Execution Policy Engine.

The engine:

- receives an authorized capability request;
- prefers deterministic execution when it can satisfy the requirement;
- selects among deterministic, local AI, hosted AI, human, and denied paths;
- enforces provider, model, data-handling, token, cost, retry, and approval policy;
- returns an execution decision and execution plan;
- creates a versioned estimated Cost Record;
- attributes retries and failover;
- remains independent of OpenClaw, Teams, CLI, APIs, agents, and providers.

Interfaces and agents may not select AI providers or models directly.

## Consequences

### Positive

- AI becomes a replaceable execution strategy.
- OpenClaw remains an operator interface.
- Model failover preserves Jason identity and policy.
- Cost becomes measurable by capability, client, provider, model, and outcome.
- Deterministic methods can be preferred where appropriate.
- Data handling and tenant restrictions are applied consistently.

### Negative

- Provider and pricing registries require stewardship.
- Cost values may initially be estimates.
- Execution planning introduces an additional Kernel decision.
- Local compute costing requires an agreed method.

## Rejected Alternatives

### Put AI selection in OpenClaw

Rejected because OpenClaw is an interface, not the source of policy or authority.

### Put AI selection in each capability

Rejected because it duplicates policy and creates inconsistent provider handling.

### Let providers choose failover automatically

Rejected because provider failover may violate tenant, cost, data-handling, or quality policy.

### Track only provider invoices

Rejected because this omits local compute, retries, deterministic workflows, and operational cost.

## Review Triggers

Review this decision when:

- a new execution mode is required;
- cost estimation proves materially inaccurate;
- pricing or usage accounting changes substantially;
- policy cannot express an operational requirement;
- provider selection begins leaking into interfaces or capabilities;
- a simpler approved platform can replace custom functionality.
