# Jason MCP Construction Guide

**Status:** Active construction guidance for MCP-001  
**Date:** 2026-09-08  
**Owner:** Jason Architecture Authority / Platform Owner  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`  
**Target architecture:** `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`

## Purpose

Define how to build a Jason MCP service without creating a parallel authority, provider, or workflow path.

This guide is subordinate to the Constitution, canonical architecture, platform-integrity standard, and approved ADRs.

## Component classification

The Jason MCP service is an **ingress/interface adapter plus capability projection layer**.

It is not:

- an agent with independent authority;
- a second Central Orchestrator;
- a direct connector/provider client;
- a secret broker;
- an unrestricted API proxy;
- a workflow engine;
- a replacement for Jason identity/authority/policy/evidence services.

## Mandatory request path

```text
ChatGPT MCP request
→ MCP transport/authentication
→ Jason identity binding
→ MCP tool/capability resolution
→ authority/scope/policy validation
→ Central Orchestrator
→ governed capability/provider resolution
→ connector/provider execution
→ evidence/provenance/audit
→ bounded MCP result
```

No step may short-circuit directly from MCP to a connector/provider.

## Tool registration

MCP tools should be generated or projected from governed Jason capability/resource metadata where practical.

Each tool must have:

- stable model-friendly name;
- concise description of what it can observe/do;
- input schema;
- read/action classification;
- resource/scope semantics;
- corresponding governed capability identity internally;
- evidence/result contract;
- policy/approval metadata for actions;
- lifecycle status.

The model-facing tool should not require knowledge of opaque internal operation references.

## Tool naming

Preferred:

- `search_managed_endpoints`
- `read_managed_endpoint`
- `read_endpoint_audit`
- `search_endpoint_alerts`
- `search_management_sites`
- `search_autotask_tickets`
- `read_autotask_ticket`
- `analyze_governed_evidence`

Avoid:

- provider URL/path names as the public tool contract;
- `op_1234`/opaque operation references;
- question-specific names;
- unrestricted `http_get`/`execute_api` tools;
- scripts whose names encode a business workflow.

## Identity

The MCP request must establish a supported authenticated caller identity before governed execution.

Initial design target:

- ChatGPT Business workspace/custom app identity context;
- map to Jason principal;
- initial AOT scope may allow authenticated `teamaot.com` users to invoke approved read capabilities;
- consequential actions remain independently capability-authorized and governed.

Do not infer action authority from workspace membership.

Unknown, missing, ambiguous, or untrusted identity fails closed.

## Client/tenant isolation

Every provider request remains scoped by Jason's existing organization/client rules.

MCP must never allow the model to choose arbitrary tenant/client credentials or inject provider base URLs.

Cross-client/cross-tenant access requires explicit Jason authority, not model intent.

## Secrets

The MCP service may receive credential references through normal Jason runtime composition but must not expose secret values in:

- MCP schemas;
- tool descriptions;
- tool results;
- errors;
- logs;
- audit payloads;
- ChatGPT conversation content.

Provider authentication remains inside governed secret/connector boundaries.

## Read-first pilot boundary

MCP-001 is read-only.

Before any write/action tool is exposed, the read-only service must demonstrate:

- correct identity binding;
- authority enforcement;
- client isolation;
- capability projection;
- Central Orchestrator-only execution;
- evidence/provenance;
- audit;
- bounded failure behavior;
- deterministic large-collection analysis;
- disable/rollback.

## Large evidence results

Never solve token limits by blindly forwarding unbounded provider responses.

Expose deterministic analysis capabilities over full internal evidence:

- count;
- filter;
- group;
- distinct;
- sort where useful;
- bounded list;
- completeness status;
- source/provenance references.

The model should receive exactly enough structured information to reason and explain the result.

## Provider documentation/schema

Provider docs/OpenAPI/schema may be registered as integration knowledge and refreshed automatically where appropriate.

Rules:

- documentation is descriptive;
- documentation does not grant capability authority;
- newly discovered provider operations do not become executable merely because they appear in current docs;
- capability/provider lifecycle remains explicit;
- docs may help enrich tool descriptions, field knowledge, pagination understanding, and engineering stewardship.

## Error contract

MCP errors should distinguish at least:

- identity/authentication failure;
- authorization failure;
- scope/client isolation failure;
- unavailable/retired capability;
- approval required;
- ambiguous resource/selector;
- provider unavailable/rate limited;
- incomplete evidence;
- invalid request;
- internal execution failure.

Errors must not reveal credentials, sensitive provider internals, or unnecessary stack traces.

## Audit/provenance

Every governed MCP invocation should correlate:

- MCP/tool request identity;
- authenticated Jason principal;
- workspace/session/request correlation where available;
- capability/resource requested;
- organization/client scope;
- policy/approval outcome;
- Central Orchestrator execution identity;
- provider/evidence references;
- result/failure status;
- duration/resource usage;
- Jason-side model/API usage if any.

Do not rely on ChatGPT transcript history as the sole operational audit record.

## Cost controls

Default MCP tool execution must not trigger an additional hosted model call.

If an MCP-exposed Jason capability itself requires a model:

- declare that dependency explicitly;
- use least-cost suitable model by policy;
- log cost/usage;
- bound token/tool-loop use;
- allow model escalation only through explicit policy;
- do deterministic processing first where possible.

## Local proof requirements

Before connecting ChatGPT Business:

1. MCP server starts with no secrets printed.
2. health/readiness verifies expected dependencies.
3. tool enumeration contains only approved read capabilities.
4. model-friendly tool names map internally to governed capabilities.
5. MCP cannot call connectors/providers directly.
6. unauthorized identity fails closed.
7. cross-client request fails closed.
8. valid read reaches Central Orchestrator.
9. provenance/audit is created.
10. large collection query completes through deterministic analysis.
11. service can be disabled/reverted without damaging Teams/OpenClaw baseline.

## ChatGPT Business pilot proof requirements

After local proof:

- connect/publish the custom Jason app to a limited pilot;
- verify actual authenticated identity behavior from ChatGPT;
- ask novel natural-language questions rather than regression phrases only;
- test follow-up references in the same ChatGPT session;
- test multiple governed reads in one conversation;
- test exact counts/lists across complete data;
- test failures and unavailable evidence;
- measure Jason-side OpenAI API usage (target: none for ordinary reads);
- preserve proof in `docs/sessions/`;
- register observed/verified service state in System Registry before calling it operational.

## Action-tool construction later

When actions are introduced, each action tool must additionally define:

- action authority;
- risk level;
- approval requirements;
- preconditions;
- idempotency key semantics;
- side-effect evidence;
- rollback/recovery where applicable;
- human confirmation/communication behavior where applicable.

Do not generalize a read-only MCP tool into arbitrary writes.

## Definition of done for MCP-001

MCP-001 is not complete until a future engineer/AI can establish from repository evidence:

- what the MCP service may call;
- what it may never call directly;
- how identity and authority are established;
- how tools map to governed capabilities;
- how secrets are isolated;
- how client isolation is enforced;
- how results are bounded/analyzed;
- how audit/provenance are retained;
- how the service is tested;
- how it is registered/verified;
- how it is disabled/rolled back;
- how a new provider capability becomes visible without adding question-specific code.
