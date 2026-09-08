# J-104 — ChatGPT-First Jason Access Architecture

**Status:** Active target architecture  
**Date:** 2026-09-08  
**Owner:** Jason Architecture Authority  
**Decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`

## Purpose

Define the target technician interaction architecture in which ChatGPT Business provides the primary conversational experience and Jason provides governed operational capabilities through MCP/tool interfaces.

This architecture deliberately separates **conversation intelligence** from **operational authority**.

## Target topology

```text
Technician
    ↓
ChatGPT Business workspace/session
    ↓
ChatGPT conversation + reasoning + session continuity
    ↓
Jason MCP service
    ↓
Identity / scope binding
    ↓
Authority / policy / approval gates
    ↓
Central Orchestrator
    ↓
Capability / resource registry
    ↓
Governed connector/provider execution
    ↓
Datto RMM / Autotask / Microsoft 365 / IT Glue / other approved providers
    ↓
Evidence / provenance / deterministic analysis
    ↓
Structured result to ChatGPT
    ↓
Technician-facing answer in the same ChatGPT session
```

## Primary design principle

**ChatGPT reasons. Jason governs and executes.**

ChatGPT is not Jason's authority layer. Jason is not a replacement conversational model runtime.

## Responsibility matrix

| Responsibility | ChatGPT Business | Jason | Provider/connector |
|---|---:|---:|---:|
| Natural conversation | Primary | No duplicate by default | No |
| Multi-turn context | Primary session owner | Only durable/governed state Jason must own | No |
| Tool selection | May request | Validates availability/authority | No |
| Identity evidence | Supplies supported caller/workspace identity context | Binds to Jason principal/org/client | No |
| Business authority | No | Enforces human-defined authority | No |
| Policy / risk / approvals | No | Primary | No |
| Credentials | Never | Governed secret broker/reference | Receives only through approved boundary |
| Provider API execution | No | Coordinates | Executes bounded request |
| Pagination / deterministic aggregation | May request | Preferred execution location | Supplies source data |
| Evidence / provenance / audit | Consumes structured evidence | Primary | Supplies source evidence |
| Final conversational synthesis | Primary | May supply bounded structured result | No |

## MCP service boundary

The MCP service is an **interface adapter to Jason capabilities**, not a second orchestrator.

It must:

- authenticate/bind the requesting ChatGPT user/workspace through a supported identity pattern;
- expose only registered, approved Jason capabilities;
- translate model-facing tool calls into governed Jason capability requests;
- call the Central Orchestrator rather than connectors/providers directly;
- return structured, bounded, provenance-bearing results;
- preserve read/write/action distinctions;
- preserve approvals and policy gates;
- reject unsupported, unauthorized, ambiguous, or out-of-scope operations;
- never expose secrets or raw secret-management interfaces;
- never grant authority based merely on possession of the MCP connection.

## Tool-surface architecture

### Model-facing tool qualities

Tools should be:

- meaningful to a technical operator/model;
- reusable across wording variations;
- capability/resource oriented;
- narrow enough to govern and audit;
- rich enough to avoid dozens of phrase-specific tools;
- stable when a provider changes implementation details.

Examples of preferred concepts:

- search managed endpoints;
- read managed endpoint;
- read endpoint audit/inventory;
- search endpoint alerts;
- search organizations/sites;
- search Autotask tickets;
- read ticket;
- search contacts;
- read Microsoft 365 user/sign-in/license state;
- deterministic aggregate/filter/group operations over governed evidence.

Avoid:

- `how_many_windows_10_devices`;
- `who_logged_into_50282`;
- question/phrase-specific tools;
- unrestricted provider HTTP;
- direct connector handles;
- opaque internal operation references as the principal model vocabulary.

## Integration knowledge

Provider documentation/schema knowledge may be exposed to reasoning when it improves tool use, but it is descriptive only.

Preferred integration registration may include:

```text
provider identity
+ governed credential reference
+ API/runtime endpoint metadata
+ live provider documentation/schema URL where available
+ capability/resource manifest
+ governance/policy metadata
```

Documentation/schema refresh may be automatic and cached, but must not grant new execution authority automatically. Newly documented operations become executable only after they enter the governed capability/provider lifecycle.

## Large collection handling

Do not send complete unbounded provider datasets into ChatGPT merely to calculate simple results.

Jason should provide deterministic operations for:

- pagination to completeness;
- count;
- filtering;
- distinct values;
- grouping;
- bounded lists;
- joins/correlation where governed;
- cross-provider normalization where governed.

The model should be able to ask Jason to perform these operations over complete governed evidence and receive concise results plus completeness/provenance metadata.

## Cross-provider reasoning

The target experience should allow ChatGPT to compose multiple Jason tools naturally:

```text
question
→ read endpoint state from Datto RMM
→ read associated ticket/client state from Autotask
→ read identity/license/sign-in state from Microsoft 365
→ reason across structured evidence
→ answer technician
```

Jason must not create a bespoke workflow for each such question. The provider/capability boundaries should make composition possible without changing Jason's conversational code.

## Session and memory boundary

ChatGPT owns ordinary conversational continuity for the primary interface.

Jason persists only state that is operationally/governance-significant, including as appropriate:

- authenticated principal binding;
- organization/client scope;
- approvals;
- action continuation/state;
- resource identities that must remain durable;
- correlation/idempotency state;
- evidence/provenance/audit;
- policy-required memory;
- bounded task continuation state that cannot safely depend only on chat context.

Jason should not mirror the full ChatGPT transcript solely to reproduce conversational memory.

## Cost architecture

### Goal

Use the AI capability already available in the technician's ChatGPT Business session and avoid paying for a second model to do the same reasoning.

### Default rules

- no Jason-side OpenAI call for ordinary MCP tool execution;
- no second-model restatement of the user's request;
- no second-model synthesis when ChatGPT can synthesize the returned structured evidence;
- deterministic data processing in Jason;
- cache stable schemas/provider docs;
- bound result payloads;
- use least-cost hosted model only when a Jason capability explicitly requires model reasoning;
- policy-controlled escalation for exceptional workloads;
- maintain cost/usage telemetry.

### Separate cost domains

ChatGPT Business subscription usage and OpenAI API usage are separate. The architecture must measure Jason-side API spend independently so duplicate model usage is visible.

## Security model

Before production pilot:

1. establish supported ChatGPT/MCP caller authentication;
2. map caller to Jason identity;
3. prove organization/client isolation;
4. enforce capability-specific authority;
5. return no provider secrets;
6. rate-limit/resource-bound tool usage;
7. sanitize provider evidence;
8. log/audit each governed execution;
9. validate write tools separately from reads;
10. preserve approval/precondition/idempotency controls;
11. provide rapid disable/revocation of the MCP service/app.

## Action model

Read-only capability exposure comes first.

Consequential actions remain a later phase and must satisfy all existing Jason controls. ChatGPT may request an action, but Jason decides whether it is authorized, whether approval is required, whether preconditions are satisfied, and whether execution may proceed.

## Teams architecture after this pivot

Teams remains deployed and useful, but its preferred role changes.

Primary future Teams use:

- notifications;
- approvals;
- short operational requests;
- proactive/outbound communication;
- secondary/fallback technician access.

Do not continue expanding Teams-specific conversational machinery solely to imitate the ChatGPT experience.

## OpenClaw architecture after this pivot

OpenClaw becomes optional infrastructure rather than Jason's preferred conversational brain.

Retain it only where it provides justified capabilities. It must not bypass Jason governance. Its eventual role may be transport, proactive automation, compatibility, specialist tooling, or retirement.

## Migration safety

The current Teams/OpenClaw/Jason topology remains valid production/historical evidence until actually changed and verified.

This target architecture is not a claim that MCP is already deployed.

Production transition requires:

- implementation;
- deterministic tests;
- identity/authority proof;
- pilot evidence;
- System Registry registration;
- current-state verification;
- rollback plan;
- documentation update after observed state changes.

## Measures of success

The target architecture succeeds when technicians can:

- talk to Jason as naturally as a normal ChatGPT conversation;
- ask novel questions without phrase-specific code;
- use follow-up context naturally;
- combine evidence across providers;
- receive exact collection-wide results when source data permits;
- request governed actions without gaining unauthorized authority;
- see useful source/provenance context;
- do all of the above with materially less custom conversation code and duplicate model spend.

## Non-goals

This architecture does not:

- make ChatGPT the source of business authority;
- eliminate Central Orchestrator;
- eliminate Jason governance;
- grant ChatGPT direct provider credentials;
- permit unrestricted provider API access;
- require immediate retirement of Teams or OpenClaw;
- declare MCP production-ready before verification.
