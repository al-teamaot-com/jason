# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-08
**Purpose:** Canonical human-readable resume point for a future Jason work session. Host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

The 2026-08-08 architecture/runtime sequence now includes merged PRs #72–#76 and #78–#89, covering INF-010 through INF-014, J-119, JKD-001 runtime/durability, OpenClaw production ingress/governance, machine trust, governed human delegation, operational hardening, key lifecycle tooling, AWS TODO capture, and deployed operational-health evidence.

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
- One historical synthetic delegation is elapsed but remained stored as `active`; the production-maintenance package is designed to normalize such records to `expired` without deleting audit history.

Host proof evidence is recorded in `08-Session-Records/OpenClaw-Delegated-Human-Host-Proof-2026-08-08.md`.

## Current Primary Workstream

### Production Packaging + Observability

Branch `agent/openclaw-production-packaging-monitoring` packages the proven boundary for repeatable operations without adding provider authority.

The workstream adds:

1. hourly `jason-delegation-maintenance.timer` to normalize elapsed active delegations while preserving history/audit;
2. five-minute `jason-openclaw-authority-health.timer` to write an atomic mode-0600 secret-safe health snapshot;
3. `tools/install_openclaw_authority_operations.sh` for repeatable systemd installation and first-run validation;
4. Command Center metrics for OpenClaw/JKD-001 health, trusted-key count, delegation lifecycle, backup/restore proof, and snapshot age;
5. Grafana dashboard `Jason OpenClaw / JKD-001 Operations`;
6. CatchMeUp integration for deployed unit state and sanitized operational-health summaries;
7. CI for systemd syntax, shell packaging, status-exporter metrics, and CatchMeUp rendering;
8. operational health fails closed when the trusted-key registry is missing, non-owner-only, or has zero active signing keys.

No provider credential is resolved and no provider call is performed by this packaging workstream.

## Next Trust Milestone

After the production-packaging host proof, perform an **overlap-first Ed25519 signing-key rotation proof**:

1. generate a second private key only inside the OpenClaw persistent secret boundary;
2. register its public key under a new key ID;
3. prove both old and new signed synthetic requests authenticate during overlap;
4. use the new private key for the synthetic signing proof;
5. revoke the old public-key record;
6. prove new-key success and old-key fail-closed behavior;
7. retain non-secret rotation evidence; do not delete the old private key until cutover/revocation is proven.

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

1. validate/merge production operations packaging;
2. install the operations package on Jason and verify both timers, the `0600` health snapshot, delegation normalization, CatchMeUp output, and Command Center metrics;
3. perform overlap-first OpenClaw signing-key rotation proof;
4. record host evidence and update CatchMeUp/CURRENT;
5. begin the AWS provider-family foundation once the OpenClaw/Jason production trust boundary is stable;
6. return to PR #77 when approved IT Glue/Datto credentials exist.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. Do not overwrite an existing `generate-root` setting without first inspecting live configuration and governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh CatchMeUp host snapshot together as authoritative resume context.
- Reconcile conflicts between checkpoint/GitHub/host state before destructive or security-sensitive changes.
- Agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, private signing keys, or secret values in chat, repository content, logs, or evidence.
