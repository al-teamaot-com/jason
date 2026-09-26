# ADR-011 — Provider Read Requester Authorization

**Status:** Accepted  
**Date:** 2026-09-26  
**Authority:** Jason Constitution; J-405 Platform Integrity and Boundary Enforcement  
**Decision owner:** AOT Infrastructure Owner / Jason Architecture Authority

## Context

Provider fetch authority and human requester authority are not the same thing.

Some provider APIs support requester impersonation or delegated execution. Others expose only service/API-key access plus resource restriction metadata. Provider-native requester enforcement can also be technically supported but unreliable for a particular read path.

Autotask REST access is performed by an API-only identity. Its documented impersonation capability exists, but bounded AOT production proof established that requester mapping succeeds while requester-impersonated Ticket and Company reads return provider HTTP 500. The equivalent service-account reads succeed.

IT Glue API access is API-key based. IT Glue exposes resource restriction and resource-access evidence for restricted objects, but no accepted durable mechanism has been established to execute arbitrary API reads as the authenticated Microsoft/Jason requester.

Jason already owns the constitutional identity, business-authority, client-scope, orchestration, information-release, sensitivity, audit, and evidence boundaries. Technical provider access never creates business authority.

## Decision

Jason adopts a tiered provider-read requester-authorization model.

### 1. Provider-native requester enforcement

Use provider-native impersonation/delegation when all of the following are true:

- the provider exposes a supported requester-specific mechanism for the required read;
- the requester can be mapped from stable authenticated identity without making mutable aliases root authority;
- bounded acceptance proves the mechanism is reliable for the exact operation;
- provider-native enforcement does not require widening unrelated provider privileges.

A positive or negative provider-native requester decision is authoritative and may only narrow Jason release authority, never widen it.

### 2. Provider ACL / restriction mirroring

When a provider returns resource-specific ACL/restriction evidence, Jason shall evaluate that evidence before release.

For restricted resources:

- positive ACL evidence is required to release protected content;
- an explicit ACL denial is authoritative;
- missing or unverifiable ACL evidence does not become requester authority by fallback;
- provider ACL material may be removed from the final response after it has served the authorization decision.

### 3. Jason-managed requester authorization

When provider-native requester execution is unavailable, unreliable, or unsuitable for the read path, Jason may fetch using a dedicated least-privileged service/API identity and independently authorize USE / PROCESS / RELEASE.

Jason-managed release requires, at minimum:

- authenticated requester identity;
- stable Microsoft tenant/object to Jason identity binding for human requesters;
- positive JKD-001 authority;
- validated authority context;
- exact client/tenant scope;
- observe-only permission for read compatibility paths;
- Central Orchestrator execution;
- registered provider-neutral capability;
- information-release authorization;
- sensitivity/derived-output controls;
- audit/evidence correlation;
- fail-closed behavior on unknown/ambiguous requester authority.

Service-account FETCH authority never implies requester RELEASE authority.

### Provider-specific application

#### Autotask reads

`JASON_AUTOTASK_REQUESTER_AUTH_MODE=jason_managed` is an accepted production read mode, not a temporary constitutional exception.

Autotask reads remain governed by the Jason-managed release requirements above.

Autotask writes are separate: they continue to use their dedicated write identities/profiles and provider impersonation where required by the governed mutation design. This ADR grants no write authority and does not weaken approval, execution-plan binding, or readback verification.

Provider-native Autotask requester impersonation may be reintroduced for reads only after bounded acceptance proves it reliable. Its future availability is an optimization/defense-in-depth improvement, not a prerequisite for constitutional read authorization.

#### IT Glue reads

Jason-managed requester authorization is an accepted production read mode for provider-neutral IT Glue reads.

Provider-native IT Glue restriction evidence remains authoritative.

For restricted document content and document attachments, release requires positive provider ACL evidence. An explicit denial, missing ACL evidence, unknown restriction state, or inability to establish the requester in the provider ACL fails closed for protected content.

Non-document IT Glue read output remains subject to client scope, information-release authorization, sensitivity controls, and credential-like field sanitization.

### Identity aliases

Microsoft tenant/object identity is the stable requester identity. Email/UPN values are mapping/profile attributes only.

A mutable alias may assist a provider ACL comparison only after it comes from a trusted active identity binding. Caller-supplied aliases must never override the trusted binding.

## Consequences

- Provider limitations do not force Jason to broaden provider permissions or create undocumented side paths.
- Provider-native enforcement remains preferred where it is supported, reliable, and useful.
- Jason remains the authoritative business-information release boundary.
- Provider restriction evidence remains a one-way narrowing control.
- Autotask and IT Glue temporary requester-authorization exceptions may be retired after regression and bounded production evidence confirm this ADR's invariants.
- This decision does not authorize writes, direct provider access, cross-client release, or bypass of Central Orchestrator governance.

## Verification requirements

Certification must prove:

- service-account fetch cannot become human release without positive requester authority;
- missing/ambiguous trusted identity fails closed;
- cross-client release fails closed;
- Autotask writes retain their independent impersonation/governed mutation path;
- restricted IT Glue content cannot be released without positive ACL evidence;
- explicit IT Glue ACL denial is never overridden;
- sensitive/credential-like material remains derived-only or redacted as designed;
- direct provider access remains disabled at the MCP boundary.
