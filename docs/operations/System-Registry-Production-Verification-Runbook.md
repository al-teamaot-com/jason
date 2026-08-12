# System Registry Production Verification Runbook

**Environment:** Jason single-host pilot  
**Status:** Canonical declared inventory implemented; current-host verification must be generated on the physical Jason host before System Registry lifecycle promotion  
**Authority:** J-002 Article XIX and J-103  

## Purpose

This runbook converts Jason's known pilot topology from durable project evidence into a canonical machine-readable System Registry and defines the bounded read-only process used to verify the current physical host.

The registry is descriptive and authoritative for declared topology. It does not authorize changes, execute remediation, rotate credentials, restart services, or silently reconcile drift.

## Canonical files

Declared production-pilot inventory:

`implementation/kernel/system_registry/production-registry.json`

Read-only host verification plan:

`implementation/kernel/system_registry/production-verification-plan.json`

Generic verifier:

`tools/system_registry_verify.py`

The manifest includes the current pilot runtime, OpenBao boundary, OpenClaw transport and bridge, Central Orchestrator relationship, governance gates, credential references, Datto RMM endpoint provider, Microsoft Graph identity-enrichment provider, AWS SES provider, known Microsoft identity binding, registered capabilities, and the single-host pilot deployment relationship.

## Evidence basis for initial declared state

The initial inventory is grounded in durable repository evidence rather than conversation memory. Principal references include:

- `infrastructure/jason-runtime/compose.yaml`
- `implementation/runtime_service/src/jason_runtime/composition.py`
- `implementation/runtime_service/src/jason_runtime/http.py`
- `implementation/orchestrator/resource_capability_catalog.py`
- `implementation/cap-007/src/jason_cap_007/kernel_registration.py`
- `docs/operations/Jason-Secret-Provider-Deployment-Record.md`
- `docs/operations/INF-010-Microsoft-Cloud-Deployment-Checklist.md`
- `docs/operations/CAP-007-AWS-SES-Activation-Runbook.md`
- `docs/sessions/Teams-CAP-007-End-to-End-Operational-Proof-2026-08-11.md`

Historical evidence is sufficient to establish a declared configuration baseline, but it is not automatically treated as a current System Registry observation.

## Lifecycle rule

Physical components represented by the current host-verification plan begin at `configured`, not `verified` or `active`.

Logical governance, provider, capability, identity-binding, and deployment records begin at `registered` unless a dedicated current verification method has been executed and governed evidence is attached.

The verifier never promotes lifecycle state. A successful verification report is evidence for a later governed registry change; it is not authority to edit declared state.

## Read-only host probes

The first production verification plan deliberately supports only bounded non-mutating probes:

- Docker container inspection;
- SHA-256 of a named file inside a named Docker container;
- SHA-256 of an explicitly named local file;
- existence check for an explicitly named local file.

There is no arbitrary-shell probe. There is no restart, repair, package installation, credential read, network mutation, container mutation, or automatic reconciliation behavior.

The initial host plan verifies:

1. `openbao` container identity, image, and running state;
2. `jason-runtime` container identity, image, health, non-root user, read-only root filesystem, dropped capabilities, no-new-privileges, and expected network attachments;
3. `openclaw-openclaw-gateway-1` running and healthy state;
4. the deployed Jason bridge SHA-256 inside the OpenClaw gateway container.

## Validate inventory without touching production

From the repository root:

```bash
python3 tools/system_registry_verify.py --validate-only
```

Expected result is JSON with `status` equal to `valid`, a non-zero registered entity count, a non-zero planned host-check count, `declared_state_changed` equal to `false`, and `remediation_attempted` equal to `false`.

This mode performs no Docker or host-state probe.

## Run current-host verification

On the physical Jason pilot host, first synchronize the approved branch through the normal repository process. Then run the verifier from the repository root using the repository-local Python environment when required:

```bash
mkdir -p /home/al/Jason-Evidence/System-Registry
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
python3 tools/system_registry_verify.py \
  --output "/home/al/Jason-Evidence/System-Registry/system-registry-verification-${STAMP}.json"
```

The verifier exits `0` only when every planned host observation satisfies the corresponding declared state. It exits `2` when any planned item is drifted, unverified, or cannot be observed.

The generated report records only non-secret operational state. It explicitly records that declared state was not changed and remediation was not attempted.

## Interpreting outcomes

### `verified`

The current observation contains all declared fields for that entity and they match exactly. Preserve the report as governed evidence. Lifecycle promotion, if appropriate, requires the normal governed registry change and must reference the evidence.

### `drifted`

The host differs from declared state. Preserve the evidence and investigate. Do not alter the manifest merely to make the check green, and do not modify production directly from the verifier. Any remediation or declared-state change returns through the Central Orchestrator, identity-first authorization, applicable policy, approval, audit, and post-change verification.

### `unverified`

The current evidence is insufficient. Do not infer success from historical records.

### `failed`

The read-only observation itself could not complete. Treat this as an evidence-acquisition failure, not proof that the service is down. Investigate the observer boundary and host access separately.

## Secret handling

The System Registry may store credential references such as `datto_rmm.readonly`, `microsoft_graph.directory_read`, and `aws_ses.sendmail` because those are logical references, not credential values.

The registry and verifier must never record RoleIDs, SecretIDs, OpenBao service tokens, provider keys, OAuth tokens, Microsoft private keys, certificate contents, AWS credentials, transport private keys, passwords, or other secret values.

Provider-secret readiness remains governed by JKD-003 and the canonical provider-secret lifecycle. The host verifier does not read credential material.

## Promotion and documentation rule

After a successful physical-host verification, create a governed change that:

1. references the verification evidence file;
2. records the authenticated change principal and authority;
3. advances only entities whose required verification is satisfied;
4. preserves previous declared-state history;
5. does not broaden provider, capability, identity, or approval scope;
6. updates generated operational documentation from registry truth.

Logical provider/capability/identity records require their own appropriate current verification evidence before promotion. A healthy Docker topology alone does not prove provider authorization, Graph identity resolution, Datto RMM access, or successful email delivery.

## Stop conditions

Stop and escalate rather than guessing when:

- the declared manifest does not schema-validate;
- a dependency is missing or cyclic;
- a probe type is not explicitly supported;
- Docker inspection requires privileges the operator does not possess;
- observed state contains unexpected sensitive information;
- the bridge digest differs from declared state;
- a production component cannot be observed safely;
- remediation would be required to make a check pass.

## Constitutional result

This workstream makes the production-pilot topology reproducible from structured truth and creates a current-state verification path that is read-only, deterministic, bounded, attributable, and incapable of silently repairing production. It implements the next operational increment of Article XIX without weakening Jason's identity, orchestration, governance, or secret boundaries.
