# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-09
**Purpose:** Canonical human-readable resume point for a future Jason work session. Host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

The architecture/runtime sequence now includes merged PRs #72–#76 and #78–#90, covering INF-010 through INF-014, J-119, JKD-001 runtime/durability, OpenClaw production ingress/governance, machine trust, governed human delegation, operational hardening, key lifecycle tooling, AWS TODO capture, and deployed production operations/observability.

PR #77 remains the IT Glue + Datto RMM convergence branch at the live-provider credential boundary. Do not invent provider payload schemas or placeholder secrets while those credentials are unavailable.

## What Is Proven On The Jason Host

- OpenClaw runs in Docker as `openclaw-openclaw-gateway-1`, user `node` UID/GID 1000.
- OpenClaw persistent secret/config mounts are under `/opt/jason/services/openclaw/data/`.
- Dedicated Ed25519 OpenClaw machine identity exists. The private key remains only in the OpenClaw persistent auth-profile secret boundary; Jason stores only the public key and pinned fingerprint.
- Jason verified a real signed request from OpenClaw and rejected tampering.
- OpenClaw is ingress/transport only; the Central Orchestrator remains the sole execution coordinator.
- JKD-001 provides scoped identity/authority, formal approvals, short-lived contexts, revocation, durable delegation, and authority audit.
- The direct machine-service path completed through signature -> JKD-001 -> governance -> Central Orchestrator -> synthetic capability, and replay was rejected.
- The delegated-human path kept the human principal distinct from `svc-openclaw-gateway`, evaluated the human's own observe authority, validated explicit delegation, completed through governance/orchestration, and failed closed after delegation revocation.
- Operational-health validation passed: authority/replay/security-audit/orchestration-audit SQLite integrity `ok`, all security-sensitive state and key-registry files mode `0600`, one active OpenClaw public signing key, backup/restore integrity `ok`, restored counts matched live state, and no provider contact/credentials occurred.
- Production operations packaging from PR #90 is deployed on Jason.
- `jason-delegation-maintenance.timer` is active and automatically normalized the historical elapsed synthetic delegation to `expired` while preserving history.
- `jason-openclaw-authority-health.timer` is active and writes `/var/lib/jason/openclaw/operational-health.json` with mode `0600`.
- Operational health snapshot reports zero expired-active delegation records, one active trusted signing key, successful backup/restore proof, and no provider contact or credential use.
- Command Center Prometheus metrics for OpenClaw/JKD-001 operational health are live.
- CatchMeUp reports the production operations timers and sanitized OpenClaw/JKD-001 operational-health state.

Host proof evidence is recorded in `08-Session-Records/OpenClaw-Delegated-Human-Host-Proof-2026-08-08.md`; production-packaging host output is reflected in this checkpoint and CatchMeUp runtime state.

## Current Primary Workstream

### Overlap-First OpenClaw Ed25519 Signing-Key Rotation

Branch `agent/openclaw-ed25519-rotation-proof` prepares the first governed production signing-key rotation proof.

The workstream adds:

1. reusable `tools/openclaw_ed25519_rotation_proof.py` continuity/fail-closed proof tooling;
2. CI tests for rotation-proof invariants;
3. operator runbook `07-Operations/OpenClaw-Ed25519-Key-Rotation.md`;
4. explicit overlap-first stop conditions preventing old-key revocation until replacement-key continuity is proven.

The host proof sequence is:

1. generate key #2 only inside the OpenClaw persistent auth-profile secret boundary;
2. derive/export only key #2 public material to Jason;
3. register key ID `openclaw-gateway-2` while key #1 remains active;
4. prove both key #1 and key #2 authenticate during overlap;
5. prove a governed synthetic request using key #2;
6. revoke only the key #1 public registry record;
7. prove key #1 is rejected and key #2 remains accepted;
8. refresh operational health/CatchMeUp and record non-secret rotation evidence.

No provider credential or provider API is involved in this rotation proof. Rotation does not grant authority or alter JKD-001 grants/delegations.

## Parallel / Future Provider Workstreams

### IT Glue + Datto RMM — PR #77

Blocked only on approved credentials:

- IT Glue logical secret `it_glue.readonly` with dedicated `api_key`.
- Datto RMM logical secret `datto_rmm.readonly` with durable `api_url`, `api_key`, `api_secret`; bearer access token remains runtime-only.
- Before live Datto use, re-verify the current OAuth token endpoint/request contract against official vendor documentation.

### AWS Connection — TODO

AWS must be added as a governed provider family, not ad hoc SDK access. Initial design must include provider-neutral resources/capabilities, identity-first organization/account/region scope, least-privilege/read-only roles, OpenBao-backed durable role/configuration, runtime-only STS credentials, Central-Orchestrator-only access, audit/evidence, and controlled test-account validation. Review Organizations, IAM, CloudTrail, Config, Security Hub, GuardDuty, EC2, S3, RDS, Backup, and Systems Manager before expanding scope.

Use **integrate before innovate**: prefer AWS-native identity, audit, inventory, configuration, and security capabilities over custom replacements.

## Immediate Next Actions

1. validate/merge the overlap-first Ed25519 rotation tooling/runbook;
2. perform the production key #1 -> key #2 overlap rotation proof on Jason;
3. record host rotation evidence and refresh operational health/CatchMeUp;
4. begin the AWS provider-family foundation once the OpenClaw/Jason production trust boundary has completed key-rotation proof;
5. return to PR #77 when approved IT Glue/Datto credentials exist.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. Do not overwrite an existing `generate-root` setting without first inspecting live configuration and governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh CatchMeUp host snapshot together as authoritative resume context.
- Reconcile conflicts between checkpoint/GitHub/host state before destructive or security-sensitive changes.
- Agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, private signing keys, or secret values in chat, repository content, logs, or evidence.
