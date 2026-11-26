# Project Jason — Risk-Based Independent Review Policy

**Status:** Authoritative release-review policy
**Effective target:** next governed production release after Owner approval
**Date:** 2026-11-10

## Purpose

Independent review is a control for **material security or authority change**, not a ritual attached to every release or every file whose path contains release/governance code.

Protected CI, targeted regression, production-equivalent preproduction, exact Owner release authorization, serialized production mutation, rollback readiness, and post-deployment verification remain mandatory under the Minimal Production Release contract.

This policy supersedes older generic statements that every high-risk-looking or PMV3/release-related change automatically requires a separate independent security review.

## Independent review is required when a change materially alters any of these boundaries

1. **Authority / identity**
   - who may request, approve, administer, impersonate, or execute;
   - approval acceptance, issuer, verifier, binding, replay, expiry, or delegation semantics;
   - standing capability-grant scope or privilege expansion.

2. **Cryptography / trusted evidence**
   - signing or verification algorithms;
   - trusted keys, trust roots, key registries, signed evidence formats;
   - authentication provenance or anti-forgery/replay contracts.

3. **Root / credential / secret boundary**
   - new or expanded root/sudo privilege;
   - new privileged systemd execution;
   - credential, token, secret-provider or secret-mount behavior;
   - new path from ordinary service identity to privileged host mutation.

4. **Tenant / client / information-release isolation**
   - cross-tenant or cross-client matching;
   - requester/client scope rules;
   - sensitive information-release decisions;
   - client-visible communication authority expansion.

5. **Release break-glass / protection boundary**
   - branch-protection bypass;
   - release-lock bypass;
   - circuit-breaker override;
   - rollback/LKG trust weakening;
   - emergency/break-glass authority expansion.

6. **Provider write expansion**
   - a new provider write capability;
   - widening targets, organizations, clients, or action classes;
   - moving an action from approval-required to standing/unattended authority;
   - newly autonomous disruptive behavior.

If any of these applies, independent review is mandatory before production authorization. If classification is genuinely ambiguous, classify as review-required.

## Independent review is not required merely because

- a file is part of PMV3, Release Manager, Teams approval, or another historically sensitive subsystem;
- the existing release risk classifier labels the candidate `production_control_core`;
- the release changes tests, documentation, observability, error handling, retry behavior, performance, or implementation details without altering a protected boundary above;
- a bug fix preserves the exact current authority/identity/tenant/root/provider-write contract;
- code moves or refactors while protected behavior is proven unchanged;
- an exact release is being retried without changing candidate identity or approved scope.

The file/risk classifier remains useful for selecting test depth and release evidence. It is not, by itself, a human-review requirement.

## Evidence required when independent review is not triggered

The release record must still show:

- exact protected candidate SHA;
- complete reviewed scope and manifest fingerprint;
- applicable security/regression CI;
- targeted negative tests for the changed behavior;
- production-equivalent preproduction;
- verified rollback SHA/readiness;
- one exact Owner production decision;
- serialized production mutation;
- post-deployment health, drift, functional and ticket-continuity verification.

## Evidence required when independent review is triggered

In addition to normal release evidence:

- identify the exact protected boundary being changed;
- state the prior and proposed authority/security behavior;
- include negative tests proving denied paths remain denied;
- record the independent review outcome against the exact candidate/scope;
- invalidate that review if the candidate or reviewed protected-boundary scope changes.

## No invented reviewer ceremony

Do not require a nominal second reviewer when no material protected boundary changed. Do not falsely label ordinary CI or the primary engineer's own review as an independent human review. When independent review is required, use a genuinely separate review path appropriate to the boundary.

## Relationship to Owner approval

Independent review is evidence, not a second business authorization. The Owner still makes **one exact production decision** for the release. Independent review must never create another unfreeze, CCC, deployment, or equivalent Owner approval ceremony.
