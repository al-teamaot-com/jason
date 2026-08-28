# CAP-002: Local Ticket Intelligence

**Status:** Retired; superseded by CAP-003  
**Retired:** 2026-08-07

## Historical purpose

CAP-002 was the first governed proof that Jason could combine the canonical read-only Autotask path, the Central Orchestrator, durable evidence, and the local loopback-only Ollama model into a useful technician-facing workflow.

The operator supplied a unique Autotask ticket number and identity context. The Central Orchestrator resolved the named capability `support.ticket.analyze`, selected the governed local provider, invoked the registered CAP-002 implementation, persisted orchestration lifecycle events, and returned a structured technician briefing.

## Retirement decision

CAP-002 was intentionally transitional. Maintaining a ticket-specific runtime in parallel with the broader Autotask business-context architecture would create duplicate orchestration, duplicate local-LLM handling, and a second long-term capability model for the same provider data.

On 2026-08-07, CAP-003 proved replacement parity through the canonical `autotask.business.context` capability using optional ticket focus. Live execution `cap003-ticket-parity-live-004`:

- resolved `James Bales Financial LLC` to Autotask company ID `208`;
- explicitly resolved focused ticket `T20260805.0064` through the canonical `autotask.ticket.search` path;
- verified the ticket belonged to the resolved company boundary;
- analyzed the focused ticket together with bounded company context using local model `qwen3:1.7b`;
- completed through the Central Orchestrator with the expected four-event lifecycle ending in `orchestration.capability.completed`;
- produced protected briefing and evidence artifacts;
- made no provider-side change; and
- completed in approximately 117 seconds on the CPU-only pilot host.

After that parity proof, the CAP-002 runtime package, tests, and `tools/ticket_intelligence.py` operator command were retired. Regression tests now deny reintroduction of the retired `support.ticket.analyze` runtime.

## Superseding capability

Current governed path:

```text
autotask.business.context
```

Operator command:

```text
tools/autotask_business_context.py
```

Ticket-focused use remains available through the optional `--ticket-number` argument while retaining the broader company/business-context architecture.

## Preserved architectural lessons

CAP-002 established several controls that remain part of CAP-003:

- central orchestration rather than direct capability-to-capability invocation;
- canonical Autotask read access and governed secret resolution;
- read-only provider behavior;
- loopback-only local model processing for the pilot;
- provider content treated as untrusted data rather than instructions;
- protected evidence outside the repository;
- durable correlated orchestration events;
- one-attempt execution without hidden autonomous recovery; and
- model output treated as advisory interpretation rather than authoritative provider fact.

This document remains as institutional memory. It does not describe an active runtime capability.
