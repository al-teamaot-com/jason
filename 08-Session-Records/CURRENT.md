# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-08
**Purpose:** Canonical human-readable resume point for a future Jason work session. This file records intent and next actions; host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

The 2026-08-08 architecture/runtime sequence now includes:

1. PR #72 — INF-010 Microsoft Cloud platform foundation — merged
2. PR #73 — INF-011 Kaseya resource platform foundation — merged
3. PR #74 — INF-012 Cross-provider relationship foundation — merged
4. PR #75 — INF-013 Artifact/evidence storage foundation — merged
5. PR #76 — J-119 Event Model — approved and merged
6. PR #78 — INF-014 OpenClaw production ingress and governance gates — merged
7. PR #79 — JKD-001 Identity and Authority runtime foundation — merged
8. PR #80 — durable/revocable JKD-001 authority enforcement and OpenClaw context handoff — merged
9. PR #81 — authority/OpenClaw governed host-preparation tooling — merged
10. PR #82 — file-backed trusted OpenClaw public-key registry — merged
11. PR #83 — machine identity binding and signed synthetic OpenClaw -> JKD-001 -> governance -> Central Orchestrator proof tooling — merged
12. PR #84 — replay DB permission hardening and JKD-001 delegation foundation — merged
13. PR #85 — durable governed OpenClaw human delegation — merged
14. PR #86 — delegated-human host proof tooling — merged

PR #77 remains the IT Glue + Datto RMM convergence branch at the live-provider credential boundary. Do not invent provider payload schemas or placeholder secrets while those credentials are unavailable.

## What Is Proven On The Jason Host

- OpenClaw runs in Docker as container `openclaw-openclaw-gateway-1`, user `node` UID/GID 1000.
- OpenClaw persistent secret/config mounts are under `/opt/jason/services/openclaw/data/`.
- Dedicated Ed25519 OpenClaw machine identity exists. The private key remains only under the OpenClaw persistent auth-profile secret boundary; Jason stores only the registered public key and pinned fingerprint.
- Jason authenticated a real signed request from OpenClaw using the file-backed trusted-key registry and rejected a tampered envelope.
- Central Orchestrator remains the sole execution coordinator; no agent-to-agent/provider-to-provider coordination path was introduced.
- OpenClaw is an ingress client only and can request registered named capabilities only.
- OpenClaw production ingress supports Ed25519 signed-request authentication, freshness/expiry/nonce validation, persistent replay protection, deterministic governance gates, pre-orchestration security audit, machine-to-principal binding, and explicit delegation validation.
- JKD-001 provides executable identity, scoped authority grants, formal approvals, short-lived execution contexts, durable pilot state, decision audit, exact context validation, explicit context revocation, and durable delegation records.
- Production Central Orchestrator composition requires a valid JKD-001 execution context before capability resolution/provider selection.
- The direct machine-service synthetic path completed successfully; replay of the same signed envelope was rejected with `replay_detected`.
- The delegated-human host proof completed successfully using synthetic human `synthetic-human-al`, OpenClaw service `svc-openclaw-gateway`, and observe-only capability `jason.synthetic.health`.
- In the delegated proof, the human remained distinct from OpenClaw, the human's own authority grant was evaluated, delegation was validated, governance gates remained in path, and orchestration succeeded.
- After explicit delegation revocation, a fresh signed request was rejected before authority/orchestration execution with `delegation_inactive`.
- `/var/lib/jason/authority/authority.sqlite3`, `/var/lib/jason/openclaw/replay.sqlite3`, `/var/lib/jason/openclaw/security-audit.sqlite3`, and `/var/lib/jason/openclaw/orchestration-events.sqlite3` were all verified at owner-only mode `0600` after the host proof.
- No provider credentials or provider APIs were used in the OpenClaw machine or delegated-human proofs.

Host proof evidence is recorded in `08-Session-Records/OpenClaw-Delegated-Human-Host-Proof-2026-08-08.md`.

## Current Primary Workstream

### OpenClaw + JKD-001 Operational Hardening

The next safe work requires no provider API credentials.

Priorities:

1. delegation lifecycle housekeeping that expires/deactivates stale records without deleting audit history;
2. trusted OpenClaw machine-key rotation and revocation procedure with overlapping-key cutover support;
3. production ingress/state health checks for authority DB, replay DB, security audit, orchestration audit, trusted-key registry, Docker/OpenClaw runtime, and key readability boundaries;
4. backup and restore validation for JKD-001/OpenClaw SQLite state with owner-only permissions preserved;
5. service packaging/runbook improvements so production composition is repeatable and observable;
6. documentation and CatchMeUp integration for the above controls.

Do not enable real human delegation to provider-backed capabilities until the operational controls above are complete and the relevant capability/provider authorization model has been explicitly reviewed.

## Parallel Blocked Workstream

### IT Glue + Datto RMM Resource Convergence — PR #77

The code has reached the live credential boundary.

Needed later:

- IT Glue logical secret `it_glue.readonly` with dedicated `api_key`; provider-level method restrictions may be limited, so Jason's observe/GET-only boundary remains important;
- Datto RMM logical secret `datto_rmm.readonly` with durable `api_url`, `api_key`, and `api_secret`;
- Datto bearer access token remains runtime-only and must never be persisted as the durable credential.

Before live Datto use, re-verify the exact current OAuth token endpoint/request contract against official Datto documentation. Then run exactly one bounded IT Glue configuration GET and one bounded Datto device search, sanitize response-shape inspection, and finalize normalization/INF-012 matching.

## Immediate Next Actions

1. complete and validate the OpenClaw/JKD-001 operational-hardening branch;
2. add delegation expiry/deactivation tooling and tests;
3. add trusted-key rotation/revocation tooling and runbook;
4. add host health/preflight checks for all production ingress and authority state;
5. add owner-permission-preserving SQLite backup/restore proof tooling;
6. update CatchMeUp to report machine trust, authority/delegation store health, security-state modes, and operational-hardening status;
7. run the resulting non-provider host proof and record evidence.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. This remains a historical operational loose end, not the current primary workstream. Do not overwrite an existing `generate-root` setting without first inspecting the live configuration and reconciling it against governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh `tools/catch_me_up.py` host snapshot together as the authoritative resume context.
- Reconcile conflicts between this checkpoint and live GitHub/host state before destructive or security-sensitive changes.
- Preserve the core rule: agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, private signing keys, or secret values in chat, repository content, logs, or evidence.
