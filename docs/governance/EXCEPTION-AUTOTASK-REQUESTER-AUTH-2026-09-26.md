# J-405 Exception — Temporary Autotask Jason-Managed Requester Authorization

**Status:** Retired 2026-09-26; superseded by ADR-011 permanent requester-authorization architecture
**Effective date:** 2026-09-11  
**Formalization date:** 2026-09-26  
**Review no later than:** 2026-10-15  
**Approving authority:** AOT Infrastructure Owner / Jason Architecture Authority  
**Governing authority:** Jason Constitution; J-405 Platform Integrity and Boundary Enforcement  
**Affected system/provider:** Autotask read-only governed provider path  
**Affected capability class:** Registered Autotask provider-neutral read capabilities only  
**Write authority:** Not granted by this exception

## Exact requirement being excepted

Jason's preferred platform-integrity posture is provider-native or delegated requester authorization at the provider boundary where practical. Autotask provider-native requester impersonation currently fails with HTTP 500 after unique requester identity mapping succeeds.

The temporary exception permits:

`JASON_AUTOTASK_REQUESTER_AUTH_MODE=jason_managed`

for governed Autotask reads.

## Business / technical justification

The compatibility mode restores required read availability without broadening Autotask Add/Edit/Delete permission or converting the API-only integration identity into requester release authority.

## Scope

This exception applies only to:
- governed Autotask reads using registered provider-neutral capabilities;
- the existing dedicated Autotask API-only read credential boundary;
- authenticated Jason requesters who independently satisfy Jason identity, authority, client/tenant scope, observe-only mode, information-release authorization, and Central Orchestrator execution.

It does not apply to provider writes, direct provider access, arbitrary HTTP, unregistered capabilities, or release of information that Jason cannot independently authorize.

## Risk

The provider performs the fetch under the API-only service identity instead of provider-native requester impersonation. If Jason's independent requester-release boundary failed, provider fetch authority could otherwise be broader than the human requester's business authority.

## Compensating controls

- authenticated Microsoft/Jason human binding required;
- JKD-001 authority decision required;
- validated authority context required;
- observe-only permission mode for this compatibility path;
- client/tenant scope preserved;
- Central Orchestrator remains mandatory;
- information-release authorization remains mandatory;
- sensitivity/derived-output controls remain active;
- unknown requester mode values fail closed;
- provider writes use separate credentials, profiles, exact grants, approvals, execution-plan binding, and readback verification;
- live MCP direct provider access remains disabled.

## Evidence / audit

Primary evidence:
- `docs/operations/Provider-Read-Governed-Catalog-Activation.md`;
- `docs/operations/Jason-Production-Status-2026-09-14.md`;
- GitHub #175;
- provider-read authority and information-release regression tests;
- live MCP governance status showing Central Orchestrator execution and `direct_provider_access=false`.

## Retirement decision — 2026-09-26

The exception is retired by ADR-011. J-405 now explicitly separates provider FETCH authority from requester USE / PROCESS / RELEASE authority and permits Jason-managed requester authorization when provider-native requester execution is unavailable, unreliable, or unsuitable for the read path.

Current Autotask production evidence shows requester-impersonated reads are not reliable in the AOT environment, while the dedicated API-only service identity can fetch the same evidence. Jason therefore retains `jason_managed` as the accepted read architecture under ADR-011, with trusted Microsoft identity binding, JKD-001, validated authority context, client scope, observe-only permission, Central Orchestrator, information-release controls, sensitivity handling, and fail-closed behavior.

Autotask write paths remain separate and retain dedicated write credentials, provider impersonation where required, approvals, execution-plan binding, and post-write verification.

Provider-native requester impersonation may be reintroduced for reads later after bounded acceptance, but it is no longer a prerequisite for constitutional compliance.

## Constitutional effect

Retiring this exception grants no new business, provider, client, write, or autonomous authority. It replaces a temporary exception with the canonical governed architecture defined by ADR-011.
