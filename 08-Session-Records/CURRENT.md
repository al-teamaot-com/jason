# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-08
**Purpose:** Canonical human-readable resume point for a future Jason work session. This file records intent and next actions; host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

The 2026-08-08 provider/infrastructure foundation integration workstream is complete on `main`.

Merged in dependency order:

1. PR #72 — **INF-010 Microsoft Cloud platform foundation**
2. PR #73 — **INF-011 Kaseya resource platform foundation**
3. PR #74 — **INF-012 Cross-provider relationship foundation**
4. PR #75 — **INF-013 Artifact/evidence storage foundation**

The canonical roadmap now controls the next primary workstream: **J-119 Event Model**.

Do not return to the former PR #72-#75 integration queue. Do not restart from ORCH-005 unless a current roadmap or governance decision explicitly reactivates it.

## What Was Already Proven

- Jason Kernel foundation is complete.
- Central Orchestrator ORCH-001 through ORCH-004 are complete.
- OpenBao INF-001, INF-002, and INF-003 are complete in the roadmap.
- INF-010 Microsoft Cloud provider-family foundation is integrated.
- INF-011 provider-neutral Kaseya/Datto resource gateway foundation is integrated.
- INF-012 governed cross-provider relationship foundation is integrated.
- INF-013 provider-neutral artifact/evidence reference boundary is integrated.
- CAP-001 canonical Autotask read capability is complete.
- CAP-003 Autotask Business Context is live-validated and converged; CAP-002 is retired/superseded.
- Jason Command Center, Prometheus, Grafana, Ollama, OpenBao, and OpenClaw were healthy in the most recent host snapshot.
- OpenBao recovery fingerprint, bootstrap retirement, and governed Raft restore evidence exist outside the repository.

## Current Primary Workstream

### J-119 Event Model

Build the next canonical Jason's World model using the same rule as J-116 through J-120: **model the business, not the software**.

The Event Model must be provider-neutral and authoritative enough to become a dependency for orchestration, evidence, relationships, operational memory, and future automation. It must not collapse provider webhooks, logs, tickets, alerts, audit records, or orchestration lifecycle records into one vendor-shaped structure.

Initial work should establish:

- what constitutes a canonical Jason event versus source evidence about an event;
- immutable event identity and organization/client boundary;
- actor/principal, subject/object, relationship, and capability context;
- occurrence time versus observation/ingestion time;
- source/provenance and correlation/causation semantics;
- classification and lifecycle/state-change semantics without granting execution authority;
- links to J-116 State Model, J-117 Object Model, J-118 Relationship Model, and J-120 Organizational Model;
- compatibility with the existing durable orchestration event store without making the orchestration store the canonical business model;
- compatibility with INF-013 artifact/evidence references so large payloads remain by reference.

## Queued Implementation Follow-ons

These are deliberately secondary to the canonical Event Model unless a governance decision reprioritizes them:

1. **INF-010 deployment:** governed OpenBao certificate binding and controlled Microsoft test-tenant onboarding.
2. **INF-011 convergence:** bring IT Glue and Datto RMM adapters behind the generic resource gateway before adding additional Kaseya/security-provider adapters.
3. **INF-012 binding:** connect provider resource evidence to canonical relationship evaluation/promotion through the Central Orchestrator.
4. **INF-013 physical store:** bind the first approved physical artifact/evidence store through the capability registry.

These follow-ons must preserve integrate-before-innovate and must not create parallel provider-specific architecture when an existing platform or generic capability can satisfy the requirement.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. This is a historical operational loose end, not the current primary development workstream. Do not overwrite an existing `generate-root` setting without first inspecting the live configuration and reconciling it against the governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, the current GitHub state, and a fresh `tools/catch_me_up.py` host snapshot together as the authoritative resume context.
- Reconcile conflicts between this checkpoint and live GitHub/host state before making destructive or security-sensitive changes.
- Preserve the core rule: agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, or secret values in chat, repository content, logs, or evidence.
