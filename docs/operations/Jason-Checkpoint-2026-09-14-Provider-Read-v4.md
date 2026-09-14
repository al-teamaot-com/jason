# Jason Stabilization Checkpoint — 2026-09-14 — Provider Read v4

## Purpose

This checkpoint records the first production state in which Jason has proven governed read-only access to Datto RMM, IT Glue, Autotask, and Microsoft Entra while preserving the Central Orchestrator, information-release authorization, provider write prohibition, rollback assets, and production health monitoring.

It is intended to be the rollback/reference point before further nontrivial production changes. This is not a request to freeze the project indefinitely; it is a deliberate stopping point so future work starts from a known, recoverable state rather than from an accumulation of incidental changes.

## Accepted production level

### Jason execution and governance

- live MCP container: `jason-mcp-pilot`;
- accepted MCP image: `jason-mcp:autotask-entra-67da8d80ca97-repaired`;
- accepted MCP source revision: `67da8d80ca9703505d651e9e0935f5bd1aa7c651`;
- provider profile: `itglue-autotask-entra-governed-catalog-v4`;
- mode: read-only;
- Central Orchestrator: active;
- direct provider access: disabled;
- provider write tools: disabled;
- Autotask requester mode: `jason_managed` as an approved transitional control;
- IT Glue requester authorization: approved transitional Jason-managed path with information-release controls preserved.

### Live governed provider milestone

The following provider paths have live production acceptance evidence:

- Datto RMM governed read;
- IT Glue governed read/search with broad unscoped disclosure failing closed;
- Autotask governed read/search/count, including human status-label resolution for `New`;
- Microsoft Graph / Entra exact user search and exact user read.

The production authority added 23 observe-only grants for the v4 rollout: 10 IT Glue, 11 Autotask, and 2 Microsoft Graph capabilities. Existing Datto RMM observe authority remains in place. No provider write grant was added.

## Production health acceptance

The `Jason Production Health` observability stack is deployed and accepted.

Current accepted observations:

- `jason-runtime`: running and Docker-healthy;
- `jason-mcp-pilot`: running;
- OpenBao: running, initialized, and unsealed;
- required MCP credential-mount contract: pass;
- current-boot kernel corruption/error signature count: `0`;
- failed systemd unit count: `0`;
- root filesystem host-namespace writable metric: `1`;
- pre-v4 MCP rollback container: present;
- exporter version: `2`;
- Prometheus production-health target: UP;
- Grafana dashboard UID: `jason-production-health`.

Exporter version 2 corrects the original root-filesystem namespace false positive while preserving systemd `ProtectSystem=strict` hardening.

## Known accepted exception

The live MCP contains duplicate Docker environment entries for:

- `JASON_SOURCE_REVISION`;
- `JASON_PROVIDER_READ_ACTIVATION_PROFILE`;
- `JASON_AUTOTASK_REQUESTER_AUTH_MODE`.

The accepted effective image/source/profile/requester-mode checks all pass, and live v4 capabilities are working. This is configuration ambiguity, not a demonstrated outage. `JasonMCPDuplicateEnvironment` is expected to fire until issue #180 is deliberately corrected.

Do not recreate the MCP merely to make this warning disappear. Correct it only as a controlled change with a current-state rollback checkpoint and post-change live provider validation.

## Real-world product gaps discovered after acceptance

The following are known backlog items, not reasons to destabilize the accepted production baseline:

- issue #178 — resolve provider foreign keys into user-relevant business values; first observed when an Autotask ticket assignment returned a resource ID rather than a technician name;
- issue #179 — add governed Microsoft tenant-wide read resource families such as tenant identity, domains, licensing, Conditional Access, and appropriate Exchange configuration;
- issue #180 — remove duplicate production MCP environment entries in a controlled recreation;
- issue #181 — add low-cadence governed provider health canaries without bypassing Jason governance.

The user-relevant output and capability-aware answer principles are documented separately and apply to future provider work.

## Existing rollback assets

### Pre-v4 rollback

- container: `jason-mcp-pilot-pre-v4-20260914T085704`;
- image: `jason-mcp:ticket-read-e91d5925290b`;
- pre-v4 authority backup: `/var/lib/jason/authority/authority-pre-v4-20260914T085704.sqlite3`.

The authority backup passed SQLite integrity validation when created.

### OpenBao recovery

Canonical non-secret recovery documentation:

- `docs/operations/Jason-OpenBao-Initialization-and-Recovery-Record.md`.

Protected initialization material must remain outside Git, dashboards, Prometheus labels, and chat.

### Monitoring rollback

The production-health deployment created a rollback backup directory at:

- `/tmp/jason-production-health-rollback-20260914T134502Z`.

The exporter-v1 systemd unit was also backed up before the exporter-v2 correction. The v2 correction changed only the production-health exporter service; runtime, MCP, OpenBao, Prometheus, and Grafana container identities remained unchanged.

## Current-level checkpoint requirement

Before the next nontrivial production change, create a current-level local checkpoint containing at minimum:

1. an online SQLite backup of the current authority database with integrity verification;
2. a stable local tag/reference to the accepted MCP image ID;
3. a secret-safe production contract snapshot covering image/source/profile/network/port/restart policy, mount destinations, OpenBao readiness, and current monitoring state;
4. SHA-256 hashes for the checkpoint files;
5. the GitHub documentation revision identifying this accepted state.

Do not copy OpenBao unseal shares, provider credentials, OAuth tokens, AppRole values, API keys, raw MCP environment contents, or raw provider records into the checkpoint.

## Change discipline from this checkpoint

This checkpoint establishes the following working rule:

**Do not make changes simply because a cleanup or enhancement is available.**

Proceed when a change is justified by one of these conditions:

- a real-world test exposes a material usability/correctness problem;
- monitoring identifies an operational or reliability risk;
- a security/governance control requires correction;
- an explicitly prioritized capability is next on the roadmap;
- a dependency or recovery concern makes the current state unsafe to leave unchanged.

Otherwise preserve the accepted baseline and continue real-world testing.

## GitHub/change-control state

PR #174 remains draft/open/unmerged. This checkpoint does not authorize merging it, enabling provider writes, weakening information-release authorization, weakening tenant/client boundaries, bypassing the Central Orchestrator, or deleting rollback/recovery assets.
