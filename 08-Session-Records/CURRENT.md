# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-09
**Purpose:** Canonical human-readable resume point for a future Jason work session. Host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

The architecture/runtime sequence now includes merged PRs #72–#76 and #78–#92, covering INF-010 through INF-014, J-119, JKD-001 runtime/durability, OpenClaw production ingress/governance, machine trust, governed human delegation, operational hardening, key lifecycle tooling, production operations/observability, and the first governed overlap-first Ed25519 signing-key rotation.

PR #77 remains the IT Glue + Datto RMM convergence branch at the live-provider credential boundary. Do not invent provider payload schemas or placeholder secrets while those credentials are unavailable.

## What Is Proven On The Jason Host

- OpenClaw runs in Docker as `openclaw-openclaw-gateway-1`, user `node` UID/GID 1000.
- OpenClaw persistent secret/config mounts are under `/opt/jason/services/openclaw/data/`.
- OpenClaw machine trust uses Ed25519 application-layer signatures. Private keys remain only inside the OpenClaw persistent auth-profile secret boundary; Jason stores only public keys and pinned fingerprints.
- Jason verified real signed OpenClaw requests and rejected tampering.
- OpenClaw is ingress/transport only; the Central Orchestrator remains the sole execution coordinator.
- JKD-001 provides scoped identity/authority, formal approvals, short-lived contexts, revocation, durable delegation, and authority audit.
- The direct machine-service path completed through signature -> JKD-001 -> governance -> Central Orchestrator -> synthetic capability, and replay was rejected.
- The delegated-human path kept the human principal distinct from `svc-openclaw-gateway`, evaluated the human's own observe authority, validated explicit delegation, completed through governance/orchestration, and failed closed after delegation revocation.
- Production operations packaging from PR #90 is deployed on Jason.
- `jason-delegation-maintenance.timer` is active and automatically normalized the historical elapsed synthetic delegation to `expired` while preserving history.
- `jason-openclaw-authority-health.timer` is active and writes `/var/lib/jason/openclaw/operational-health.json` with mode `0600`.
- Command Center Prometheus metrics for OpenClaw/JKD-001 operational health are live.
- CatchMeUp reports the production operations timers and sanitized OpenClaw/JKD-001 operational-health state.
- Operational health after signing-key cutover passed: all security-state SQLite integrity checks `ok`, backup/restore proof passed, restored counts matched, zero expired-active delegation records remained, one active trusted signing key remained, and no provider contact/credential use occurred.

## OpenClaw Signing-Key Rotation — Proven

The first overlap-first production rotation from `openclaw-gateway-1` to `openclaw-gateway-2` completed successfully.

- Both keys were active and cryptographically accepted during overlap.
- Key #2 completed a full governed synthetic execution through OpenClaw ingress, JKD-001, governance, and the Central Orchestrator.
- Replay protection remained active.
- Only after key #2 continuity was proven was key #1's Jason public-trust record revoked.
- Post-revocation proof rejected key #1 and continued to accept key #2.
- Final registry state: `openclaw-gateway-2` active; `openclaw-gateway-1` revoked.
- Replacement public-key fingerprint: `fb6612b03009b2cecca812458ac35c75fd3d4f23efa29ed631e905ff03d235b7`.
- Replacement public key: `/var/lib/jason/openclaw/trusted-keys/openclaw-jason-ed25519-v2.pub.pem`.
- Replacement private key remains only inside OpenClaw at `/home/node/.config/openclaw/jason-ingress/openclaw-jason-ed25519-v2.pem`.
- The old private key remains only inside the OpenClaw secret boundary for the governed rollback/retention window; Jason no longer accepts it.

Host evidence:

- `08-Session-Records/OpenClaw-Delegated-Human-Host-Proof-2026-08-08.md`
- `08-Session-Records/OpenClaw-Ed25519-Key-Rotation-Host-Proof-2026-08-09.md`

## Current Primary Workstream

### AWS Provider-Family Foundation

The OpenClaw/Jason production trust boundary has now completed machine trust, delegated-human proof, operational packaging, monitoring, backup/restore proof, lifecycle automation, and signing-key rotation. The next independent no-IT-Glue/Datto-key workstream is the AWS provider-family foundation.

AWS must be added as a governed provider family, not ad hoc SDK access. Initial design must include:

1. provider-neutral AWS resource and capability contracts;
2. identity-first organization/account/region scope;
3. least-privilege/read-only roles for the first live validation;
4. OpenBao-backed durable role/configuration and runtime-only STS credentials;
5. Central-Orchestrator-only provider access;
6. normalized provider responses with no raw secret persistence;
7. audit/evidence for account, region, capability, authority context, provider request, and sanitized outcome;
8. controlled test-account validation before broader use;
9. an AWS service catalog review covering Organizations, IAM, CloudTrail, Config, Security Hub, GuardDuty, EC2, S3, RDS, Backup, and Systems Manager;
10. integrate-before-innovate: prefer AWS-native identity, audit, inventory, configuration, security, and automation capabilities over custom replacements.

No AWS credential should be placed into Git, chat, ordinary logs, or static application configuration. Live AWS work begins only after the credential/role boundary is explicitly provisioned through Jason's secret and authority model.

## Parallel / Blocked Provider Workstream

### IT Glue + Datto RMM — PR #77

Blocked only on approved credentials:

- IT Glue logical secret `it_glue.readonly` with dedicated `api_key`.
- Datto RMM logical secret `datto_rmm.readonly` with durable `api_url`, `api_key`, `api_secret`; bearer access token remains runtime-only.
- Before live Datto use, re-verify the current OAuth token endpoint/request contract against official vendor documentation.

## Immediate Next Actions

1. record/merge the successful signing-key rotation evidence and exact public-key location correction;
2. begin the AWS provider-family foundation as a separate governed branch/PR;
3. define AWS account/region/resource normalization, capabilities, identity/authority scope, and credential binding without requiring a live AWS credential;
4. build credential-safe AWS preflight and synthetic tests up to the live-credential boundary;
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
