# J-405 Exception — Temporary IT Glue Jason-Managed Requester Authorization

**Status:** Retired 2026-09-26; superseded by ADR-011 permanent requester-authorization architecture
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

## Retirement decision — 2026-09-26

The exception is retired by ADR-011. IT Glue API access is API-key based and exposes resource restriction/access evidence rather than a durable requester-impersonated read mechanism. J-405 now explicitly permits Jason-managed requester authorization where provider-native requester execution is unavailable or unsuitable, while preserving provider restrictions as one-way narrowing controls.

The implementation was tightened as part of retirement:
- explicitly unrestricted documents may be released only after Jason requester authority is proven;
- restricted document and attachment content requires positive provider ACL evidence;
- explicit ACL denial is authoritative;
- missing ACL evidence or unknown restriction state fails closed for protected content;
- document search releases only explicitly unrestricted, sanitized metadata;
- credential-like fields remain redacted/derived-only where applicable.

Microsoft tenant/object identity remains the stable requester identity and email/UPN aliases remain mapping data only.

## Constitutional effect

Retiring this exception grants no new provider, client, write, or autonomous authority. It replaces a temporary exception with the canonical governed architecture defined by ADR-011 and strengthens protected-document release behavior.
