# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-08
**Purpose:** Canonical human-readable resume point for a future Jason work session. This file records intent and next actions; host/runtime facts remain independently verified by `tools/catch_me_up.py`.

## Resume Here

The provider/infrastructure foundation integration workstream is complete on `main`:

1. PR #72 — **INF-010 Microsoft Cloud platform foundation**
2. PR #73 — **INF-011 Kaseya resource platform foundation**
3. PR #74 — **INF-012 Cross-provider relationship foundation**
4. PR #75 — **INF-013 Artifact/evidence storage foundation**
5. PR #76 — **J-119 Event Model**, approved and merged

The active branch is `feature/itglue-datto-resource-convergence` and draft PR #77 carries the first governed IT Glue + Datto RMM convergence slice.

### Exact resume point

The slice is at the **live credential boundary**, with credential plumbing prepared without introducing live secrets.

Repository-side work provides:

- provider-neutral convergence through INF-011;
- one bounded IT Glue configuration GET and one bounded Datto RMM device search;
- exact organization-context enforcement and cross-organization denial;
- INF-012 relationship evidence only from corroborated identity attributes;
- no provider-to-provider communication and no mutation authority;
- credential-safe preflight at `tools/resource_convergence_preflight.py`;
- operations/rotation guidance at `07-Operations/IT-Glue-Datto-Resource-Convergence-Checklist.md`;
- Datto durable credential contract with runtime bearer-token acquisition;
- CI coverage that rejects the obsolete persisted Datto bearer-token shape.

Do **not** invent live response schemas. Do **not** create placeholder secrets. The next live dependency is fresh dedicated provider credentials.

## Credentials Needed Next

### IT Glue

- logical secret: `it_glue.readonly`
- durable field: `api_key`
- provider base URL: `https://api.itglue.com`
- first live operation: exact configuration GET through `it_glue.entity.get`

### Datto RMM

- logical secret: `datto_rmm.readonly`
- durable fields: `api_url`, `api_key`, `api_secret`
- runtime-only material: `access_token`
- first live operation: bounded device search through `datto_rmm.device.search`

Jason must acquire the Datto bearer token at runtime behind the connector/secret boundary. Do not persist the bearer token in OpenBao and do not place raw credentials in Git, chat, normal logs, evidence, or command history.

## What Is Proven

- Jason Kernel foundation is complete.
- Central Orchestrator ORCH-001 through ORCH-004 are complete.
- OpenBao INF-001, INF-002, and INF-003 are complete in the roadmap.
- INF-010 Microsoft Cloud provider-family foundation is integrated.
- INF-011 provider-neutral Kaseya/Datto resource gateway foundation is integrated.
- INF-012 governed cross-provider relationship foundation is integrated.
- INF-013 provider-neutral artifact/evidence reference boundary is integrated.
- J-116, J-117, J-118, J-119, and J-120 canonical foundation models are approved.
- CAP-001 canonical Autotask read capability is complete.
- CAP-003 Autotask Business Context is live-validated and converged; CAP-002 is retired/superseded.
- PR #77 passed an explicit J-002 Article I-XVIII constitutional review at the no-secret/no-network boundary.

## Current Primary Workstream

### Governed IT Glue + Datto RMM Resource Convergence

The bounded question is:

**Which Datto RMM device corresponds to this IT Glue configuration, and what evidence supports that relationship?**

When credentials become available:

1. provision dedicated least-privilege credentials directly into the approved OpenBao paths using non-echoing input;
2. verify only required field presence, never values;
3. select one controlled organization and known configuration/device pair;
4. perform one exact IT Glue configuration GET;
5. acquire a Datto bearer token at runtime from the durable API credentials;
6. perform one bounded Datto RMM device search;
7. inspect only sanitized response-shape metadata and identity fields;
8. finalize normalization from attributes actually present in the live payloads;
9. evaluate INF-012 relationship evidence through the Central Orchestrator;
10. emit J-119 events only for material provider-neutral occurrences;
11. retain large/raw evidence behind INF-013 references.

The slice remains read-only and grants no execution authority.

## Queued Follow-ons

After the IT Glue + Datto RMM convergence proof:

1. **INF-010 deployment:** governed OpenBao certificate binding and controlled Microsoft test-tenant onboarding.
2. **INF-011 expansion:** additional Kaseya/security-provider adapters only where verified APIs exist.
3. **INF-013 physical store:** bind the first approved physical artifact/evidence store through the capability registry.
4. broader INF-012 relationship and J-119 event normalization across providers.

Additional providers — RocketCyber, SaaS Alerts, VulScan, Graphus, BullPhish, ID Agent, and Microsoft — should not receive credential contracts merely because they are listed. Introduce credentials only when a verified API and bounded first read are ready.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. This remains a historical operational loose end, not the current primary development workstream. Do not overwrite an existing `generate-root` setting without first inspecting the live configuration and reconciling it against governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh `tools/catch_me_up.py` host snapshot together as the authoritative resume context.
- Reconcile conflicts between this checkpoint and live GitHub/host state before destructive or security-sensitive changes.
- Preserve the core rule: agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, or secret values in chat, repository content, logs, or evidence.
