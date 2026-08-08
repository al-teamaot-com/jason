# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-08
**Purpose:** Canonical human-readable resume point for a future Jason work session. This file records intent and next actions; host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

Jason has moved beyond the earlier ORCH-005 recovery-eligibility pause. The immediate integration focus is the four open, mergeable draft foundations created on 2026-08-08:

1. PR #72 — **INF-010 Microsoft Cloud platform foundation** (`feature/microsoft-cloud-platform-foundation`)
2. PR #73 — **INF-011 Kaseya resource platform foundation** (`feature/kaseya-resource-platform-foundation`)
3. PR #74 — **INF-012 Cross-provider relationship foundation** (`feature/cross-provider-relationship-foundation`)
4. PR #75 — **INF-013 Artifact/evidence storage foundation** (`feature/artifact-evidence-storage-foundation`)

Treat these as the active validation/integration queue. Do not restart from ORCH-005 unless a current roadmap or governance decision explicitly returns it to active work.

## What Was Already Proven

- Jason Kernel foundation is complete.
- Central Orchestrator ORCH-001 through ORCH-004 are complete.
- OpenBao INF-001, INF-002, and INF-003 are complete in the roadmap.
- CAP-001 canonical Autotask read capability is complete.
- CAP-003 Autotask Business Context is live-validated and converged; CAP-002 is retired/superseded.
- Jason Command Center, Prometheus, Grafana, Ollama, OpenBao, and OpenClaw were healthy in the most recent host snapshot.
- OpenBao recovery fingerprint, bootstrap retirement, and governed Raft restore evidence exist outside the repository.

## Current Validation / Integration Order

The preferred order is dependency-aware rather than chronological:

1. Validate PR #72 independently: Microsoft connector tests, `tools/microsoft_cloud_foundation_check.py`, connector suite, Kernel, release validation, strict docs.
2. Validate PR #73: resource-gateway tests plus complete connector/Kernel/release/docs validation.
3. Validate PR #74 after #73 because its relationship model is intended to bind to the generic resource gateway.
4. Validate PR #75 after the preceding provider/resource boundaries because it establishes the central artifact/evidence reference contract those capabilities will use.
5. Rebase/update branches as required against the then-current `main` before merge; do not merge stale branches solely because GitHub reports them mergeable.
6. After the integration queue is complete, re-evaluate the roadmap and select the next governed capability/workstream.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. This is a historical operational loose end, not the current primary development workstream. Do not overwrite an existing `generate-root` setting without first inspecting the live configuration and reconciling it against the governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, the current GitHub state, and a fresh `tools/catch_me_up.py` host snapshot together as the authoritative resume context.
- Reconcile conflicts between this checkpoint and live GitHub/host state before making destructive or security-sensitive changes.
- Preserve the core rule: agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, or secret values in chat, repository content, logs, or evidence.
