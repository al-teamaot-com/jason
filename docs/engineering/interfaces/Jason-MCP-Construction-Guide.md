# Jason MCP Construction Guide

**Status:** Active construction guidance for ChatGPT/Jason MCP reads and governed actions  
**Updated:** 2026-09-16  
**Owner:** Jason Architecture Authority / Platform Owner  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`  
**Target architecture:** `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`

## Purpose

Define how to build and extend the Jason MCP service without creating a parallel authority, provider, secret, or workflow path.

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
→ approval validation when required
→ Central Orchestrator
→ governed capability/provider resolution
→ connector/provider execution
→ evidence/provenance/audit
→ bounded MCP result
```

No step may short-circuit directly from MCP to a connector/provider.

## Model-facing tool surface

The preferred surface is small and capability-oriented rather than provider-endpoint-oriented.

Current reusable MCP pattern includes:

- `jason_mcp_status` — self-report current MCP mode/governance/action state;
- `discover_capabilities` — live governed capability discovery;
- `execute_read_capability` — generic governed read execution;
- `execute_governed_capability` — generic governed action execution when explicitly activated and delivered to the client.

Provider-specific compatibility tools may exist temporarily, but new work should prefer the generic governed capability surface rather than proliferating provider/task-specific tools.

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

The model-facing tool must not require knowledge of provider URLs, credential identifiers, raw secret paths, or opaque internal operation references.

## Generic governed action construction

Do not add a new MCP write tool for every provider mutation when the operation can be represented as a governed Jason capability.

`execute_governed_capability` is the preferred generic action entry point. It may execute only a capability that is already:

1. present in Jason's live governed capability registry;
2. activated for action execution;
3. authorized for the authenticated Jason principal and scope;
4. allowed by applicable execution policy;
5. covered by the exact required approval when the capability requires per-execution approval;
6. routed through Central Orchestrator;
7. mapped to a bounded provider action/connector;
8. independently accepted by the provider;
9. audited and followed by required durable-state/job verification.

The MCP tool itself does not confer action authority.

## Exact grant and approval semantics

For consequential actions, authorization and approval are separate controls.

A request must fail closed when any required element is missing or mismatched:

- authenticated principal;
- exact capability grant;
- organization/client/resource scope;
- lifecycle/activation state;
- policy conditions;
- exact approval binding;
- approval expiry;
- target identity;
- argument/request digest where used;
- provider execution authority.

Changing a target, reason, component, variable, field, or other approval-bound argument after approval creates a different request and requires fresh authorization/approval evaluation.

A ChatGPT confirmation prompt is an additional client-side UX/safety gate. It does not replace Jason approval.

## Client action delivery is separate from backend registration

Backend MCP registration, Jason capability activation, and ChatGPT client delivery are separate states.

A tool may:

- exist in source;
- enumerate from the MCP server;
- be present in the configured ChatGPT app action catalog;
- be active in Jason's capability registry;

and still not be delivered as a callable tool to a particular ChatGPT session because of client/app permission policy or session-catalog state.

Therefore acceptance must verify both:

1. backend MCP/tool/capability state; and
2. the actual tools delivered to the live ChatGPT session.

For the current pilot, a Jason-specific ChatGPT permission mode that allows reads while asking before writes is preferred over broad unrestricted client action permission. That client setting must not weaken Jason's own grant/approval controls.

## Identity

The MCP request must establish a supported authenticated caller identity before governed execution.

Design target:

- ChatGPT Business workspace/custom app identity context;
- map to Jason principal;
- apply Jason role/grant/client/resource scope;
- consequential actions remain independently capability-authorized and approval-governed.

Do not infer action authority from workspace membership or app installation.

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

Read and write/execution credentials should remain separated where the provider/action risk model requires it. A write/execution credential is an execution mechanism, not requester authority.

## Read-first foundation and governed-action expansion

The original MCP-001 acceptance was intentionally read-only. That foundation had to prove:

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

Governed actions may be added only on top of those proven boundaries. Do not replace or bypass the read foundation to obtain write capability.

## Provider action design

A provider action behind MCP should be represented as a bounded Jason capability rather than arbitrary provider access.

Examples of acceptable bounded patterns:

- partial update of an approved Autotask ticket field through `service.ticket.update`;
- creation of a bounded ticket note through `service.ticket.note.create`;
- execution of an allowlisted Datto component on an allowed target through `automation.component.execute`.

Prohibited patterns include:

- unrestricted `http_request` or provider URL execution;
- arbitrary shell/PowerShell/script text supplied by the model for remote execution;
- arbitrary provider entity mutation endpoints;
- fallback to broader provider credentials after authorization failure;
- using a write credential as a general read path.

## Preconditions and postconditions for actions

Each action capability must define the relevant subset of:

- exact target resolution;
- current-state pre-read;
- reversible/current field value when applicable;
- allowed fields/variables;
- idempotency semantics;
- approval-bound request digest;
- provider preflight when available;
- expected provider response class;
- attempt limits;
- required durable-state/job readback;
- recovery/rollback behavior where meaningful.

An action is not accepted merely because the provider returned a transport success. Verify the resulting durable state or job outcome through a governed read path whenever possible.

## Provider authorization failure

Provider authorization remains an independent boundary.

If the provider returns `401`, `403`, or an equivalent authority denial:

- classify it as provider authorization failure;
- do not retry through a broader service/read credential;
- do not silently broaden provider permissions;
- preserve the exact requested capability/target in audit evidence;
- require an explicitly governed provider-configuration change before retry when necessary.

A provider 403 is not evidence that Jason governance failed; it may be evidence that the provider-side execution identity is correctly contained but insufficient for the intended action. Preserve that distinction.

## Runtime thread-safety requirement

MCP synchronous tools may execute in worker threads while runtime/service objects are process-cached.

Any process-cached stateful dependency must therefore be safe for the actual execution topology.

For SQLite-backed stores, default connection thread affinity can cause failures when a connection created on one thread is reused on another. The 2026-09-15 MCP repair made affected long-lived SQLite connections cross-thread usable with `check_same_thread=False`.

That setting removes SQLite's creating-thread restriction; it is **not** a general concurrency/serialization strategy. If MCP worker concurrency or replica count increases, evaluate per-thread connections, explicit locking/transaction serialization, or a shared durable database appropriate to the deployment topology.

Do not interpret a successful single-thread unit test as proof that a process-cached store is safe under MCP worker execution.

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
- Jason authorization failure;
- scope/client isolation failure;
- unavailable/retired capability;
- approval required/mismatched/expired;
- ambiguous resource/selector;
- provider authorization failure;
- provider unavailable/rate limited;
- incomplete evidence;
- invalid request;
- post-action verification failure;
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
- approval/request digest reference where applicable;
- Central Orchestrator execution identity;
- provider/evidence references;
- result/failure status;
- provider attempt count;
- post-action verification result when applicable;
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

Before connecting/publishing a new MCP build:

1. server starts with no secrets printed;
2. health/readiness verifies expected dependencies;
3. tool enumeration contains only the approved MCP surface;
4. tool names map internally to governed capabilities;
5. MCP cannot call connectors/providers directly;
6. unauthorized identity fails closed;
7. cross-client request fails closed;
8. valid read reaches Central Orchestrator;
9. action path cannot execute without exact grant/approval;
10. provider authority failure cannot trigger broader-credential fallback;
11. provenance/audit is created;
12. large collection query completes through deterministic analysis;
13. process-cached state is safe for MCP worker-thread execution;
14. service can be disabled/reverted without damaging Teams/OpenClaw baseline.

## ChatGPT Business live proof requirements

After local proof:

- connect/publish the custom Jason app to a limited pilot;
- verify actual authenticated identity behavior from ChatGPT;
- verify actual delivered tool catalog, not only server registration;
- ask novel natural-language questions rather than regression phrases only;
- test follow-up references in the same ChatGPT session;
- test multiple governed reads in one conversation;
- test exact counts/lists across complete data;
- test failures and unavailable evidence;
- for actions, verify ChatGPT confirmation behavior and Jason approval behavior separately;
- perform only separately approved bounded live actions;
- require governed post-action readback/job verification;
- measure Jason-side OpenAI API usage;
- preserve proof in `docs/sessions/`;
- reconcile System Registry state when required before claiming operational lifecycle promotion.

## Definition of done

The MCP construction pattern is documentation-complete only when a future engineer/AI can establish from repository evidence:

- what the MCP service may call;
- what it may never call directly;
- how identity and authority are established;
- how reads/actions map to governed capabilities;
- how client action delivery differs from backend registration;
- how exact grants and approvals are enforced;
- how secrets and read/write credential separation are preserved;
- how provider authorization failures behave;
- how results are bounded/analyzed;
- how side effects are verified;
- how audit/provenance are retained;
- how runtime thread safety is handled;
- how the service is tested;
- how it is registered/verified;
- how it is disabled/rolled back;
- how a new provider capability becomes visible without adding question-specific code.

## Current accepted proof reference

For the first Autotask/Datto governed-action checkpoint and current client-side exposure blocker, see:

`docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`
