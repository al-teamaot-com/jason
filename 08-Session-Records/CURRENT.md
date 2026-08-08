# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-08
**Purpose:** Canonical human-readable resume point for a future Jason work session. This file records intent and next actions; host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

The core 2026-08-08 architecture/runtime work now includes:

1. PR #72 — INF-010 Microsoft Cloud platform foundation — merged
2. PR #73 — INF-011 Kaseya resource platform foundation — merged
3. PR #74 — INF-012 Cross-provider relationship foundation — merged
4. PR #75 — INF-013 Artifact/evidence storage foundation — merged
5. PR #76 — J-119 Event Model — approved and merged
6. PR #78 — INF-014 OpenClaw production ingress and governance gates — merged
7. PR #79 — JKD-001 Identity and Authority runtime foundation — merged
8. PR #80 — durable/revocable JKD-001 authority enforcement and OpenClaw context handoff — merged

PR #77 remains the IT Glue + Datto RMM convergence branch at the live-provider credential boundary. Do not invent provider payload schemas or placeholder secrets while those credentials are unavailable.

## What Is Proven

- Central Orchestrator remains the sole execution coordinator; no agent-to-agent/provider-to-provider coordination path was introduced.
- OpenClaw is an ingress client only and can request registered named capabilities only.
- OpenClaw production ingress supports Ed25519 signed-request authentication, freshness/expiry/nonce validation, replay protection, deterministic governance gates, and pre-orchestration security audit.
- JKD-001 now provides executable identity, scoped authority grants, formal approvals, short-lived execution contexts, durable pilot state, decision audit, exact context validation, and explicit revocation.
- Production-mode Central Orchestrator composition can require a valid JKD-001 execution context before capability resolution/provider selection.
- OpenClaw can dispatch only with an execution context actually issued by JKD-001; caller-supplied authentication or booleans do not substitute for authority.
- J-116 through J-120 canonical foundation models are approved.
- INF-010 through INF-014 foundations are integrated.
- CAP-001 canonical Autotask read capability is complete.
- CAP-003 Autotask Business Context is live-validated and converged; CAP-002 is retired/superseded.

## Current Primary Workstream

### Authority + OpenClaw Host Deployment Preparation

The next safe host-side step requires no provider API credentials and no OpenClaw private key.

Repository tooling prepares:

- `/var/lib/jason/authority` — owner-only JKD-001 state;
- `/var/lib/jason/openclaw` — owner-only OpenClaw replay/security-audit state;
- `/var/lib/jason/authority/authority.sqlite3` — durable pilot authority database;
- governed `tools/identity_authority_admin.py` lifecycle commands;
- `tools/prepare_authority_openclaw_host.sh` — structured host preparation with no network calls, secret resolution, or key generation.

Do not generate the OpenClaw signing private key until the actual OpenClaw runtime location is confirmed. The private signing key belongs with OpenClaw; Jason should register only the corresponding public key.

## Parallel Blocked Workstream

### IT Glue + Datto RMM Resource Convergence — PR #77

The code has reached the live credential boundary.

Needed later:

- IT Glue logical secret `it_glue.readonly` with dedicated read-only `api_key`;
- Datto RMM logical secret `datto_rmm.readonly` with durable `api_url`, `api_key`, and `api_secret`;
- Datto bearer access token remains runtime-only and must never be persisted as the durable credential.

After credentials exist, run exactly one bounded IT Glue configuration GET and one bounded Datto device search, sanitize response-shape inspection, then finalize normalization and INF-012 matching.

## Immediate Next Actions

1. merge the authority/OpenClaw host-deployment-prep branch after CI and constitutional review;
2. update the Jason host to current `main`;
3. run `tools/prepare_authority_openclaw_host.sh` and verify structured PASS output;
4. confirm where the OpenClaw runtime actually executes;
5. generate/provision the dedicated Ed25519 machine identity on that runtime, registering only its public key with Jason;
6. deploy an enforced (`require_authority_context=True`) synthetic OpenClaw → JKD-001 → governance gates → Central Orchestrator path;
7. perform the signed no-provider end-to-end test before enabling any live provider capability through OpenClaw.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. This remains a historical operational loose end, not the current primary workstream. Do not overwrite an existing `generate-root` setting without first inspecting the live configuration and reconciling it against governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh `tools/catch_me_up.py` host snapshot together as the authoritative resume context.
- Reconcile conflicts between this checkpoint and live GitHub/host state before destructive or security-sensitive changes.
- Preserve the core rule: agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, private signing keys, or secret values in chat, repository content, logs, or evidence.
