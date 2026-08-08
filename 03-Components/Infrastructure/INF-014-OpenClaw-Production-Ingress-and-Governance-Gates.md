# INF-014 — OpenClaw Production Ingress and Governance Gates

## Status

Draft implementation foundation.

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
6. dispatch only a registered named capability;
7. record significant decisions/outcomes with the existing correlation ID;
8. return a sanitized structured response.

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
- the requested capability is not registered.

## Audit requirements

At minimum, correlated audit evidence should identify:

- transport authentication outcome and machine identity reference;
- request and correlation IDs;
- principal, organization, client, capability, and requested mode;
- authority decision;
- each material governance decision or summarized decision reference;
- dispatch outcome;
- sanitized failure classification;
- evidence/artifact references when material.

Secret values, signatures, bearer tokens, private keys, and protected raw payloads must never be written to normal audit output.

## Synthetic validation

The no-provider synthetic path must prove:

1. an authenticated fresh request can reach a synthetic registered capability;
2. invalid machine authentication never reaches dispatch;
3. an expired request never reaches dispatch;
4. replayed request IDs never reach a second dispatch;
5. authority denial never reaches dispatch;
6. policy denial never reaches dispatch;
7. approval-required outcomes stop before dispatch;
8. arbitrary HTTP targets and unknown capabilities fail closed.

No external provider credential is required for this validation.

## Explicit non-goals

This foundation does not:

- grant OpenClaw direct provider access;
- create new autonomous review agents;
- allow agents to communicate directly;
- choose a permanent production transport vendor or protocol;
- introduce provider API credentials;
- enable mutation/remediation authority.

## Next deployment work

After this foundation passes CI:

1. bind `TransportAuthenticator` to the approved OpenClaw machine-identity mechanism;
2. bind the policy evaluator to the Central Orchestrator governance gate chain;
3. bind replay/idempotency to durable storage;
4. bind audit output to Jason's governed audit/evidence path;
5. run the synthetic path against the deployed OpenClaw/Jason boundary before enabling any live provider capability through OpenClaw.
