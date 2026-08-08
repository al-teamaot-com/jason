# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-08
**Purpose:** Canonical human-readable resume point for a future Jason work session. This file records intent and next actions; host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

The 2026-08-08 provider/infrastructure foundation integration workstream is complete on `main`:

1. PR #72 — **INF-010 Microsoft Cloud platform foundation**
2. PR #73 — **INF-011 Kaseya resource platform foundation**
3. PR #74 — **INF-012 Cross-provider relationship foundation**
4. PR #75 — **INF-013 Artifact/evidence storage foundation**

PR #76 advances and approves **J-119 Event Model**, completing the initial canonical-model foundation set alongside J-116, J-117, J-118, and J-120.

Do not return to the former PR #72-#75 integration queue. Do not restart J-119 discovery after PR #76 is merged. ORCH-005 remains paused unless a current governance decision explicitly reactivates it.

## What Is Proven

- Jason Kernel foundation is complete.
- Central Orchestrator ORCH-001 through ORCH-004 are complete.
- OpenBao INF-001, INF-002, and INF-003 are complete in the roadmap.
- INF-010 Microsoft Cloud provider-family foundation is integrated.
- INF-011 provider-neutral Kaseya/Datto resource gateway foundation is integrated.
- INF-012 governed cross-provider relationship foundation is integrated.
- INF-013 provider-neutral artifact/evidence reference boundary is integrated.
- J-116 State Model is approved.
- J-117 Object Model is approved.
- J-118 Relationship Model is approved.
- J-119 Event Model is approved in PR #76 and should be treated as authoritative once merged.
- J-120 Organizational Model is approved.
- CAP-001 canonical Autotask read capability is complete.
- CAP-003 Autotask Business Context is live-validated and converged; CAP-002 is retired/superseded.
- Jason Command Center, Prometheus, Grafana, Ollama, OpenBao, and OpenClaw were healthy in the most recent host snapshot.

## Current Primary Workstream

### Governed IT Glue + Datto RMM Resource Convergence

The next implementation slice should prove the merged foundations working together without introducing provider-specific parallel architecture.

Primary objectives:

1. converge existing IT Glue and Datto RMM read adapters behind the INF-011 generic resource gateway;
2. preserve organization/client scoping and fail closed on ambiguous tenant boundaries;
3. produce provider resource evidence suitable for INF-012 relationship evaluation;
4. route cross-provider relationship evaluation through the Central Orchestrator, never provider-to-provider communication;
5. normalize material occurrences through J-119 only after the source/evidence boundary is satisfied;
6. use INF-013 artifact/evidence references for large supporting payloads;
7. keep the entire first slice read-only;
8. preserve CAP-001/CAP-003 Autotask behavior and generic capability naming.

A successful slice should demonstrate that Jason can answer a bounded cross-provider question such as: **which Datto RMM device corresponds to this IT Glue configuration, and what evidence supports that relationship?**

The answer must preserve source provenance, tenant context, confidence/verification state, canonical resource references, and evidence without granting execution authority.

## J-119 Architecture Decisions

The approved Event Model establishes:

- Request, Decision, Approval, Evidence, and other business concepts remain J-117 objects; J-119 records occurrences involving them.
- Canonical event classes are Observation, Action, State Change, Relationship Change, and Communication.
- Lifecycle progression is represented through J-116 State Change, not a separate event class.
- Event-to-event causation, correction, supersession, duplication, sequence, and containment resolve through J-118 relationships.
- Event verification uses Reported, Inferred, Corroborated, Verified, Disputed, and Rejected.
- Time uncertainty remains explicit; false precision is prohibited.
- ORCH-002 remains orchestration evidence and is promoted only when a material provider-neutral business occurrence is established.
- Deduplication uses governed multi-factor evidence and fails safe when confidence is insufficient.

## Queued Follow-ons

After the IT Glue + Datto RMM convergence slice:

1. **INF-010 deployment:** governed OpenBao certificate binding and controlled Microsoft test-tenant onboarding.
2. **INF-011 expansion:** additional Kaseya/security-provider adapters only where verified APIs exist.
3. **INF-013 physical store:** bind the first approved physical artifact/evidence store through the capability registry.
4. broader INF-012 relationship and J-119 event normalization across providers.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. This remains a historical operational loose end, not the current primary development workstream. Do not overwrite an existing `generate-root` setting without first inspecting the live configuration and reconciling it against governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh `tools/catch_me_up.py` host snapshot together as the authoritative resume context.
- Reconcile conflicts between this checkpoint and live GitHub/host state before destructive or security-sensitive changes.
- Preserve the core rule: agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, or secret values in chat, repository content, logs, or evidence.
