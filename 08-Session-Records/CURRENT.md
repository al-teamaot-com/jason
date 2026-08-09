# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-09
**Purpose:** Canonical human-readable resume point for a future Jason work session. Host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

Project Jason has now completed the first successful governed live Datto RMM read from the production Jason host.

Recent merged work includes the OpenClaw/JKD-001 production trust sequence, AWS provider-family foundation, canonical OpenBao provider-secret AppRole hardening, CAS-aware provider-secret provisioning, Datto RMM AppRole self-revoke correction, and the first bounded Datto RMM live-read path.

The historical draft PR #77 remains open but is no longer the authoritative Datto RMM implementation path. Datto RMM credential provisioning and the first live read have been absorbed into current `main` through PRs #96–#99. PR #77 should be reconciled or retired as remaining IT Glue/cross-provider convergence work is brought current.

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
- Operational health after signing-key cutover passed: all security-state SQLite integrity checks `ok`, backup/restore proof passed, restored counts matched, zero expired-active delegation records remained, one active trusted signing key remained, and no provider contact/credential use occurred during that proof.
- Datto RMM logical secret `datto_rmm.readonly` is stored in OpenBao with durable fields `api_url`, `api_key`, and `api_secret`.
- Datto RMM runtime secret access uses a provider-specific OpenBao AppRole through JKD-003.
- Datto RMM AppRole artifacts are protected as `root:root` mode `0600`.
- No shared persistent provider runtime token is used.
- The Datto AppRole token can read only its provider secret and revoke itself.
- Datto OAuth bearer tokens are acquired at runtime and are not persisted.
- The first live `datto_rmm.device.search` proof succeeded with a maximum of one provider record.
- The first live Datto proof emitted `connector.requested` and `connector.completed` audit events.
- The live proof retained only sanitized count/shape metadata; no raw device record, API credential, bearer token, or provider response body was printed or persisted.

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
- `08-Session-Records/Datto-RMM-First-Live-Read-Host-Proof-2026-08-09.md`

## Current Primary Workstream

### Datto RMM Provider Expansion

Datto RMM is no longer at the credential boundary. The first governed live read is proven. Next work should expand only through registered read-only capabilities and governed resource queries.

Priorities:

1. validate and normalize additional live response shapes for existing registered capabilities;
2. preserve organization/client scoping and bounded pagination;
3. avoid retaining raw provider payloads when sanitized normalized evidence is sufficient;
4. keep OAuth bearer tokens runtime-only;
5. continue emitting connector/audit evidence for each governed provider read;
6. reconcile the Datto portions of historical draft PR #77 with current `main` and retire duplicated/stale implementation where appropriate.

## Parallel Provider Workstreams

### IT Glue

IT Glue remains the next provider needed for the original cross-provider convergence objective.

- logical secret: `it_glue.readonly`;
- durable field: `api_key`;
- runtime identity: provider-specific OpenBao AppRole through JKD-003;
- provision and validate independently before creating any IT Glue <-> Datto relationship evidence.

No cross-provider relationship evidence should be treated as execution authority.

### AWS Provider-Family Foundation

AWS platform foundation is merged. Live AWS work remains at the controlled credential/role boundary:

- use OpenBao-backed durable role/configuration;
- prefer STS AssumeRole with runtime-only credentials;
- begin live validation with STS GetCallerIdentity;
- preserve account/organization/region scope and read-only governance.

## Immediate Next Actions

1. merge the Datto RMM first-live-read host-proof checkpoint update;
2. reconcile or retire the stale Datto portions of draft PR #77;
3. continue bounded DRMM response-shape validation for existing registered capabilities as needed;
4. provision IT Glue through the canonical AppRole secret workflow;
5. validate the first governed IT Glue live read independently;
6. only then resume IT Glue + Datto cross-provider convergence/evidence work.

## Provider Secret Architecture — Canonical Rule

Production provider secrets use provider-specific OpenBao AppRoles through JKD-003.

- provisioning authority is temporary and separate from runtime authority;
- runtime AppRole tokens are short-lived and self-revoked;
- provider runtime policies may read only the specific provider secret plus `auth/token/revoke-self`;
- shared persistent provider runtime tokens are prohibited;
- KV-v2 provider secret writes use compare-and-set semantics;
- future providers must reuse this pattern unless an explicit architecture review approves a replacement.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. Do not overwrite an existing `generate-root` setting without first inspecting live configuration and governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh CatchMeUp host snapshot together as authoritative resume context.
- Reconcile conflicts between checkpoint/GitHub/host state before destructive or security-sensitive changes.
- Agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, private signing keys, or secret values in chat, repository content, logs, or evidence.
