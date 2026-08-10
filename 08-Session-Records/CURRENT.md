# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-10  
**Purpose:** Canonical human-readable resume point for a future Jason work session. Host/runtime facts remain independently verified by `tools/catch_me_up.py` and the applicable host-proof records.

## Resume Here

Project Jason has completed the 2026-08-10 physical-host validation of the canonical OpenBao provider AppRole runtime, governed IT Glue and Datto RMM live reads, bounded provider discovery, and the Datto managed-device authority model. PR #136 was governance-reviewed and merged to `main` as `ac5344a`.

The repository-wide connector regression baseline discovered during that host validation was repaired through PR #138 and merged to `main` as `35de7c1`. The full connector suite now collects and passes on the physical Jason host.

The active branch is `feature/microsoft-teams-certificate-authorization`. The current workstream is the first live Teams approval round-trip. During pre-deployment inspection, Jason correctly stopped before provisioning Microsoft credentials because the existing Graph channel-post path relied on an application credential model that is not appropriate for normal Teams channel posting. Issue #139 records the correction.

The preferred architecture is now to reuse the already-installed OpenClaw Microsoft Teams channel strictly as transport/ingress while Jason retains all identity, approval, policy, authority, orchestration, replay, recovery, and audit decisions.

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
- `tools/it_glue_configuration_discovery.py` provides a bounded, sanitized operator path for selecting a controlled configuration without source introspection or raw provider dumps.

### Datto RMM

- `datto_rmm.readonly` resolves through the canonical provider-specific AppRole lifecycle.
- Durable fields: `api_url`, `api_key`, `api_secret`.
- Datto OAuth bearer tokens are acquired at runtime and are not persisted.
- A bounded governed `datto_rmm.device.search` live read succeeded with maximum one returned device.
- Connector audit emitted `connector.requested` and `connector.completed`.
- Raw provider payloads, API credentials, and OAuth tokens were not printed or persisted.
- `tools/datto_rmm_device_discovery.py` provides bounded sanitized operator discovery.

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

The selected IT Glue documentation relationship remained `unresolved` because the requested serial-number attribute was absent or inconsistent across the governed observations. This is expected fail-closed behavior: Datto managed-device authority remains valid while documentation reconciliation remains unresolved.

Host proof: `08-Session-Records/IT-Glue-Datto-Host-Operational-Proof-2026-08-10.md`.

## Regression Baseline — Resolved

Issue #137 was opened when the broad connector suite exposed stale test/package assumptions unrelated to PR #136. The fixes were isolated to the regression baseline, validated on the physical Jason host, and merged through PR #138 as `35de7c1`.

Host result after the fix:

- full connector test collection succeeded;
- the complete `implementation/connectors/tests` suite passed 100%;
- the working tree remained clean.

This cleared the test-baseline blocker for the Teams approval workstream.

## ADR-005 — OpenClaw Teams Transport Boundary

ADR-005 records the Teams transport convergence decision.

### Decision

- OpenClaw is the supported Microsoft Teams transport/ingress provider for Jason approval interactions.
- Jason does not import OpenClaw TypeScript internals by filesystem path.
- Jason integrates through a supported OpenClaw external capability boundary.
- OpenClaw does not decide whether a Teams response is a valid Jason approval.
- Microsoft authentication is identity evidence, not execution authority.
- Jason binds Microsoft tenant/object identity to the governed Jason organization/identity before producing a provider-neutral approval response.
- Approval policy, immutable approval records, fresh authority contexts, replay protection, recovery authorization, and continuation remain Jason responsibilities.
- Central Orchestrator alone resumes or retries execution.

This was reviewed against the Jason Constitution/Canon and found consistent with human governance, evidence-before-assertion, separation of responsibilities, vendor independence, and institutional-memory requirements.

### OpenClaw capability evidence observed on host

The installed OpenClaw Teams channel provides:

- proactive message delivery using stored conversation references;
- direct Adaptive Card delivery through `sendAdaptiveCardMSTeams`;
- organization/team/channel scoping through OpenClaw configuration;
- allowlist checks for card-action invokes;
- authenticated `adaptiveCard/action` handling after Bot Framework JWT validation;
- a supported Gateway `send` boundary with idempotency/deduplication and delivery receipt identifiers;
- a deliberately restricted admin HTTP RPC allowlist that does not expose normal message/session sends.

Jason therefore uses the supported Gateway send path rather than weakening the admin RPC allowlist or duplicating a Teams bot stack.

## Teams Transport Adapter — Host Validation

Branch: `feature/microsoft-teams-certificate-authorization`.

The branch now contains:

- `05-ADR/ADR-005-OpenClaw-Teams-Transport-Boundary.md`;
- updated `07-Operations/Teams-Approval-Deployment-and-Recovery.md`;
- `08-Session-Records/Teams-Approval-Transport-Decision-2026-08-10.md`;
- `implementation/connectors/microsoft_graph/openclaw_teams_approval_transport.py`;
- `implementation/connectors/microsoft_graph/openclaw_teams_approval_runtime.py`;
- `implementation/connectors/tests/test_openclaw_teams_approval_transport.py`.

Physical-host validation at branch revision `1adbf26` passed:

- 15 focused OpenClaw Teams transport / approval delivery / approval ingress tests passed;
- the full connector regression suite passed 100%;
- all required ADR/runbook/session records were present;
- the working tree remained clean.

The branch is ahead of `main` only by the Teams transport convergence changes and documentation.

## Documentation Reconciled On 2026-08-10

The morning physical-host session and subsequent Teams workstream exposed several operational/documentation gaps. They are now explicitly recorded rather than left as tribal knowledge:

1. historical `jason-secret` token-file health behavior versus canonical provider AppRole runtime;
2. project-local `.venv` bootstrap and pytest requirement;
3. required `ConnectorContext` for direct OpenBao resolver validation;
4. verified implementation/tool names rather than guessed class names;
5. supported bounded/sanitized provider object discovery;
6. Datto RMM managed-device authority and IT Glue documentation role;
7. J-118 canonical `represents` relationship direction;
8. acceptable unresolved documentation relationship behavior;
9. repository-wide connector regression-baseline defects and their resolution through PR #138;
10. Teams live credential/configuration state was absent when inspected, so no secret was provisioned prematurely;
11. the original Graph app-only channel-post design was stopped before live provisioning because its permission model was inappropriate for normal approval delivery;
12. OpenClaw Teams was verified as the preferred reusable transport/ingress boundary;
13. the OpenClaw transport design was checked against the Constitution/Canon before implementation;
14. the supported Gateway `send` boundary is preferred over OpenClaw implementation-file imports or broadening admin HTTP RPC;
15. host validation of the thin Teams transport adapter and full connector regression suite passed.

## Current Primary Workstream

### Complete Teams transport governance and perform first live approval round-trip

Immediate next steps:

1. validate the exact installed OpenClaw Gateway `send` request mapping used by the Jason adapter;
2. run release validation for the feature branch;
3. open PR for issue #139, perform governance review, and merge only after green validation;
4. deploy only the non-secret target/identity bindings and whatever existing OpenClaw Teams configuration is required by the approved runbook;
5. perform one harmless/no-side-effect approval request through the live Teams delivery path;
6. submit one authenticated Teams approval/deny action;
7. verify Jason tenant/identity binding, approval authorization, immutable audit, fresh JKD-001 authority context, replay protection, and Central Orchestrator continuation;
8. preserve sanitized evidence and update this checkpoint after the live round-trip.

A successful Teams button click alone is not proof. The full authority and evidence chain must be observed.

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
