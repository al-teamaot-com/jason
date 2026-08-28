# INF-014 — OpenClaw Production Ingress and Governance Gates

## Status

Draft implementation foundation with runtime bindings and a concrete signed-transport reference implementation.

## Purpose

Define and implement the production boundary by which OpenClaw may request Jason capabilities without becoming an authority, a provider client, or an orchestration peer.

## Constitutional alignment

This component exists to enforce J-002 Articles II, III, IV, VI, VIII, IX, XIII, XVI, XVII, and XVIII at ingress.

OpenClaw is an ingress client. It is not the Central Orchestrator, a policy authority, or an agent-to-agent routing fabric.

## Mandatory request path

1. authenticate the OpenClaw machine identity at the transport boundary;
2. validate request freshness, expiry, nonce presence, and replay identity;
3. validate the structured capability-request contract;
4. evaluate human/principal authority and exact organization/client scope;
5. evaluate the centrally ordered governance gate chain;
6. translate only a registered named capability into a real `OrchestrationRequest`;
7. let the Central Orchestrator resolve policy/provider execution and invoke the capability;
8. record significant decisions/outcomes with the existing correlation ID;
9. return a sanitized structured response.

No step may be skipped because a caller is trusted, internal, or AI-assisted.

## Canonical governance gates

The initial focused gate registry is:

- Security
- Compliance
- Privacy
- Business Authority
- Communications
- Evidence Quality
- Rollback / Reversibility
- Human Approval

These are policy/evaluation components, not autonomous agents. Each gate has one responsibility and returns a structured allow, deny, or approval-required decision. Gates do not call providers, capabilities, agents, or other gates. The Central Orchestrator owns ordering and final assembly.

A specialized reasoning agent may later support a gate only when deterministic policy evaluation is insufficient. Such an agent remains advisory: it returns structured findings to the orchestrator and receives no independent execution authority.

## Runtime bindings now implemented

The branch includes production-oriented adapters that require no provider credentials:

- `JasonAuthorityEvaluator` binds the OpenClaw request identity/scope to a Jason authority-service protocol and fails closed on unknown decisions.
- `GateChainPolicyEvaluator` maps the Central Orchestrator governance gate-chain result to the OpenClaw policy contract.
- `OpenClawOrchestratorDispatcher` translates only explicitly versioned capabilities into `OrchestrationRequest` objects for the real `CentralOrchestrator` interface.
- `SQLiteReplayStore` provides durable request-ID replay protection across process restarts.
- `SQLiteIngressSecurityAudit` stores pre-orchestration transport-security events separately from the canonical orchestration event store because untrusted transport failures do not yet possess a trusted principal/capability context.

The dispatcher deliberately sets `approval_present=False`. OpenClaw cannot manufacture or infer human approval from a requested mode. A future approval-record binding must supply verified approval state through a governed Jason service before an approval-required execution can proceed.

## Signed transport reference implementation

`Ed25519TransportAuthenticator` is the first concrete `TransportAuthenticator` implementation.

It uses asymmetric application-layer signing:

- the OpenClaw host retains the Ed25519 private signing key;
- Jason stores/registers only the corresponding public key and key ID;
- the signature covers the canonical request envelope, including identity scope, capability, arguments, timestamps, expiry, nonce, and key ID;
- payload tampering invalidates the signature;
- unknown key IDs fail closed;
- signatures and private-key material are never written to audit output.

Ed25519 is a deployment choice, not an architectural dependency. The `TransportAuthenticator` contract remains replaceable by mTLS or another approved machine-identity implementation.

## Production transport requirements

Production deployment must use:

- a dedicated OpenClaw machine identity;
- a rotatable asymmetric signing key or an equivalent short-lived machine-identity mechanism;
- authenticated integrity protection;
- request timestamps and expiry;
- unique nonce/request identity;
- durable replay rejection;
- no credentials in prompts or capability arguments.

The OpenClaw private signing key must be generated/stored on the OpenClaw side through the approved secret boundary. Jason needs only the public verification key; public-key fingerprints should be retained as deployment evidence.

## Fail-closed behavior

The request must not reach capability dispatch when:

- machine authentication/signature validation fails;
- the signing key ID is unregistered;
- freshness metadata is absent or invalid;
- a request is expired or not yet valid beyond permitted clock skew;
- a request ID has already been claimed;
- capability syntax is invalid or arbitrary HTTP is requested;
- authority denies the principal/client/capability combination;
- any governance gate denies;
- a gate or authority requires human approval and no recorded approval exists;
- the requested capability is not explicitly version-bound for orchestration.

## Audit requirements

Pre-orchestration security events and trusted orchestration events have distinct storage contracts.

Pre-orchestration audit may record:

- transport authentication outcome;
- request/correlation IDs supplied by the caller;
- registered machine-identity reference when authentication succeeds far enough to establish it;
- sanitized denial reason.

It must not invent a trusted principal, capability, or execution ID merely to fit the orchestration event schema.

After the structured request is trusted, correlated audit evidence should identify principal, organization, client, capability, requested mode, authority/gate decisions, orchestration execution ID, dispatch outcome, sanitized failure classification, and evidence/artifact references when material.

Secret values, signatures, bearer tokens, private keys, and protected raw payloads must never be written to normal audit output.

## Synthetic validation

The no-provider synthetic path must prove:

1. a valid Ed25519 signature resolves only a registered OpenClaw machine identity;
2. payload tampering fails authentication;
3. invalid/unknown signing keys never reach dispatch;
4. an expired request never reaches dispatch;
5. replayed request IDs remain rejected across replay-store instances;
6. authority denial never reaches dispatch;
7. policy denial never reaches dispatch;
8. approval-required outcomes stop before dispatch;
9. arbitrary HTTP targets and unknown capabilities fail closed;
10. identity, organization, client, correlation, capability, mode, and arguments are preserved into the real `OrchestrationRequest` contract;
11. OpenClaw never self-asserts approval;
12. pre-orchestration audit survives restart and strips secret/signature fields.

No external provider credential is required for this validation.

## Explicit non-goals

This foundation does not:

- grant OpenClaw direct provider access;
- create new autonomous review agents;
- allow agents to communicate directly;
- introduce provider API credentials;
- enable mutation/remediation authority;
- permit OpenClaw to assert or synthesize approval records.

## Next deployment work

After CI passes:

1. bind `IdentityAuthorityService` to Jason's production identity/authority implementation;
2. bind verified approval-record lookup into the orchestrator path rather than request payloads;
3. decide production paths/retention for ingress security audit and replay state;
4. generate a dedicated OpenClaw Ed25519 machine keypair through the governed secret workflow, retaining only the public key/fingerprint on Jason;
5. wire OpenClaw request signing to the canonical envelope format;
6. run the full synthetic signed request against the deployed OpenClaw/Jason boundary before enabling any live provider capability through OpenClaw.
