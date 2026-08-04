# JKD-004 — Execution Policy Engine

**Status:** Proposed foundation design  
**Owner:** Jason Architecture Authority  
**Applies to:** All governed execution requests, including deterministic workflows, local AI, hosted AI, human approval, human execution, and denied execution

## 1. Purpose

The Execution Policy Engine determines how an authorized Jason capability should be executed.

It does not merely answer whether AI may be used. It selects the permitted execution path after considering:

- capability requirements;
- identity and authority;
- client and tenant boundaries;
- policy;
- data classification;
- privacy and handling restrictions;
- deterministic alternatives;
- execution risk;
- provider and model availability;
- quality requirements;
- cost and token budgets;
- approval requirements;
- failover conditions;
- audit requirements.

The Execution Policy Engine is provider-neutral and interface-neutral.

OpenClaw, Teams, CLI, API clients, scheduled jobs, and future interfaces all rely on the same execution decision.

## 2. Governing Principle

Jason asks:

> How should this capability be executed?

Possible answers include:

- deterministic execution;
- local AI execution;
- hosted AI execution;
- human approval before execution;
- human execution;
- denied execution.

AI is one execution strategy among several. It is not the default execution path.

## 3. Position in the Architecture

```text
Operator Interface
    |
    v
Ingress Connector
    |
    v
Orchestrator
    |
    v
Identity and Authority
    |
    v
Execution Policy Engine
    |
    +--> Deterministic capability
    +--> Local AI provider
    +--> Hosted AI provider
    +--> Human approval
    +--> Human execution
    +--> Denied
```

The Execution Policy Engine does not execute capabilities directly.

It returns a governed execution plan to the orchestrator.

## 4. Non-Negotiable Boundaries

- Interfaces do not select models or providers.
- Agents do not select models or providers.
- Connectors do not select models or providers.
- Providers do not grant authority.
- Possession of a model credential does not grant permission to use the model.
- AI is not used when a deterministic method can satisfy the requirement within policy and quality constraints.
- No execution path may bypass identity, authority, policy, tenant isolation, or audit.
- No client data may be sent to a hosted provider unless policy explicitly permits it.
- No model output is treated as authoritative evidence.
- Failover must preserve identity, context, policy, tenant boundaries, and audit.
- Unknown policy, provider, pricing, or data-handling state fails closed or requires approval.

## 5. Inputs

The engine receives a normalized execution request containing:

- execution ID;
- correlation ID;
- capability name and version;
- requested mode;
- requester identity;
- organization and tenant;
- affected client;
- execution context;
- applicable authority decision;
- data classification;
- permitted data handling;
- deterministic execution options;
- AI execution requirements;
- quality requirements;
- latency requirements;
- risk;
- approval state;
- provider health;
- pricing registry version;
- policy references.

## 6. Execution Decision

The engine returns an `ExecutionDecision`.

Required fields:

```yaml
execution_decision:
  execution_id: exec_...
  correlation_id: corr_...
  outcome: allowed | allowed_limited | approval_required | human_required | denied
  execution_mode: deterministic | local_ai | hosted_ai | human | none
  capability: ticket.investigate
  capability_version: "0.1"
  reason_codes: []
  policy_ids: []
  approval:
    required: false
    approval_type: null
    approval_id: null
  data_handling:
    tenant_id: tenant_...
    classification: confidential
    redaction_profile: client-default
    hosted_processing_allowed: false
  budget:
    maximum_estimated_cost: 0.05
    currency: USD
    maximum_input_tokens: 12000
    maximum_output_tokens: 2000
    maximum_attempts: 2
  provider_selection:
    provider_id: null
    model_id: null
    provider_region: null
  audit_required: true
  expires_at: "..."
```

The decision is policy output. It is not an execution result.

## 7. Execution Plan

When execution is allowed, the engine returns an `ExecutionPlan`.

Required fields:

```yaml
execution_plan:
  execution_id: exec_...
  correlation_id: corr_...
  execution_mode: deterministic | local_ai | hosted_ai | human
  capability: ticket.investigate
  capability_version: "0.1"
  provider:
    provider_id: openai
    model_id: approved-model
    region: null
  constraints:
    tenant_id: tenant_...
    maximum_estimated_cost: 0.05
    currency: USD
    maximum_input_tokens: 12000
    maximum_output_tokens: 2000
    maximum_attempts: 2
    timeout_seconds: 60
  data_handling:
    classification: confidential
    redaction_profile: client-default
    hosted_processing_allowed: true
    retention_allowed: false
  quality:
    minimum_confidence: 0.70
    schema_required: true
    citations_required: true
  failover:
    allowed: true
    approved_paths:
      - local_ai
      - hosted_ai
    preserve_context: true
    preserve_policy: true
  audit:
    required: true
    pricing_version: pricing-...
```

The orchestrator executes only the approved plan.

## 8. Deterministic-First Policy

Before permitting AI, the engine evaluates whether a deterministic capability can satisfy the requested outcome.

Deterministic execution should be preferred when it:

- satisfies the capability contract;
- meets required quality;
- stays within risk and authority;
- provides adequate explainability;
- completes within acceptable time;
- costs less than the approved AI path;
- does not create greater operational burden.

A deterministic method must not be chosen merely because it is cheaper if it cannot produce the required outcome.

## 9. AI Execution Modes

### 9.1 Local AI

Local AI may be selected when:

- hosted processing is prohibited;
- data sensitivity requires local handling;
- an approved local model can meet the quality requirement;
- local compute is healthy and available;
- estimated cost and latency are acceptable.

### 9.2 Hosted AI

Hosted AI may be selected when:

- policy permits external processing;
- the provider and model are approved;
- the provider region and data handling are acceptable;
- the request is within token and cost budgets;
- provider health is acceptable;
- the model meets capability quality requirements.

### 9.3 Human Execution

Human execution is required when:

- no approved automated path exists;
- authority is insufficient;
- policy requires professional judgment;
- evidence is too uncertain;
- data handling cannot be safely automated;
- cost or risk exceeds automated limits;
- a qualified person must make the determination.

## 10. Provider and Model Selection

The engine selects from an approved provider registry.

Selection criteria include:

- capability compatibility;
- data-handling policy;
- tenant restrictions;
- model quality history;
- provider health;
- latency;
- estimated total cost;
- token limits;
- regional availability;
- known limitations;
- failover compatibility;
- Technology Steward status.

The engine does not accept a provider or model name from free-form prompt text as authoritative.

## 11. Cost Estimation

Every execution plan must include a pre-execution cost estimate when practical.

Every completed execution must create a post-execution Cost Record.

Jason distinguishes:

1. provider cost;
2. internal compute cost;
3. infrastructure cost;
4. operational cost;
5. total estimated cost.

Cost remains an estimate unless the provider later supplies authoritative billing data.

## 12. Cost Record

```yaml
cost_record:
  cost_record_id: cost_...
  execution_id: exec_...
  correlation_id: corr_...
  tenant_id: tenant_...
  client_id: client_...
  capability: ticket.investigate
  execution_mode: hosted_ai
  provider_id: openai
  model_id: approved-model
  usage:
    input_tokens: 8420
    output_tokens: 611
    cached_input_tokens: 0
    reasoning_tokens: 0
    tool_calls: 3
    attempts: 1
    execution_seconds: 14.2
  cost:
    provider_cost: 0.0184
    internal_compute_cost: 0.0000
    infrastructure_cost: 0.0003
    operational_cost: 0.0000
    total_estimated_cost: 0.0187
    currency: USD
  pricing:
    pricing_source: provider-registry
    pricing_version: openai-2026-08-04
    effective_at: "2026-08-04T00:00:00Z"
  estimate:
    confidence: high
    measured_at: "..."
    limitations: []
```

## 13. Pricing Registry

Jason maintains a versioned pricing registry.

Each pricing entry records:

- provider;
- model;
- execution mode;
- input token price;
- output token price;
- cached token price;
- request or tool-call charges;
- applicable unit;
- currency;
- effective date;
- expiration or supersession date;
- source;
- last verification time;
- Technology Steward owner;
- confidence.

Pricing values must not be embedded throughout business logic.

Unknown or stale pricing must be visible in the cost record.

## 14. Local Compute Costing

Local AI cost estimates may include:

- measured execution time;
- CPU or GPU utilization;
- electricity estimate;
- hardware amortization;
- hosting cost;
- storage and network cost;
- platform maintenance allocation.

The initial method may use a governed standard internal rate per compute-second.

The method must be documented and versioned.

Local AI must not be labeled free merely because no API invoice exists.

## 15. Deterministic Execution Costing

Deterministic execution may include:

- connector API charges;
- workflow execution charges;
- infrastructure runtime;
- storage;
- network transfer;
- third-party transaction charges;
- operational retries.

Near-zero cost may be recorded as zero when the estimation method and threshold are documented.

## 16. Retry and Failover Attribution

Every attempt contributes to total cost.

The final Cost Record must preserve:

- number of attempts;
- original execution path;
- failed execution paths;
- failover reason;
- cost of each attempt;
- total accumulated cost;
- final successful or failed path.

Failover must not hide the cost of failed attempts.

## 17. Pre-Execution Budget Enforcement

The engine may enforce:

- maximum estimated cost per execution;
- maximum input tokens;
- maximum output tokens;
- maximum attempts;
- maximum provider calls;
- maximum wall-clock time;
- daily or monthly client budget;
- capability-specific budget;
- approval threshold.

When the estimated cost exceeds the allowed budget, the engine must:

- choose a compliant lower-cost path;
- reduce scope within policy;
- request approval;
- require human execution;
- or deny the request.

It must not silently exceed the budget.

## 18. Post-Execution Reconciliation

After execution, Jason compares:

- estimated cost;
- measured usage;
- calculated cost;
- provider-reported usage;
- provider invoice data when later available.

Material variance should be recorded and may trigger pricing or estimation review.

## 19. Optimization Metrics

Jason should support reporting such as:

- cost per completed capability;
- cost per useful recommendation;
- cost per client;
- cost per provider;
- cost per model;
- cost per execution mode;
- retry and failover cost;
- estimated technician time saved;
- recommendation acceptance rate;
- quality-gate failure rate;
- useful outcome per dollar;
- false-confidence cost;
- human rework associated with model output.

Jason optimizes for verified useful outcome per total cost, not merely cheapest execution.

## 20. Audit Requirements

Audit records must include:

- execution request;
- authority decision;
- policy decision;
- selected execution mode;
- provider and model when applicable;
- pricing version;
- estimated cost;
- budget;
- approval requirement;
- data classification;
- redaction profile;
- failover decisions;
- actual usage;
- final estimated cost;
- result status;
- verification status.

Audit must not include:

- access tokens;
- API keys;
- private keys;
- unrestricted prompt content;
- secrets;
- raw provider credentials.

## 21. Failover

Failover is a new governed execution decision, not an uncontrolled provider retry.

A failover plan must preserve:

- Jason identity;
- tenant context;
- execution context;
- authority;
- policy;
- data restrictions;
- cost budget;
- audit correlation;
- output contract.

The alternate provider or model must be independently approved for the capability and data class.

## 22. Provider Health

Provider health may influence selection but does not override policy.

Health inputs may include:

- availability;
- latency;
- error rate;
- throttling;
- quota;
- recent quality failures;
- pricing uncertainty;
- regional outage;
- local compute saturation.

An unhealthy provider must not be selected merely because it is the default.

## 23. Initial Implementation Scope

The first implementation should include:

- provider-neutral request and plan contracts;
- deterministic, local AI, hosted AI, human, and denied modes;
- in-memory policy and pricing registries;
- deterministic-first selection;
- fixed budget enforcement;
- versioned cost estimation;
- post-execution Cost Record creation;
- attempt and failover attribution;
- safe audit events;
- focused tests.

The first implementation should not include:

- automatic provider purchasing;
- live billing reconciliation;
- dynamic self-modifying pricing;
- autonomous policy creation;
- uncontrolled model benchmarking;
- client-facing billing;
- unrestricted provider discovery.

## 24. Technology Steward Review

The Technology Steward reviews:

- provider availability;
- model deprecations;
- pricing changes;
- token accounting changes;
- data-handling terms;
- regional processing;
- API contract changes;
- quality history;
- opportunities to replace custom code;
- retirement criteria.

## 25. Completion Criteria

JKD-004 is ready for production implementation when:

- execution contracts are approved;
- cost contracts are approved;
- provider and pricing registries are defined;
- deterministic-first policy is approved;
- tenant and data handling rules are mapped;
- failover behavior is defined;
- audit requirements are defined;
- initial test cases are approved;
- the design passes architectural review.
