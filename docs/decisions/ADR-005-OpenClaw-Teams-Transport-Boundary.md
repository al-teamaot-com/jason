# ADR-005 — OpenClaw Teams Transport Boundary

**Status:** Accepted for outbound/proactive Teams transport; **superseded for ordinary inbound Teams ingress by ADR-009 as of 2026-08-15**  
**Decision owner:** Jason Architecture Authority  
**Date:** 2026-08-10  
**Updated:** 2026-08-15

> **Supersession boundary:** ADR-009 now controls ordinary inbound Microsoft Teams conversation ingress. Statements below that describe OpenClaw as the inbound owner are historical architecture for that path. This ADR remains controlling for the approved OpenClaw outbound/proactive transport boundary until that function is separately replaced or retired.

## Context

Jason already contains provider-neutral approval request, audit, Microsoft identity binding, Teams card rendering, authenticated ingress, approval authorization, replay protection, and orchestration foundations.

During live-deployment preparation on 2026-08-10, the existing Teams delivery runtime was found to use Microsoft Graph application credentials for ordinary Teams channel message posting. Microsoft's permission model does not make ordinary app-only channel posting an appropriate production path for Jason approvals; the app-only permission available for that endpoint is intended for migration scenarios.

The Jason host already runs OpenClaw and its Microsoft Teams channel supplies transport capabilities useful for proactive Teams delivery, Adaptive Cards, sender/team/channel allowlists, and a supported Gateway `send` boundary with idempotency and delivery identifiers.

Subsequent 2026-08-15 production work proved that OpenClaw could not reliably guarantee exclusive ownership of ordinary inbound Jason-bound Teams turns before its own model path. ADR-009 therefore replaced OpenClaw as the ordinary inbound Teams transport owner while preserving the outbound/proactive boundary documented here.

## Decision

For approved **outbound/proactive Teams delivery**, Jason may use OpenClaw as a Microsoft Teams transport/interface provider.

The outbound flow is:

`Central Orchestrator -> approval/communication service -> Jason Teams adapter -> OpenClaw Gateway -> Teams -> Human`

Ordinary inbound Teams conversation ingress is now governed by ADR-009:

`Teams -> direct Jason Teams Gateway -> signed trusted ingress -> Jason runtime -> Central Orchestrator`

OpenClaw MUST NOT:

- decide whether a response constitutes valid approval;
- assign Jason organization or tenant scope;
- map a Microsoft principal directly to execution authority;
- bypass JKD-001, approval policy, replay controls, or the Central Orchestrator;
- call Jason agents or connectors outside the orchestrator;
- become the canonical store of approval authority.

Jason MUST:

- resolve an organization-scoped OpenClaw Teams delivery target for approved outbound/proactive messaging;
- use deterministic approval-delivery idempotency where applicable;
- expose only approved non-secret approval metadata in the card;
- treat OpenClaw message/conversation identifiers as transport evidence only;
- preserve immutable audit and replay protections;
- keep ordinary inbound Teams routing on the ADR-009 direct gateway unless a later governed decision replaces it.

## Constitution / Canon review

This design remains consistent with:

- **Human Governance** — human-approved policy remains governing authority;
- **Evidence Before Assertion** — transport/authentication evidence is verified before Jason accepts a response;
- **Separation of Responsibilities** — transport remains separate from Jason identity/authority/policy/orchestration;
- **Vendor Independence** — OpenClaw is replaceable and is not embedded into Jason Core;
- **Institutional Memory** — the decision and later supersession boundary are recorded durably.

The architectural rule "OpenClaw is an interface, not an authority" remains controlling.

## Integration boundary

For outbound delivery, Jason integrates to supported OpenClaw Gateway/channel capabilities rather than importing OpenClaw TypeScript modules by filesystem path or broadening admin RPC merely for message delivery.

For inbound ordinary Teams turns, Jason no longer depends on OpenClaw hooks, plugin claims, or OpenClaw model lifecycle. ADR-009 owns that boundary.

## Consequences

### Positive

- avoids inappropriate Microsoft Graph migration permissions for ordinary outbound channel posting;
- preserves certificate-based Graph authentication for capabilities that require it;
- keeps OpenClaw replaceable behind a Jason adapter;
- preserves existing approval/proactive messaging work;
- allows inbound Teams to use a simpler exclusive Jason-owned gateway without discarding approved outbound OpenClaw capabilities.

### Costs / constraints

- outbound/proactive delivery still depends on the OpenClaw Teams provider and conversation/bootstrap state;
- OpenClaw Gateway contract changes remain a provider-version dependency monitored by Technology Steward governance;
- inbound and outbound Teams paths are now intentionally different and must not be conflated operationally;
- disabling OpenClaw's internal `msteams` provider requires review of outbound/proactive dependencies first.

## Rejected alternatives

1. **Microsoft Graph app-only ordinary channel POST** — rejected because it would require an inappropriate permission model for normal approval messaging.
2. **Delegated service-account workaround** — rejected because it adds standing human-like delegated identity and operational fragility merely to transport approvals.
3. **Direct import of OpenClaw internal TypeScript modules** — rejected because it tightly couples Jason to implementation internals rather than a supported provider boundary.
4. **Expanding OpenClaw Admin HTTP RPC to expose arbitrary send/session methods** — rejected because the normal Gateway already supplies the required outbound capability.
5. **OpenClaw as ordinary inbound Jason ingress after 2026-08-15** — rejected/superseded by ADR-009 after live evidence showed exclusive pre-model turn ownership could not be guaranteed reliably.

## Retirement criteria

Revisit the remaining outbound/proactive portion of this ADR when any of the following becomes true:

- OpenClaw removes or materially changes its supported Gateway/channel transport contract;
- Microsoft introduces a narrower, appropriate Teams transport that materially simplifies Jason without weakening governance;
- Jason adopts a different standard communications transport provider;
- OpenClaw can no longer meet Jason audit, tenant-boundary, or security requirements;
- ADR-009's direct gateway or another governed adapter gains an approved outbound/proactive path that safely replaces OpenClaw.
