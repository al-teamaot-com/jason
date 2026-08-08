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

The active branch is `feature/itglue-datto-resource-convergence`.

### Exact resume point

The first governed IT Glue + Datto RMM convergence slice has reached the **live credential boundary**.

Repository-side work now provides:

- a provider-neutral convergence plan through INF-011;
- one bounded IT Glue configuration GET and one bounded Datto RMM device search;
- execution through the existing connector and secret-resolution boundaries;
- exact organization-context enforcement across provider reads;
- explicit denial of cross-organization correlation;
- INF-012 relationship evidence only when selected identity attributes actually agree;
- no provider-to-provider communication;
- read-only execution only;
- a credential-safe preflight command at `tools/resource_convergence_preflight.py`;
- an operations checklist at `07-Operations/IT-Glue-Datto-Resource-Convergence-Checklist.md`.

Do **not** invent or guess live provider response schemas. The next step is controlled read-only validation with fresh credentials so Jason can observe the actual provider payloads and finalize normalization from evidence.

## Credentials Needed Next

### IT Glue

- logical secret: `it_glue.readonly`
- current connector credential field: `api_key`
- provider base URL: `https://api.itglue.com`
- first live operation: exact configuration GET through `it_glue.entity.get`

### Datto RMM

- logical secret: `datto_rmm.readonly`
- current connector credential fields: `base_url`, `access_token`
- first live operation: bounded device search through `datto_rmm.device.search`

If the production Datto RMM credential is issued as an API key/secret or OAuth client rather than a durable bearer token, add token acquisition behind the existing secret/transport boundary before the live read. Do not place raw credentials in Git, chat, normal logs, evidence, or command history.

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
- Jason Command Center, Prometheus, Grafana, Ollama, OpenBao, and OpenClaw were healthy in the most recent host snapshot.

## Current Primary Workstream

### Governed IT Glue + Datto RMM Resource Convergence

The bounded question is:

**Which Datto RMM device corresponds to this IT Glue configuration, and what evidence supports that relationship?**

The live validation sequence after credentials are provisioned is:

1. select one controlled organization and one known configuration/device pair;
2. resolve `it_glue.readonly` through Jason's approved secret provider;
3. perform one exact IT Glue configuration GET;
4. resolve `datto_rmm.readonly` through Jason's approved secret provider;
5. perform one bounded Datto RMM device search;
6. inspect only sanitized response-shape metadata and identity fields;
7. finalize provider normalization for attributes actually present in the live payloads;
8. evaluate INF-012 relationship evidence through the Central Orchestrator;
9. emit J-119 events only for material provider-neutral occurrences;
10. retain large/raw provider evidence behind INF-013 references rather than copying it into normal logs or chat.

The first slice remains read-only and grants no execution authority.

## Queued Follow-ons

After the IT Glue + Datto RMM convergence proof:

1. **INF-010 deployment:** governed OpenBao certificate binding and controlled Microsoft test-tenant onboarding.
2. **INF-011 expansion:** additional Kaseya/security-provider adapters only where verified APIs exist.
3. **INF-013 physical store:** bind the first approved physical artifact/evidence store through the capability registry.
4. broader INF-012 relationship and J-119 event normalization across providers.

Additional providers — RocketCyber, SaaS Alerts, VulScan, Graphus, BullPhish, ID Agent, and Microsoft — should not receive credential contracts merely because they are listed in the resource catalog. Introduce credentials when a verified API and bounded first read are ready for controlled validation.

## Outstanding Historical Recovery Note

A prior operator session stopped while temporarily enabling a legacy OpenBao root-recovery endpoint because a `generate-root` setting already existed. Multiple pre-root-recovery configuration backups exist under `/opt/jason/infrastructure/openbao/config/`. This remains a historical operational loose end, not the current primary development workstream. Do not overwrite an existing `generate-root` setting without first inspecting the live configuration and reconciling it against governed recovery records.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance.
- Treat this checkpoint, current GitHub state, and a fresh `tools/catch_me_up.py` host snapshot together as the authoritative resume context.
- Reconcile conflicts between this checkpoint and live GitHub/host state before destructive or security-sensitive changes.
- Preserve the core rule: agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, or secret values in chat, repository content, logs, or evidence.
