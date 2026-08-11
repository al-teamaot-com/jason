# Project Jason — Current Session Checkpoint

**Updated:** 2026-08-11  
**Purpose:** Canonical human-readable resume point for a future Jason work session. Host/runtime facts remain independently verified by `tools/catch_me_up.py` and the applicable host-proof records.

## Resume Here

Project Jason has now completed the first live end-to-end conversational consequential action through the governed architecture:

```text
Authenticated Microsoft Teams user
-> OpenClaw transport / signed Jason bridge
-> Jason trusted ingress
-> Microsoft tenant/object identity binding
-> validated Microsoft client boundary
-> JKD-003/OpenBao Microsoft certificate credential
-> MSAL application token
-> Microsoft Graph exact-user lookup
-> governed conversation action intent
-> JKD-001 authority and pilot per-request approval evidence
-> Central Orchestrator
-> CAP-007 communication.email.send
-> JKD-003/OpenBao AWS SES credential
-> AWS SES
-> deterministic Teams success response
```

The live Teams command was:

```text
send me an email
```

Jason resolved the logged-in user to `al@teamaot.com`, completed the governed CAP-007 send, and the operator supplied mailbox evidence showing receipt with subject `Test email from Jason`.

Mailbox evidence digest:

```text
SHA-256: be2b2239dd5449f0ee085fb007bf3fb921f885e46a9b51b7a416b7ad9cef9c53
Size: 113664 bytes
```

The binary `.msg` evidence is not stored in Git. The digest is retained for integrity comparison.

## Active Branch

```text
feature/jason-runtime-service
```

The branch contains the runtime/service, governed Teams conversational action path, Microsoft Graph identity enrichment, CAP-007 runtime integration, provider-specific OpenBao secret lifecycle changes, deployment composition, and constitutional proof documentation.

`main` remains the authoritative branch until this feature branch completes validation, governance review, and merge.

## What Is Proven On The Jason Host

### Central orchestration and authority

- Central Orchestrator is the sole execution coordinator.
- OpenClaw transports conversation evidence but does not decide Jason execution authority.
- JKD-001 provides scoped identity/authority, approvals, short-lived contexts, revocation, and durable authority evidence.
- Conversation reasoning may propose intent but may not invoke providers, invent credentials, or claim provider success.
- Deterministic response rendering reports consequential success only after orchestrator completion.
- Agents do not invoke or communicate with other agents directly.

### OpenClaw / Teams boundary

- OpenClaw runs in Docker and remains ingress/transport only.
- Jason ingress uses application-layer Ed25519 machine trust and replay/security controls.
- The active `jason-bridge` extension was hash-compared against the repository implementation before the live send.
- A stale active bridge was detected, backed up, replaced from the repository, and the gateway restarted.
- Post-restart active bridge SHA-256 matched the repository:

```text
a9438c939d76a79c5f0113d654e1c5a47ae1e845ac1f0113ad7a2a56eb39f211
```

- OpenClaw gateway was healthy before the live test.

### OpenBao / JKD-003 provider secret runtime

- OpenBao runs in Docker for the single-host pilot.
- Provider secrets use dedicated AppRoles through JKD-003.
- Runtime AppRole service tokens are short-lived, restricted to the provider-specific KV read plus self-revoke, and are not persisted.
- Shared persistent provider runtime tokens are prohibited.
- The historical `/usr/local/bin/jason-secret` wrapper is not the canonical production-provider readiness path.
- Evidence must never contain RoleIDs, SecretIDs, OpenBao tokens, provider credentials, private keys, or bearer tokens.

Current governed logical secrets include:

```text
autotask.readonly
it_glue.readonly
datto_rmm.readonly
microsoft_graph.directory_read
aws_ses.sendmail
```

### Microsoft Graph identity enrichment

The approved pilot Microsoft identity metadata is:

```text
Tenant ID: f7054323-d52b-4863-8c2f-1898f0b6077c
Application ID: c94301b7-7194-46ab-aab7-94f9366f51a9
Service principal ID: f784d32d-1d6f-4080-97d4-5efa194a14ed
Authenticated user object ID: bee80bdc-ffb0-4c50-b453-c09d4d411f5f
Resolved mailbox: al@teamaot.com
```

The exact-user lookup uses application permission:

```text
User.Read.All
```

The runtime profile is currently named `directory-read`; the name does not imply use of broader `Directory.Read.All`.

The durable client boundary is:

```text
Internal client ID: client-aot-internal
Provider: microsoft_graph
Primary domain: teamaot.com
Profile: directory-read
Status: validated
```

The runtime obtains the Microsoft certificate credential only through OpenBao. The historical Teams certificate files are not a runtime fallback.

A live no-send test inside the running `jason-runtime` container proved:

```text
validated boundary -> OpenBao -> MSAL -> Graph -> al@teamaot.com
```

No access token was printed or persisted, and no email was sent during this identity proof.

### CAP-007 governed email

Canonical capability:

```text
communication.email.send
```

Current provider:

```text
aws-ses
```

Current approved sender:

```text
jason@teamaot.com
```

CAP-007 characteristics for the pilot:

- explicit authority required;
- per-request approval evidence required;
- idempotency key required;
- non-idempotent consequential action;
- exactly one provider attempt;
- no blind automatic retry;
- no SMTP/Graph/local-sendmail fallback;
- provider credential only through `aws_ses.sendmail` / JKD-003/OpenBao;
- durable safe audit excludes recipient, clear subject, body, and credential-bearing fields.

The earlier manual CAP-007 pilot succeeded and is preserved in:

`07-Operations/CAP-007-Live-Pilot-Proof-2026-08-11.md`.

The later Teams conversational end-to-end proof is preserved in:

`08-Session-Records/Teams-CAP-007-End-to-End-Operational-Proof-2026-08-11.md`.

### Pilot approval limitation

The current pilot policy may materialize an authenticated Teams imperative as explicit per-request JKD-001 approval evidence for that same authenticated principal. This is formal self-approval evidence for the approved pilot, not an independent approver class and not a generalized authorization model for higher-risk actions.

Any broader use of self-approval, especially for higher-risk capabilities, requires governance review.

## Runtime Deployment State

`jason-runtime` is deployed as a hardened container with:

- non-root UID/GID `1000:1000`;
- read-only root filesystem;
- dropped Linux capabilities;
- `no-new-privileges`;
- bounded tmpfs;
- durable authority, identity-binding, replay, security-audit, orchestration-event, and Microsoft client-boundary stores;
- provider-specific read-only AppRole mounts;
- local Ollama model `qwen3:1.7b` for bounded conversational reasoning.

The Microsoft Graph AppRole host directory is root-owned and mode `0750`; its AppRole files are root-owned, runtime-group-readable only, and mode `0640`.

This permission change was necessary because the first live container lookup correctly failed closed when the runtime UID could not read root-only mode-`0600` AppRole files. No fallback credential source was used.

## Test Evidence

During the Microsoft/Teams/CAP-007 workstream:

```text
61 focused governed bridge tests passed
66 expanded Microsoft identity/runtime/deployment tests passed
```

The live runtime self-resolution then passed before any Teams send was attempted.

Final release-wide validation and CI review are still required before merging the feature branch to `main`.

## Previous Proven Foundations

The following previously accepted work remains in force:

- canonical OpenBao provider AppRole runtime;
- governed IT Glue and Datto RMM bounded reads;
- ADR-004 Datto RMM managed-device authority model;
- IT Glue documentation-observation role;
- provider-neutral canonical identity and cross-provider mapping authority retained by Jason;
- repository-wide connector regression baseline repaired and merged;
- ADR-005 OpenClaw Teams transport boundary accepted;
- OpenClaw is transport/ingress, not policy/authority/orchestration.

## Constitutional Reconciliation — 2026-08-11

The Teams-to-CAP-007 implementation was reviewed against `J-002 — The Jason Constitution`.

Key conclusions:

- **Human Governance:** action originates from an authenticated human; Microsoft authentication is identity evidence, not execution authority.
- **Architecture Before Implementation:** Teams, Graph, OpenBao, and SES are implementations behind defined boundaries.
- **Independence and Capability Abstraction:** conversation requests `communication.email.send`; it does not define the capability as SES.
- **Integration Before Innovation:** existing OpenClaw Teams, Microsoft application infrastructure, OpenBao, Central Orchestrator, and CAP-007 were reused; no bespoke Teams-to-SES script was introduced.
- **Separation of Responsibilities:** transport, identity enrichment, authority, orchestration, secret resolution, provider execution, and response rendering remain distinct.
- **Explainability/Auditability:** named stages, durable state, safe event evidence, and mailbox digest permit independent review.
- **Institutional Memory/Living Documentation:** runbooks, deployment records, proof records, and this checkpoint were updated as part of the implementation work.
- **Trust:** multiple fail-closed conditions were observed and corrected without weakening the architecture.

## Current Documentation Set For This Capability

- `01-Foundation/J-002-Constitution.md`
- `07-Operations/CAP-007-AWS-SES-Activation-Runbook.md`
- `07-Operations/CAP-007-Live-Pilot-Proof-2026-08-11.md`
- `07-Operations/INF-010-Microsoft-Cloud-Deployment-Checklist.md`
- `07-Operations/Jason-Secret-Provider-Deployment-Record.md`
- `08-Session-Records/Teams-CAP-007-End-to-End-Operational-Proof-2026-08-11.md`
- `08-Session-Records/CURRENT.md`

## Current Primary Workstream

### Release validation and merge of the governed runtime service workstream

Immediate next steps:

1. synchronize the physical host to the latest feature-branch documentation commits;
2. run the broad repository validation/CI-representative test set;
3. inspect Git diff/branch divergence and ensure the worktree is clean;
4. open or update the feature PR to `main` with explicit constitutional review and evidence references;
5. review CI results and governance-sensitive diffs;
6. merge only after green validation;
7. update this checkpoint with authoritative `main` commit/PR metadata after merge.

Do not perform another live consequential send merely to prove the same path. Additional live sends require a new operational purpose and fresh governed execution.

## Provider Authority Rule

Authority is assigned by **resource domain and attribute**, not by one globally authoritative provider.

For Microsoft identity enrichment, Microsoft Graph is authoritative only for the approved external directory attributes returned from the authenticated tenant/object lookup. Jason remains authoritative for internal identity binding, client boundary, policy, approval, capability resolution, and execution authority.

For RMM-managed devices, Datto RMM remains the authoritative external provider for managed-device existence and operational identity while IT Glue remains a documentation observation.

## Interaction Rules For Future Sessions

- Continue Jason in larger workstreams/batches; do not default to one-command-at-a-time guidance unless a host-sensitive step requires it.
- Treat this checkpoint, current GitHub state, applicable ADRs/runbooks, and a fresh host snapshot together as authoritative resume context.
- Reconcile conflicts between checkpoint/GitHub/host state before destructive or security-sensitive changes.
- Agents never invoke or communicate with other agents directly; all coordination goes through the Central Orchestrator.
- Preserve identity-first authorization, policy-as-data, versioned workflows/prompts/policies, provider-neutral capability boundaries, centralized evidence by reference, event-based auditability, and integrate-before-innovate.
- Never expose OpenBao tokens, unseal shares, passwords, API keys, bootstrap credentials, RoleIDs, SecretIDs, OAuth bearer tokens, Microsoft access tokens, private signing keys, private certificate keys, or secret values in chat, repository content, logs, or evidence.
