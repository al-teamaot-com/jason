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
15. PR #87 — OpenClaw + JKD-001 operational hardening — merged
16. PR #88 — trusted-key lifecycle CLI regression fix and AWS provider-family TODO — merged

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
- Operational-health validation passed on the deployed host after PR #88: authority/replay/security-audit/orchestration-audit SQLite integrity all returned `ok`; trusted-key registry contained one active OpenClaw public-key record; all security-sensitive state and registry files were mode `0600`.
- Ephemeral online SQLite backup -> restore proof passed with both backup and restore mode `0600`, integrity `ok`, and authority object counts matching live state.
- Operational-health validation reported no provider contact and no provider credentials used.
- The synthetic delegation record is expired by time but still retains `status=active`; maintenance should normalize this historical record to `expired` without deleting audit history.

Host proof evidence is recorded in `08-Session-Records/OpenClaw-Delegated-Human-Host-Proof-2026-08-08.md`.

## Current Primary Workstream

### Production Packaging + OpenClaw Trust Operations

Operational health is now proven on the live Jason host. Remaining no-provider work:

1. integrate periodic delegation lifecycle maintenance so elapsed active records are normalized to `expired` without deleting history;
2. package the production OpenClaw/Jason ingress composition as a repeatable service with explicit health/readiness behavior and owner-only state paths;
3. integrate operational-health signals into the existing Jason observability/Command Center path;
4. perform an overlap-first OpenClaw Ed25519 signing-key rotation proof: add new key, validate both keys, move signing to the new private key inside OpenClaw, prove continuity, then revoke the old public key;
5. update CatchMeUp to report machine trust, active/revoked key count, delegation-state health, security-state modes, and backup/restore readiness.

Do not enable real human delegation to provider-backed capabilities until the relevant capability/provider authorization model has been explicitly reviewed and the production packaging/trust-rotation controls above are complete.

## Parallel / Future Provider Workstreams

### IT Glue + Datto RMM Resource Convergence — PR #77

The code has reached the live credential boundary.

Needed later:

- IT Glue logical secret `it_glue.readonly` with dedicated `api_key`; provider-level method restrictions may be limited, so Jason's observe/GET-only boundary remains important;
- Datto RMM logical secret `datto_rmm.readonly` with durable `api_url`, `api_key`, and `api_secret`;
- Datto bearer access token remains runtime-only and must never be persisted as the durable credential.

Before live Datto use, re-verify the exact current OAuth token endpoint/request contract against official Datto documentation. Then run exactly one bounded IT Glue configuration GET and one bounded Datto device search, sanitize response-shape inspection, and finalize normalization/INF-012 matching.

### AWS Connection — TODO

Add AWS as a governed provider family rather than as direct ad hoc SDK access.

Initial design/implementation should include:

- provider-neutral AWS resource family registration and named capabilities;
- identity-first authorization and organization/account/region scoping;
- least-privilege, preferably read-only initial credentials/roles;
- OpenBao-backed durable credential or role-assumption configuration with no long-lived access key exposure in Git/chat/logs;
- STS/session credentials treated as runtime-only material;
- Central Orchestrator-only invocation, with no direct OpenClaw/agent -> AWS path;
- audit/evidence events for AWS reads and any later mutations;
- controlled synthetic/test-account validation before any production account access;
- explicit review of Organizations, IAM, CloudTrail, Config, Security Hub, GuardDuty, EC2, S3, RDS, Backup, and Systems Manager capabilities before expanding scope.

Use "integrate before innovate": prefer AWS-native identity, audit, inventory, configuration, and security services over custom replacements.

## Immediate Next Actions

1. package production OpenClaw/Jason ingress and authority composition with repeatable health/readiness checks;
2. wire periodic delegation expiration maintenance and preserve full lifecycle history;
3. integrate operational-health state into CatchMeUp and Jason Command Center telemetry;
4. perform overlap-first OpenClaw signing-key rotation and old-key revocation proof;
5. record the production-packaging and key-rotation host evidence;
6. design AWS provider-family foundation after the OpenClaw/Jason production boundary is stable;
7. return to PR #77 when approved IT Glue/Datto credentials exist.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. This remains a historical operational loose end, not the current primary workstream. Do not overwrite an existing `generate-root` setting without first inspecting the live configuration and reconciling it against governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh `tools/catch_me_up.py` host snapshot together as the authoritative resume context.
- Reconcile conflicts between this checkpoint and live GitHub/host state before destructive or security-sensitive changes.
- Preserve the core rule: agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, private signing keys, or secret values in chat, repository content, logs, or evidence.
