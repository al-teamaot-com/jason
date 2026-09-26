# J-405 Exception — Temporary IT Glue Jason-Managed Requester Authorization

**Status:** Approved transitional exception; remediation tracked in GitHub #176  
**Effective date:** 2026-09-12  
**Formalization date:** 2026-09-26  
**Review no later than:** 2026-10-15  
**Approving authority:** AOT Infrastructure Owner / Jason Architecture Authority  
**Governing authority:** Jason Constitution; J-405 Platform Integrity and Boundary Enforcement  
**Affected system/provider:** IT Glue read-only governed provider path  
**Affected capability class:** Registered IT Glue provider-neutral read capabilities only  
**Write authority:** Not granted by this exception

## Exact requirement being excepted

Jason's preferred platform-integrity posture is provider-native or delegated requester authorization at the provider boundary where practical. Current IT Glue integration does not yet provide the desired durable requester-specific provider authorization model for the required read scope.

The temporary exception permits Jason-managed requester authorization for governed IT Glue reads.

## Business / technical justification

The compatibility mode allows governed operational/documentation reads while keeping release authority inside Jason and without broadening IT Glue provider permissions or adding write authority.

## Scope

This exception applies only to:
- governed IT Glue reads through registered provider-neutral capabilities;
- authenticated Jason requesters that independently satisfy identity, authority, client/tenant scope, observe-only mode, information-release authorization, and Central Orchestrator execution;
- provider/source-native document restriction evidence where available.

It does not authorize IT Glue writes, direct provider access, cross-client data release, or bypass of restricted-document semantics.

## Risk

The provider-side read credential may have broader fetch reach than an individual human requester. Jason must therefore remain the authoritative release boundary and must preserve any provider-native restricted-document evidence available from IT Glue.

## Compensating controls

- authenticated Microsoft/Jason identity required;
- JKD-001 authority and validated authority context required;
- observe-only permission mode;
- explicit client/tenant scope;
- Central Orchestrator execution required;
- information-release authorization and sensitivity handling required;
- provider/source-native restriction semantics preserved when available;
- no write capabilities are granted by this exception;
- cross-client release remains denied;
- live MCP direct provider access remains disabled.

## Evidence / audit

Primary evidence:
- GitHub #176;
- `docs/operations/Jason-Production-Status-2026-09-14.md`;
- information-release boundary tests;
- IT Glue Jason-managed information-authorizer tests;
- live MCP governance status showing Central Orchestrator execution and `direct_provider_access=false`.

## Review / expiration rule

This exception must be reviewed no later than 2026-10-15. At review, the Architecture Authority must either:
1. retire it after provider-native/delegated requester authorization is accepted;
2. replace it with a stronger supported provider authorization design; or
3. explicitly renew it with updated evidence, risk review, and a new review date.

The exception must not silently become permanent architecture.

## Retirement criteria

Retire this exception when:
- a supported provider-native/delegated requester model is documented;
- Microsoft tenant/object identity remains the stable requester identity and aliases remain mapping data;
- restricted-document ACL/restriction semantics remain authoritative;
- bounded production proof and regression tests demonstrate safe requester enforcement;
- rollback evidence exists.

## Constitutional effect

This record grants no new provider, client, write, or autonomous authority. It formalizes an existing transitional read compatibility condition and its compensating controls.
