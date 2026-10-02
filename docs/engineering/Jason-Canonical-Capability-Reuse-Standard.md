# J-CAP-001 — Canonical Capability Reuse Standard

**Version:** 1.0  
**Status:** Non-production implementation / enforcement pilot  
**Owner:** Jason Architecture Authority  
**Authority:** Jason Constitution; ADR-0008 Central Capability Registry; Jason Capability Catalog; Central Orchestrator  
**Scope:** All Project Jason processes, playbooks, interfaces, scheduled workers, maintenance jobs, support-repair workflows, and future agents

## 1. Section Goal

**Goal:** Ensure that the same Jason operation behaves the same regardless of which process calls it.

**Success means:**
- processes/playbooks contain decision logic, not duplicated provider plumbing;
- canonical capability identity is owned by the Kernel;
- governance and execution-plan binding remain centralized;
- provider-specific API/transport behavior remains behind registered provider boundaries;
- a new caller can reuse an existing operation without creating another implementation;
- CI prevents new workflow/process code from introducing direct provider plumbing where a canonical capability should be used.

## 2. Trigger

This standard applies whenever new or modified Jason code needs to read, create, update, execute, notify, deploy, verify, or otherwise act on an operational resource.

## 3. Scope and Boundaries

The standard applies equally to:
- autonomous playbooks;
- technician-triggered requests;
- Teams workflows;
- scheduled reconciliation;
- Support List repair;
- Release Manager;
- procurement;
- OpenClaw/ChatGPT interfaces;
- future local-model or dashboard callers.

Provider implementation modules remain permitted to contain provider-specific code because they are the replaceable implementation behind the capability boundary.

## 4. Core Architectural Rule

> A process may decide **when and why** an operation occurs, but it must not reimplement **how** the operation is performed when Jason already has a canonical capability for that operation.

The required flow is:

`caller -> canonical capability -> Central Orchestrator/governance -> provider implementation -> authoritative verification`

The caller must not depend on whether the current provider is Autotask, Datto, IT Glue, Microsoft Graph, Teams, DNSFilter, KFS, or a future replacement.

## 5. Ownership of Meaning

- **Caller/process:** desired outcome, domain decision, target facts.
- **Kernel Capability Registry:** stable operation identity and contract.
- **Central Orchestrator/governance:** identity, authority, scope, plan binding, retry/timeout/evidence behavior.
- **Provider registry/adapter/invoker:** concrete provider translation and transport.
- **Verification source:** evidence that the intended state actually occurred.

Provider modules may implement a capability; they may not redefine the capability's business meaning.

## 6. Reuse Before Creation Gate

Before adding provider-facing behavior, the developer/process must:
1. search the canonical capability inventory/registry;
2. use an existing canonical capability when its contract covers the intended operation;
3. extend the existing contract only when the operation is semantically the same and compatibility is preserved;
4. propose a new canonical capability only when the operation is materially distinct;
5. never create a workflow-local provider action merely because doing so is faster.

## 7. Caller Boundary

Workflow/process callers must not add:
- imports from provider connector packages;
- direct provider HTTP clients or raw network transport;
- provider authentication/token handling;
- provider-specific retry logic;
- provider-specific authorization decisions;
- provider-specific success assumptions;
- duplicate mutation/readback implementations.

A caller may:
- request a canonical capability;
- interpret its normalized result;
- make domain-specific decisions from authoritative evidence;
- choose the next canonical capability;
- persist workflow state;
- document the resulting decision.

## 8. Provider Boundary

Provider-specific modules may contain:
- endpoint/path construction;
- provider schema translation;
- authentication handoff from approved secret mechanisms;
- provider-native requester impersonation;
- bounded provider retries when explicitly part of the provider contract;
- provider response normalization;
- post-action provider readback.

These modules remain subordinate to Central Orchestrator and do not grant authority.

## 9. Shared Runtime Rule

Common workflow mechanics belong in the shared runtime:
- ownership/work-start;
- identity association;
- persisted state;
- retry accounting;
- waiting/recheck;
- duplicate suppression;
- documentation;
- human handoff;
- terminal readback;
- common observability.

Individual playbooks should primarily express trigger, expected state, evidence questions, classification, domain-specific decision gates, remediation choice, and verification criteria.

## 10. Migration Strategy

This is a ratchet, not a flag-day rewrite.

1. New code must follow the standard immediately.
2. Modified legacy caller code is checked for new direct provider plumbing.
3. Existing legacy paths are cataloged as migration debt.
4. Migrate one caller/family at a time to canonical capabilities.
5. Prove equivalent behavior before removing the legacy path.
6. Delete redundant provider logic after successful acceptance.
7. Do not maintain two permanent ways to perform the same operation.

## 11. Structural CI Enforcement

`tools/canonical_capability_boundary_gate.py` inspects changed workflow/process caller files.

It fails when a caller introduces:
- direct connector imports;
- direct HTTP provider transports;
- other configured provider-boundary violations.

The gate intentionally does not fail the repository for historical untouched code. That allows safe incremental convergence while preventing architecture from getting worse.

## 12. Initial Machine-Readable Inventory

`config/canonical-capability-inventory.json` records major current capability families and their caller rule.

The Kernel Capability Registry and source-controlled capability catalogs remain authoritative. The inventory is a coordination/reuse view, not a second source of execution authority.

## 13. Acceptance Tests

The initial enforcement suite proves:
1. workflow caller importing a connector fails;
2. workflow caller issuing direct HTTP fails;
3. canonical action invocation is allowed;
4. provider implementation modules remain allowed to use provider plumbing;
5. analysis/workflow/worker/maintenance/flow callers are covered by the ratchet;
6. production provider authority is unchanged.

## 14. Current Reference Behavior

The existing autonomy worker already demonstrates the desired caller style: it requests canonical names such as `service.ticket.note.create` through its governed action executor rather than implementing the Autotask TicketNote API inside the playbook decision path.

That pattern should become universal.

## 15. Production Boundary

This workstream is source/CI architecture only. It does not:
- activate a new provider capability;
- change production permissions;
- deploy production;
- bypass approval;
- change `direct_provider_access=false`.

Production migration of individual legacy callers requires its own normal release and acceptance evidence.

## 16. Section Goal Closure

The non-production foundation is complete when:
- the standard, inventory, and CI ratchet exist;
- protected validation passes;
- at least one real caller family is confirmed to follow the canonical pattern;
- remaining legacy paths can be enumerated and migrated incrementally.

Future work should add a generated registry view so capability inventory is derived automatically from the Kernel catalog instead of manually maintained.
