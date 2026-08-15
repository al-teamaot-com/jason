# System Registry Production Verification Runbook

**Environment:** Jason single-host pilot  
**Status:** Canonical inventory and governed lifecycle evidence active; recurring host verification remains read-only and bounded  
**Authority:** J-002 Article XIX and J-103  
**Updated:** 2026-08-15

## Purpose

This runbook defines how Jason converts durable topology declarations and current observations into governed System Registry verification evidence without allowing the registry or verifier to become a remediation engine.

The registry is descriptive and authoritative for declared/effective operational topology. It does not authorize changes, execute remediation, rotate credentials, restart services, or silently reconcile drift.

## Canonical files

Declared production-pilot inventory:

`implementation/kernel/system_registry/production-registry.json`

Append-only governed lifecycle/verification evidence:

`implementation/kernel/system_registry/production-lifecycle-events.json`

Bounded recurring host verification plan:

`implementation/kernel/system_registry/production-verification-plan.json`

Generic verifier:

`tools/system_registry_verify.py`

Generated human-readable operational view:

`docs/operations/System-Registry-Current-Operational-State.md`

The current registry includes the runtime, OpenBao boundary, OpenClaw component/bridge, direct Microsoft Teams ingress gateway, Central Orchestrator relationship, governance gates, credential references, Datto RMM endpoint provider, Microsoft Graph identity-enrichment provider, AWS SES provider, known Microsoft identity binding, registered capabilities, and the single-host pilot deployment relationship.

## Verification models

Jason currently uses two governed verification patterns.

### 1. Bounded recurring observer plan

The generic verifier executes only pre-registered non-mutating probes from `production-verification-plan.json`. It is appropriate when the declared state can be compared directly to the bounded probe output.

The original plan covers the stable core physical observations:

1. `openbao` container identity/image/running state;
2. `jason-runtime` container identity/image/health/hardening/network state;
3. `openclaw-openclaw-gateway-1` running/health state; and
4. deployed OpenClaw Jason bridge SHA-256.

### 2. Governed production-proof lifecycle verification

A topology change may require a broader but still bounded proof than the generic observer currently models, for example exclusive host-port ownership plus live interface/runtime behavior.

In that case:

- the production mutation is governed separately;
- current host evidence is captured without secret values;
- a durable proof record documents the exact observations;
- a System Registry lifecycle event references that proof and the registered verification method;
- lifecycle promotion remains explicit and attributable rather than being performed automatically by the observer.

The 2026-08-15 direct Teams ingress cutover used this pattern. `component.jason-teams-gateway`, `credential.microsoft-teams-gateway-client`, and the updated `deployment.jason-single-host-pilot` were promoted from governed evidence in `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`.

The recurring generic Docker probe should not be assumed to verify host-port ownership fields that it does not currently emit. Do not add a component to the recurring verification plan until its registered declared-state comparison can be satisfied by the bounded probe or an approved new probe type.

## Evidence basis for declared state

Declared inventory is grounded in durable repository evidence rather than conversation memory. Principal references include:

- `infrastructure/jason-runtime/compose.yaml`;
- `infrastructure/jason-teams-gateway/`;
- `implementation/runtime_service/src/jason_runtime/composition.py`;
- `implementation/runtime_service/src/jason_runtime/http.py`;
- `implementation/orchestrator/resource_capability_catalog.py`;
- `implementation/cap-007/src/jason_cap_007/kernel_registration.py`;
- `docs/operations/Jason-Secret-Provider-Deployment-Record.md`;
- `docs/operations/INF-010-Microsoft-Cloud-Deployment-Checklist.md`;
- `docs/operations/CAP-007-AWS-SES-Activation-Runbook.md`;
- `docs/sessions/Teams-CAP-007-End-to-End-Operational-Proof-2026-08-11.md`; and
- `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`.

Historical evidence can establish a declared configuration baseline but must not be silently treated as a fresh observation. Lifecycle promotion requires the registered verification method and governed evidence applicable to that entity.

## Lifecycle rule

Lifecycle progression is explicit and append-only through governed lifecycle events.

Typical progression:

`registered -> configured -> verified -> active`

Not every entity is currently `active`; `verified` means only that governed evidence satisfied the entity's registered verification method at the recorded time.

The generic verifier never promotes lifecycle state. A successful verification report is evidence for a later governed registry change; it is not authority to edit declared state.

A production proof likewise does not self-promote anything. The lifecycle event is the explicit governed change and must identify principal, authority, reason, verification method, outcome, and evidence references.

## Read-only host probes

The recurring verifier deliberately supports only bounded non-mutating probes:

- Docker container inspection;
- SHA-256 of a named file inside a named Docker container;
- SHA-256 of an explicitly named local file; and
- existence check for an explicitly named local file.

There is no arbitrary-shell probe. There is no restart, repair, package installation, credential read, network mutation, container mutation, or automatic reconciliation behavior.

## Validate inventory without touching production

From the repository root:

```bash
python3 tools/system_registry_verify.py --validate-only
python3 tools/system_registry_docs.py --check
```

The inventory validation must report a valid registry/plan without changing declared state or attempting remediation.

The documentation check must prove the committed generated operational-state view exactly matches the current registry plus lifecycle history.

These modes perform no production mutation.

## Run recurring current-host verification

On the physical Jason pilot host, first synchronize the approved branch through the normal repository process. Then run the verifier from the repository root:

```bash
mkdir -p /home/al/Jason-Evidence/System-Registry
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
python3 tools/system_registry_verify.py \
  --output "/home/al/Jason-Evidence/System-Registry/system-registry-verification-${STAMP}.json"
```

The verifier exits `0` only when every **planned** host observation satisfies the corresponding declared state. It exits `2` when a planned item is drifted, unverified, or cannot be observed.

A successful recurring run proves only the entities included in the current plan. It does not invalidate or replace separate governed verification evidence for entities outside that plan.

The generated report records only non-secret operational state and explicitly records that declared state was not changed and remediation was not attempted.

## Interpreting outcomes

### `verified`

The current observation contains all declared fields expected by that verification method and they match. Preserve the report as governed evidence. Lifecycle promotion, if appropriate, requires the normal governed registry change and must reference the evidence.

### `drifted`

Observed state differs from declared state. Preserve evidence and investigate. Do not alter the manifest merely to make the check green, and do not modify production directly from the verifier. Any remediation or declared-state change returns through the Central Orchestrator, identity-first authorization, applicable policy, approval, audit, and post-change verification.

### `unverified`

Current evidence is insufficient for the registered declared state. Do not infer success from a historical proof or unrelated health check.

### `failed`

The read-only observation itself could not complete. Treat this as an evidence-acquisition failure, not proof that the service is down. Investigate the observer boundary and host access separately.

## Teams ingress topology verification

Current declared/effective Teams ingress topology is represented by:

- `component.jason-teams-gateway`;
- `credential.microsoft-teams-gateway-client`; and
- `deployment.jason-single-host-pilot`.

The production proof established:

- `jason-teams-gateway` healthy;
- host `3978` published to gateway container `3979`;
- OpenClaw healthy on host `18789-18790` without host `3978`;
- `jason-runtime` healthy;
- live Teams -> Jason -> Datto RMM response completed;
- no matching OpenClaw model dispatch for the ordinary Teams turns; and
- a rollback state/Compose backup existed before declaring success.

Proof owner:

`docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`

Future topology changes affecting host port `3978` require new governed observation/evidence and must update the System Registry rather than editing only the runbook.

## Secret handling

The System Registry may store logical credential references and non-secret protection/location metadata, for example:

- `datto_rmm.readonly`;
- `microsoft_graph.directory_read`;
- `aws_ses.sendmail`; and
- `microsoft_teams.gateway_app`.

The registry, lifecycle events, generated view, and verifier must never record client-secret values, RoleIDs, SecretIDs, OpenBao service tokens, provider keys, OAuth tokens, Microsoft private keys, certificate contents, AWS credentials, transport private keys, passwords, or other secret values.

The current direct Teams gateway credential reference describes a temporary mode-0600 host-protected migration location. The value itself is excluded from the registry. Migration into Jason's governed secret-provider or federated/certificate identity architecture remains a separate hardening workstream.

## Promotion and documentation rule

After successful verification, a governed change that promotes lifecycle must:

1. reference the applicable verification evidence;
2. record authenticated change principal and authority;
3. advance only entities whose required verification is satisfied;
4. preserve prior lifecycle history;
5. avoid broadening provider, capability, identity, or approval scope merely because physical state is healthy;
6. update generated operational documentation from registry truth; and
7. update CURRENT/ADR/runbook/proof records when the topology change affects a material architectural or operational boundary.

Logical provider/capability/identity records require their own appropriate current verification evidence before promotion. Healthy Docker topology alone does not prove provider authorization, Graph identity resolution, Datto RMM access, or successful email delivery.

## Stop conditions

Stop and escalate rather than guessing when:

- the declared manifest or lifecycle history does not schema-validate;
- a dependency is missing or cyclic;
- a lifecycle event does not match the current effective state;
- a verification method is not registered for the entity;
- a probe type is not explicitly supported;
- the recurring probe cannot emit all declared state required for comparison;
- Docker inspection requires privileges the operator does not possess;
- observed state contains unexpected sensitive information;
- a digest or declared topology differs from observation;
- a production component cannot be observed safely;
- remediation would be required to make a check pass; or
- generated operational documentation is stale relative to structured truth.

## Constitutional result

The production-pilot topology is reconstructable from structured truth plus append-only lifecycle evidence. Current physical verification remains read-only, deterministic, bounded, attributable, and incapable of silently repairing production. Broader production proofs may establish verification when the evidence requirement is richer than the generic probe plan, but lifecycle promotion remains a separate explicit governed event.

This preserves Article XIX while keeping identity, Central Orchestrator authority, governance, provider, and secret boundaries intact.
