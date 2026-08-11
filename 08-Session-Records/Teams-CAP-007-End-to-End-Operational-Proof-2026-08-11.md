# Teams to CAP-007 End-to-End Operational Proof — 2026-08-11

**Environment:** Jason pilot host  
**Capability:** `communication.email.send` / CAP-007  
**Conversation transport:** OpenClaw Microsoft Teams bridge  
**Email provider:** AWS SES  
**Status:** OPERATIONAL PROOF COMPLETE FOR APPROVED PILOT SCOPE  
**Evidence date:** 2026-08-11  

## Purpose

This record preserves the first successful live end-to-end proof that an authenticated Microsoft Teams user can ask Jason to send email and that Jason resolves the authenticated human identity, applies governed authority, routes through the Central Orchestrator, invokes CAP-007, obtains provider credentials through JKD-003/OpenBao, sends through AWS SES, and returns a deterministic success response only after successful execution.

This record is intentionally non-secret. It must not contain access tokens, passwords, private keys, RoleIDs, SecretIDs, AWS credentials, OpenBao tokens, message bodies, or other secret material.

## Constitutional review

The implementation and proof were reviewed against J-002 — The Jason Constitution.

### Article II — Human Governance

- The action originated from an authenticated human request in Teams.
- Microsoft authentication established identity evidence; it did not itself grant execution authority.
- CAP-007 remained subject to Jason authority and approval controls.
- For the pilot, an authenticated imperative may be materialized as explicit per-request JKD-001 approval evidence according to the approved pilot policy. This is self-approval evidence for the authenticated principal, not an independent approver class and not a bypass of the approval system.

### Article IV — Independence and Capability Abstraction

- The conversation flow requested capability `communication.email.send` rather than calling AWS SES directly.
- Teams is transport/ingress, Microsoft Graph is identity enrichment, OpenBao is the current secret provider, and AWS SES is the current email provider.
- None of those provider identities define the capability itself.

### Article V — Integration Before Innovation

- Existing OpenClaw Teams transport was reused.
- Existing Microsoft Graph application infrastructure was reused through a governed boundary.
- Existing CAP-007 and AWS SES implementation were reused.
- No workflow-specific Teams-to-SES script was introduced.

### Article VI — Separation of Responsibilities

The observed path preserves explicit responsibility boundaries:

1. OpenClaw transports authenticated Teams conversation evidence.
2. Jason verifies the trusted OpenClaw machine boundary.
3. Jason binds Microsoft tenant/object identity to a governed Jason identity.
4. Microsoft Graph resolves the authenticated Microsoft object to a current mailbox address.
5. Conversation reasoning proposes a capability intent but cannot invoke providers or invent credentials.
6. The request factory creates governed orchestration material, including a fresh idempotency key when required.
7. JKD-001 supplies authority and approval evidence.
8. The Central Orchestrator alone resolves and invokes the capability.
9. CAP-007 performs the bounded email operation.
10. JKD-003/OpenBao resolves the SES provider credential only at the provider boundary.
11. AWS SES performs the external send.
12. The deterministic response renderer may claim success only after orchestrator success.

No agent-to-agent direct invocation path was introduced.

### Articles VIII and IX — Explainability and Auditability

- The path is decomposed into named, reviewable stages.
- Significant operations use durable Jason state and event stores.
- Provider secrets and access tokens are excluded from normal evidence.
- Mailbox evidence is retained outside Git and referenced by digest.
- The live proof distinguishes observed facts from architectural inference.

### Article XII — Institutional Memory

- The implementation history, operating constraints, live proof, provider boundary, and evidence digest are recorded centrally in project documentation.
- The binary Outlook evidence is not duplicated into Git; it is referenced by digest.

### Article XVII — Living Documentation

This record, the CAP-007 pilot record, Microsoft deployment checklist, secret-provider deployment record, and current-session checkpoint are updated as part of the same workstream rather than after the fact.

## Approved architecture

The live path is:

```text
Authenticated Teams user
        |
        v
OpenClaw Teams transport / Jason bridge
        |
        v
Jason trusted ingress + replay/security controls
        |
        v
Microsoft tenant/object identity binding
        |
        v
Validated Microsoft client boundary
        |
        v
JKD-003/OpenBao certificate credential
        |
        v
MSAL application token (memory only)
        |
        v
Microsoft Graph exact user lookup
        |
        v
Bound Jason principal with resolved mailbox address
        |
        v
Governed conversation action intent
        |
        v
JKD-001 authority + per-request pilot approval evidence
        |
        v
Central Orchestrator
        |
        v
CAP-007 communication.email.send
        |
        v
JKD-003/OpenBao SES credential
        |
        v
AWS SES
        |
        v
Deterministic Teams success response
```

## Microsoft identity boundary proof

The authenticated Microsoft identity used during the controlled proof was:

```text
Microsoft tenant ID: f7054323-d52b-4863-8c2f-1898f0b6077c
Microsoft object ID: bee80bdc-ffb0-4c50-b453-c09d4d411f5f
Jason identity: person-al
Resolved mailbox: al@teamaot.com
```

The durable Microsoft boundary used:

```text
Internal client ID: client-aot-internal
Provider: microsoft_graph
Primary domain: teamaot.com
Profile: directory-read
Application ID: c94301b7-7194-46ab-aab7-94f9366f51a9
Service principal ID: f784d32d-1d6f-4080-97d4-5efa194a14ed
Status: validated
```

The Graph application permission used for the exact user lookup is `User.Read.All`. The runtime does not require broad `Directory.Read.All` for this self-resolution path.

The live no-send container proof returned:

```text
=== JASON RUNTIME MICROSOFT SELF-RESOLUTION ===
tenant_id: f7054323-d52b-4863-8c2f-1898f0b6077c
object_id: bee80bdc-ffb0-4c50-b453-c09d4d411f5f
resolved_email: al@teamaot.com
PASS: Running jason-runtime resolved the authenticated Teams user.
PASS: Governed Microsoft boundary was enforced.
PASS: Microsoft credential came from OpenBao.
PASS: No email was sent.
```

This proved the identity path before a consequential send was attempted.

## Microsoft secret-provider proof

The canonical provider-secret lifecycle for `microsoft_graph` returned:

```text
action: verify
field_contract_valid: true
runtime_access_active: true
runtime_token_persisted: false
secret_values_printed: false
status: pass
```

The subsequent status check confirmed:

```text
logical_name: microsoft_graph.directory_read
runtime_access_active: true
secret_present: true
status: pass
```

The dedicated AppRole artifacts are stored under the protected host path:

```text
/opt/jason/bootstrap/secrets/openbao/microsoft-graph-directory-read-approle
```

Only the `role-id` and `secret-id` files are mounted read-only into the runtime at:

```text
/run/jason-secrets/openbao/microsoft-graph/role_id
/run/jason-secrets/openbao/microsoft-graph/secret_id
```

The host files remain root-owned and group-readable only by the runtime group. They are not world-readable.

## Runtime deployment proof

The production-style pilot runtime was rebuilt after wiring Microsoft identity enrichment into the governed composition.

Observed state:

```text
jason-runtime   Up ... (healthy)   jason-runtime:local
```

The runtime uses:

- read-only root filesystem;
- dropped Linux capabilities;
- `no-new-privileges`;
- non-root UID/GID 1000:1000;
- durable authority, identity-binding, replay, security-audit, orchestration-event, and client-boundary stores;
- provider-specific read-only AppRole mounts;
- local Ollama model `qwen3:1.7b` for bounded conversation reasoning;
- Central Orchestrator as the sole execution coordinator.

## OpenClaw bridge deployment proof

Before the live Teams send, the active OpenClaw extension was compared against the repository implementation.

Repository SHA-256:

```text
a9438c939d76a79c5f0113d654e1c5a47ae1e845ac1f0113ad7a2a56eb39f211
```

The active extension was initially stale. The previous active bridge was backed up, the current repository bridge was installed, and the OpenClaw gateway was restarted.

Post-restart proof:

```text
PASS: OpenClaw gateway is healthy.
a9438c939d76a79c5f0113d654e1c5a47ae1e845ac1f0113ad7a2a56eb39f211  /home/node/.openclaw/extensions/jason-bridge/index.mjs
```

The live Teams test therefore used the current repository bridge rather than a stale deployed copy.

## Live Teams execution

The authenticated operator sent this command to Jason in Microsoft Teams:

```text
send me an email
```

Jason returned a successful result indicating delivery to `al@teamaot.com` with subject `Test email from Jason` and confirmed the email capability.

The operator then supplied mailbox evidence showing the received message with subject:

```text
Test email from Jason
```

The observed mailbox receipt time was approximately 08:31 America/New_York on 2026-08-11.

This was a fresh non-idempotent governed request. It was not a replay of the earlier CAP-007 pilot execution.

## Mailbox evidence integrity

Operator-supplied Outlook evidence file:

```text
Test email from Jason.msg
```

Observed file size:

```text
113664 bytes
```

SHA-256:

```text
be2b2239dd5449f0ee085fb007bf3fb921f885e46a9b51b7a416b7ad9cef9c53
```

The binary message file is not stored in this repository. The digest permits later integrity comparison against the operator-retained evidence.

## Safety and fail-closed findings during activation

The workstream produced several useful operational findings and demonstrated safe failure behavior:

1. The canonical provider-secret lifecycle initially rejected `microsoft_graph` because no provider definition existed. The lifecycle was extended before runtime use rather than bypassed.
2. The first container self-resolution attempt failed because the root-owned AppRole files were mode `0600`. The runtime did not fall back to environment variables, local certificate files, transport data, or another secret source.
3. The AppRole file permissions were corrected to root ownership with runtime-group read access (`0640`) and a traversable protected directory (`0750`). World-readable access was not introduced.
4. A stale OpenClaw bridge deployment was detected by SHA-256 comparison before the live send. The active extension was updated and the gateway restarted before testing.
5. No automatic email retry was performed during identity/provider configuration failures.

These failures are evidence of the intended fail-closed model rather than reasons to weaken the controls.

## Data minimization and secret handling

The proof intentionally excludes:

- OpenBao administrative passwords;
- AppRole RoleIDs and SecretIDs;
- Microsoft private key or certificate contents;
- Microsoft access tokens;
- AWS access keys or session tokens;
- full message body contents;
- raw Graph responses;
- raw SES responses beyond safe operational metadata.

The Microsoft access token was acquired for application use and kept in memory. The provider-specific OpenBao token is short-lived and self-revoked by the resolver lifecycle.

## Test evidence

Before deployment, the focused governed Microsoft identity bridge and runtime composition test set passed:

```text
66 passed
```

An earlier bridge-focused set passed:

```text
61 passed
```

These tests covered Microsoft directory resolution, tenant token adaptation, certificate token handling, durable client boundaries, Teams identity binding, conversation action intent, email request creation, runtime composition, and deployment contracts.

## Operational conclusion

The approved pilot now has live evidence that the Teams conversational interface is connected to CAP-007 through Jason's governed architecture.

The previous integration gap — "Teams conversational interface is not yet connected to CAP-007" — is closed for the approved pilot scope.

The proven behavior is:

1. authenticated Teams identity is required;
2. "me" resolves from the logged-in Microsoft user, not a static email binding;
3. a validated tenant boundary is required;
4. Graph credentials come only from JKD-003/OpenBao;
5. Graph lookup is exact and read-only;
6. action intent cannot call providers directly;
7. the Central Orchestrator remains the sole execution coordinator;
8. CAP-007 remains the email capability boundary;
9. SES credentials come only from JKD-003/OpenBao;
10. success is reported only after successful governed execution;
11. mailbox receipt independently confirms delivery.

## Pilot limitations and governance notes

- The current pilot permits authenticated-imperative self-approval evidence for this capability. This must not be confused with independent approval or generalized to higher-risk actions without governance review.
- The current Microsoft application has additional Teams-related application permissions from earlier transport work. They are not required for the Graph self-user lookup and do not define the email capability.
- The Microsoft `directory-read` profile currently represents the approved exact-user lookup implementation and uses `User.Read.All`; future profile decomposition may rename it without changing the capability architecture.
- The current deployment is a single-host pilot. Remote or multi-host expansion requires the normal infrastructure/TLS/governance review.
- CAP-007 remains non-idempotent and must not be blindly retried. A failed consequential send requires a fresh governed execution unless future replay semantics are explicitly designed and approved.

## Evidence references

- Constitution: `01-Foundation/J-002-Constitution.md`
- CAP-007 activation runbook: `07-Operations/CAP-007-AWS-SES-Activation-Runbook.md`
- CAP-007 first live pilot: `07-Operations/CAP-007-Live-Pilot-Proof-2026-08-11.md`
- Microsoft deployment checklist: `07-Operations/INF-010-Microsoft-Cloud-Deployment-Checklist.md`
- Secret-provider deployment record: `07-Operations/Jason-Secret-Provider-Deployment-Record.md`
- This proof: `08-Session-Records/Teams-CAP-007-End-to-End-Operational-Proof-2026-08-11.md`

## Change rule

Any change to Teams identity evidence, tenant binding, Microsoft permission profile, Graph lookup semantics, OpenBao credential resolution, pilot approval semantics, orchestration path, CAP-007 policy, SES provider policy, success rendering, or evidence-retention requirements must be reviewed through normal Jason governance and documented in the same governed change.
