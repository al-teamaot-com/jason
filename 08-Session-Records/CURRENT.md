# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-10  
**Purpose:** Canonical human-readable resume point for a future Jason work session. Host/runtime facts remain independently verified by `tools/catch_me_up.py` and the applicable host-proof records.

## Resume Here

Project Jason has now completed the first physical-host operational validation of the canonical OpenBao provider AppRole runtime, governed IT Glue and Datto RMM live reads, bounded provider discovery, and the Datto managed-device authority model.

PR #136 (`feature/operational-live-proof-runbook`) contains the host-proof runbook, bounded provider discovery tools, accepted ADR-004, the Datto managed-device authority implementation, and the 2026-08-10 documentation corrections. The branch passed focused host tests and both GitHub release gates before final governance completion.

A separate repository-wide connector regression-baseline problem is tracked in issue #137 and must be resolved before the first live Teams approval round-trip.

## What Is Proven On The Jason Host

### OpenClaw / authority foundation

- OpenClaw runs in Docker and remains ingress/transport only; the Central Orchestrator is the sole execution coordinator.
- OpenClaw machine trust uses Ed25519 application-layer signatures with private keys retained only inside the OpenClaw secret boundary.
- JKD-001 provides scoped identity/authority, approvals, short-lived contexts, revocation, durable delegation, and authority audit.
- Direct machine-service and delegated-human paths completed through governance/orchestration and fail closed after revocation/replay.
- Production OpenClaw operations timers and sanitized operational health are deployed.

### OpenBao / provider secret runtime

- OpenBao runs in Docker and is exposed only on host loopback `127.0.0.1:8200` for the pilot.
- OpenBao version observed during the 2026-08-10 preflight: 2.6.1.
- OpenBao was initialized, unsealed, and active/non-standby.
- Production provider secrets use provider-specific OpenBao AppRoles through JKD-003.
- Provider runtime AppRole tokens are short-lived, may read only the provider-specific secret plus self-revoke, and are not persisted.
- Shared persistent provider runtime tokens are prohibited.
- `/usr/local/bin/jason-secret` remains a historical commissioning/general wrapper and is **not** the canonical production-provider readiness path.
- `jason-secret --health` / `--contract-test` may return `DENIED: OpenBao token file is not configured` while provider-specific AppRole runtime is healthy. Operators must not create a persistent provider token merely to satisfy that historical wrapper path.
- Host-side Python validation uses `~/projects/jason/.venv` built from `implementation[dev]`; system Python cannot be assumed to contain pytest.
- Direct `OpenBaoSecretResolver.resolve()` validation requires the logical secret plus a governed `ConnectorContext` with a non-empty correlation ID.

### IT Glue

- `it_glue.readonly` resolves through the canonical provider-specific AppRole lifecycle.
- Required durable field: `api_key`.
- Live AppRole resolution succeeded with secret values suppressed and temporary token self-revocation.
- A bounded governed IT Glue live read succeeded with maximum one returned record.
- Connector audit emitted `connector.requested` and `connector.completed`.
- Raw provider payloads and credentials were not printed or persisted.
- `tools/it_glue_configuration_discovery.py` now provides a bounded, sanitized operator path for selecting a controlled configuration without source introspection or raw provider dumps.

### Datto RMM

- `datto_rmm.readonly` resolves through the canonical provider-specific AppRole lifecycle.
- Durable fields: `api_url`, `api_key`, `api_secret`.
- Datto OAuth bearer tokens are acquired at runtime and are not persisted.
- A bounded governed `datto_rmm.device.search` live read succeeded with maximum one returned device.
- Connector audit emitted `connector.requested` and `connector.completed`.
- Raw provider payloads, API credentials, and OAuth tokens were not printed or persisted.
- `tools/datto_rmm_device_discovery.py` now provides bounded sanitized operator discovery.

## ADR-004 — Managed Device Authority

ADR-004 is accepted and implemented.

For the **RMM-managed device domain**:

- Datto RMM is the authoritative external provider for managed-device existence, stable Datto external UID, and governed operational identity/state.
- IT Glue is a documentation observation and cannot independently establish or override managed-device operational identity.
- Jason remains authoritative for provider-independent canonical Asset/Device identity, tenant/organization binding, cross-provider mappings, verification state, promotion decisions, policy, approvals, and execution authority.

Provider authority is separate from relationship direction. J-118 canonical semantics remain:

`IT Glue configuration -> represents -> Datto managed-device observation`

No new inverse canonical relationship `represented_by` was admitted.

## 2026-08-10 Live Managed-Device Authority Proof

The live proof passed:

- exactly one bounded Datto device observation was accepted;
- source authority was `datto_rmm:managed-device-authority`;
- the stable external Datto device identifier was present;
- approved operational identity metadata was present;
- both Datto and IT Glue connector audit boundaries fired;
- no canonical Jason object was created;
- no canonical relationship was promoted;
- no provider mutation occurred;
- no raw provider payload or secret material was printed or persisted.

The selected IT Glue documentation relationship remained `unresolved` because the requested serial-number attribute was absent or inconsistent across the governed observations. This is the expected fail-closed behavior: the Datto managed-device authority remains valid while documentation reconciliation remains unresolved.

Host proof:

- `08-Session-Records/IT-Glue-Datto-Host-Operational-Proof-2026-08-10.md`

## Documentation Reconciled On 2026-08-10

The physical host session exposed several operational documentation gaps. They are now explicitly recorded rather than left as tribal knowledge:

1. historical `jason-secret` token-file health behavior versus canonical provider AppRole runtime;
2. project-local `.venv` bootstrap and pytest requirement;
3. required `ConnectorContext` for direct OpenBao resolver validation;
4. verified implementation/tool names rather than guessed class names;
5. supported bounded/sanitized provider object discovery;
6. Datto RMM managed-device authority and IT Glue documentation role;
7. J-118 canonical `represents` relationship direction;
8. acceptable unresolved documentation relationship behavior;
9. repository-wide connector regression-baseline defects discovered during host validation.

Updated/added records include:

- `05-ADR/ADR-004-Datto-RMM-Managed-Device-Authority.md`;
- `07-Operations/Jason-Bootstrap-and-Secrets-Runbook.md`;
- `07-Operations/Jason-Secret-Provider-Deployment-Record.md`;
- `07-Operations/IT-Glue-Datto-Resource-Convergence-Checklist.md`;
- `07-Operations/OPS-ITGLUE-DATTO-LIVE-CONVERGENCE-PROOF.md`;
- `08-Session-Records/IT-Glue-Datto-Host-Operational-Proof-2026-08-10.md`;
- this checkpoint.

## Regression Baseline — Issue #137

The focused PR #136 authority/convergence scope passed. GitHub `Validate Jason` and `Validate IT Glue Datto Resource Convergence` also passed on the finalized branch history.

A broader host connector-suite run exposed unrelated pre-existing defects that are tracked in issue #137:

- stale Microsoft bounded-automation expected error text;
- Microsoft JWKS tests using JWT fixtures rejected by the installed PyJWT before mocked verification paths;
- relationship-registry test use of `__dict__` on a `slots=True` dataclass;
- Teams approval delivery tests constructing `ApprovalRequest(summary=...)` although the current contract no longer accepts `summary`;
- package-layout collection problems for artifact-evidence and AWS provider tests under the declared implementation packaging.

These failures must not be hidden, waived, or fixed by weakening implementation behavior. The Teams approval delivery failures are blocking before the live Teams approval round-trip.

## Current Primary Workstream

### Restore clean connector regression baseline, then Teams approval round-trip

Immediate priority is issue #137.

1. establish the canonical full regression command for the Jason host;
2. repair stale/brittle tests and package configuration without weakening fail-closed behavior;
3. make dependency-sensitive JWT test fixtures deterministic;
4. update Teams approval delivery tests to the current `ApprovalRequest` contract;
5. run the normal branch -> tests -> release validation -> PR -> governance review -> merge workflow;
6. only after the Teams delivery/ingress boundary is green perform the first live Teams approval round-trip.

## Provider Authority Rule

Authority is assigned by **resource domain and attribute**, not by one globally authoritative provider.

The accepted device rule is the first formal example. Future assignments for users, tickets, agreements, cloud identity, security state, knowledge, and other resources require explicit policy/architecture decisions rather than assumption.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance unless a host-sensitive step requires it.
- Treat this checkpoint, current GitHub state, applicable ADRs/runbooks, and a fresh CatchMeUp host snapshot together as authoritative resume context.
- Reconcile conflicts between checkpoint/GitHub/host state before destructive or security-sensitive changes.
- Agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, RoleIDs, SecretIDs, OAuth bearer tokens, private signing keys, or secret values in chat, repository content, logs, or evidence.
