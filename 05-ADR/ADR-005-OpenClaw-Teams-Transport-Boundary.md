# ADR-005 — OpenClaw Teams Transport Boundary

**Status:** Accepted for implementation  
**Decision owner:** Jason Architecture Authority  
**Date:** 2026-08-10

## Context

Jason already contains provider-neutral approval request, audit, Microsoft identity binding, Teams card rendering, authenticated ingress, approval authorization, replay protection, and orchestration foundations.

During live-deployment preparation on 2026-08-10, the existing Teams delivery runtime was found to use Microsoft Graph application credentials for ordinary Teams channel message posting. Microsoft's permission model does not make ordinary app-only channel posting an appropriate production path for Jason approvals; the app-only permission available for that endpoint is intended for migration scenarios.

The Jason host already runs OpenClaw and its Microsoft Teams channel supplies the transport capabilities Jason needs: proactive Teams delivery, Adaptive Cards, authenticated inbound Bot Framework activities, sender/team/channel allowlists, and a supported Gateway `send` boundary with idempotency and delivery identifiers.

## Decision

Jason will use OpenClaw as the Microsoft Teams **transport/interface provider** for governed approval delivery and response ingress.

The authority flow is:

`Human -> Teams -> OpenClaw transport -> Jason ingress -> JKD-001 / approval policy -> Central Orchestrator`

The outbound flow is:

`Central Orchestrator -> approval service -> Jason Teams adapter -> OpenClaw Gateway -> Teams -> Human`

OpenClaw MUST NOT:

- decide whether a response constitutes valid approval;
- assign Jason organization or tenant scope;
- map a Microsoft principal directly to execution authority;
- bypass JKD-001, approval policy, replay controls, or the Central Orchestrator;
- call Jason agents or connectors outside the orchestrator;
- become the canonical store of approval authority.

Jason MUST:

- resolve an organization-scoped OpenClaw Teams delivery target;
- use a deterministic approval-delivery idempotency key;
- expose only approved non-secret approval metadata in the card;
- treat OpenClaw message/conversation identifiers as transport evidence only;
- require authenticated Microsoft identity evidence on inbound interaction;
- re-bind tenant and Microsoft object identity to Jason organization/identity records;
- perform provider-neutral approval authorization before creating execution authority;
- preserve immutable audit and replay protections.

## Constitution / Canon review

This design was explicitly reviewed against the Jason Constitution/Canon on 2026-08-10 and found consistent with:

- **Human Governance** — human-approved policy remains governing authority;
- **Evidence Before Assertion** — transport/authentication evidence is verified before Jason accepts a response;
- **Separation of Responsibilities** — OpenClaw owns transport, Jason owns identity/authority/policy/orchestration;
- **Vendor Independence** — the OpenClaw boundary is replaceable and is not embedded into Jason Core;
- **Institutional Memory** — the decision and operational reasoning are recorded durably.

The architectural rule "OpenClaw is an interface, not an authority" remains controlling.

## Integration boundary

Jason integrates to the supported OpenClaw Gateway capability rather than importing OpenClaw TypeScript modules by filesystem path or expanding the Admin HTTP RPC allowlist merely for message delivery.

The OpenClaw Gateway `send` path provides channel selection, outbound target resolution, idempotency/deduplication, durable delivery, and delivery identifiers. Jason consumes only the minimum receipt fields needed for audit correlation.

## Consequences

### Positive

- avoids a duplicate Teams bot stack;
- avoids inappropriate Microsoft Graph migration permissions;
- preserves certificate-based Graph authentication for the Graph capabilities that actually require it;
- keeps Teams/OpenClaw replaceable behind a Jason adapter;
- aligns with integrate-before-innovate;
- preserves existing approval backend work rather than replacing it.

### Costs / constraints

- Jason needs a thin OpenClaw Gateway adapter and organization-scoped target binding;
- live proactive delivery requires OpenClaw to possess a valid stored Teams conversation reference;
- inbound Adaptive Card actions must continue through Jason identity and approval authorization even though OpenClaw already authenticates the Bot Framework activity;
- OpenClaw Gateway contract changes must be treated as a provider-version dependency and monitored by Technology Steward governance.

## Rejected alternatives

1. **Microsoft Graph app-only ordinary channel POST** — rejected because it would require an inappropriate permission model for normal approval messaging.
2. **Delegated service-account workaround** — rejected because it adds standing human-like delegated identity and operational fragility merely to transport approvals.
3. **Second custom Teams bot stack inside Jason** — rejected because OpenClaw already supplies the required transport and duplicating it violates integrate-before-innovate.
4. **Direct import of OpenClaw internal TypeScript modules** — rejected because it tightly couples Jason to implementation internals rather than a supported provider boundary.
5. **Expanding OpenClaw Admin HTTP RPC to expose arbitrary send/session methods** — rejected because the normal Gateway already supplies the required capability and broadening an admin surface is unnecessary.

## Retirement criteria

Revisit this ADR when any of the following becomes true:

- OpenClaw removes or materially changes its supported Gateway/channel transport contract;
- Microsoft introduces a narrower, appropriate app-only Teams approval-message transport that materially simplifies Jason without weakening governance;
- Jason adopts a different standard communications transport provider;
- OpenClaw can no longer meet Jason audit, tenant-boundary, or security requirements.
