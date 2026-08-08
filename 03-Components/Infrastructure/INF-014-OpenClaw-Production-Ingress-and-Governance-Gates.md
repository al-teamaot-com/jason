# INF-014 — OpenClaw Production Ingress and Governance Gates

## Status

Draft implementation foundation with runtime bindings.

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

The branch includes three production-oriented adapters that require no provider credentials:

- `JasonAuthorityEvaluator` binds the OpenClaw request identity/scope to a Jason authority-service protocol and fails closed on unknown decisions.
- `GateChainPolicyEvaluator` maps the Central Orchestrator governance gate-chain result to the OpenClaw policy contract.
- `OpenClawOrchestratorDispatcher` translates only explicitly versioned capabilities into `OrchestrationRequest` objects for the real `CentralOrchestrator` interface.

The dispatcher deliberately sets `approval_present=False`. OpenClaw cannot manufacture or infer human approval from a requested mode. A future approval-record binding must supply verified approval state through a governed Jason service before an approval-required execution can proceed.

The branch also includes `SQLiteReplayStore`, which provides durable request-ID replay protection across process restarts. The deployment path may later replace SQLite behind the same `ReplayStore` contract without changing OpenClaw capability logic.

## Production transport contract

The implementation intentionally depends on a `TransportAuthenticator` abstraction rather than choosing mTLS, signed requests, or another machine-identity mechanism inside the architecture.

Production deployment must bind that abstraction to an approved mechanism with:

- a dedicated OpenClaw machine identity;
- short-lived or rotatable credentials retrieved through the Secrets Broker;
- authenticated integrity protection;
- request timestamps and expiry;
- unique nonce/request identity;
- replay rejection;
- no credentials in prompts or capability arguments.

## Fail-closed behavior

The request must not reach capability dispatch when:

- machine authentication fails;
- freshness metadata is absent or invalid;
- a request is expired or not yet valid beyond permitted clock skew;
- a request ID has already been claimed;
- capability syntax is invalid or arbitrary HTTP is requested;
- authority denies the principal/client/capability combination;
- any governance gate denies;
- a gate or authority requires human approval and no recorded approval exists;
- the requested capability is not explicitly version-bound for orchestration.

## Audit requirements

At minimum, correlated audit evidence should identify:

- transport authentication outcome and machine identity reference;
- request and correlation IDs;
- principal, organization, client, capability, and requested mode;
- authority decision;
- each material governance decision or summarized decision reference;
- orchestration execution ID and dispatch outcome;
- sanitized failure classification;
- evidence/artifact references when material.

Secret values, signatures, bearer tokens, private keys, and protected raw payloads must never be written to normal audit output.

## Synthetic validation

The no-provider synthetic path must prove:

1. an authenticated fresh request can reach a synthetic registered capability;
2. invalid machine authentication never reaches dispatch;
3. an expired request never reaches dispatch;
4. replayed request IDs remain rejected across replay-store instances;
5. authority denial never reaches dispatch;
6. policy denial never reaches dispatch;
7. approval-required outcomes stop before dispatch;
8. arbitrary HTTP targets and unknown capabilities fail closed;
9. identity, organization, client, correlation, capability, mode, and arguments are preserved into the real `OrchestrationRequest` contract;
10. OpenClaw never self-asserts approval.

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

After the runtime-binding CI passes:

1. choose and bind the production `TransportAuthenticator` mechanism (prefer short-lived machine identity with signed requests or mTLS rather than a static shared secret);
2. bind `IdentityAuthorityService` to Jason's production identity/authority implementation;
3. bind verified approval-record lookup into the orchestrator path rather than request payloads;
4. bind ingress/audit output to Jason's governed event/evidence store;
5. select the production location and retention policy for replay/idempotency state;
6. run the full synthetic path against the deployed OpenClaw/Jason boundary before enabling any live provider capability through OpenClaw.
