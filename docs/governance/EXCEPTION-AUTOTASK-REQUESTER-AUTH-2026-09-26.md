# J-405 Exception — Temporary Autotask Jason-Managed Requester Authorization

**Status:** Approved transitional exception; remediation tracked in GitHub #175  
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

## Review / expiration rule

This exception must be reviewed no later than 2026-10-15. At review, the Architecture Authority must either:
1. retire the exception after successful provider-native/delegated requester authorization acceptance;
2. replace it with a stronger supported provider authorization design; or
3. explicitly renew the exception with updated evidence, risk review, and a new review date.

The exception must not silently become permanent architecture.

## Retirement criteria

Retire this exception when:
- the Autotask impersonation HTTP 500 root cause is understood and corrected, or an equivalent supported delegated requester model is available;
- requester identity aliases are handled without making mutable email strings root authority;
- bounded production proof confirms provider-native/delegated requester enforcement;
- regression tests prove ambiguous or unauthorized requester mappings fail closed;
- rollback evidence exists.

## Constitutional effect

This record grants no new business, provider, client, write, or autonomous authority. It formalizes an existing transitional read compatibility condition and its compensating controls.
