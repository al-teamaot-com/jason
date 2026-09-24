# DNSFilter Full Read/Write Design — 2026-09-24

## Status

**DEPLOYABLE SOURCE — PRODUCTION WRITES REMAIN DISABLED UNTIL SEPARATE ACTIVATION/ACCEPTANCE**

This document defines the deployable DNSFilter governed read/write implementation after the accepted read-only production integration. Deploying this source does not authorize or enable any DNSFilter mutation.

Current production read state is separately documented in `DNSFilter-Dual-Plane-Integration-2026-09-24.md`.

## Objective

Extend the existing provider-supported DNSFilter MCP integration from governed reads to a full governed administrative read/write surface while preserving Project Jason constitutional controls:

- Central Orchestrator remains authoritative.
- DNSFilter OAuth role and provider `confirm=true` do not create Jason authority.
- Every mutation is bound to an exact Autotask company -> DNSFilter organization/network boundary.
- Callers never supply provider organization/MSP scope or `confirm`.
- Every write requires a bound execution plan, explicit approval, exactly one provider mutation attempt, and provider-native readback.
- Unknown write outcome is never blindly retried.
- User-disruptive mutations remain technician-approved for the exact action.
- No generic arbitrary MCP tool invocation is exposed.

## Provider contract reviewed

DNSFilter's current MCP documentation states that Admin capability writes require explicit confirmation, reads/writes are attributable to the authenticated user, privacy settings are enforced, and an MSP session is scoped to one organization.

The 2026-09-24 provider catalog snapshot contains 107 tools. Twenty-five administrative tools require `confirm=true`; those are the governed write scope for this design.

Authentication lifecycle (`authenticate`, `logout`) remains outside operational capability authority. `suggest_threat` is provider feedback rather than client configuration and remains excluded from this administrative write surface.

## Mutation families

### Policy domain/category lists

- add/remove block-list domain
- add/remove allow-list domain
- add/remove blocked category
- bulk add block-list domains
- bulk add allow-list domains

Preflight:
- exact policy ID(s);
- `get_policy` for every policy target;
- target organization must equal the validated boundary.

Readback:
- `get_policy` and verify the requested list/category state.

### Global lists / organization-wide category posture

- add/remove global-list domain
- set category across organization policies

Scope:
- organization ID is injected from the validated boundary;
- caller-supplied `organization_id`, `msp_id`, and `confirm` are rejected.

Readback:
- `get_global_lists` for global-list state;
- `policies_with_category` / bounded policy reads for category state.

### Policy lifecycle

- clone policy
- create policy
- update policy
- delete policy

Preflight:
- clone/update/delete source policy must belong to the mapped organization;
- clone target organization is injected from the same boundary;
- create organization is injected;
- no cross-client policy clone is permitted.

Readback:
- created/cloned policy: provider result ID when available, otherwise exact-name `find_policy`;
- updated policy: `get_policy`;
- deleted policy: verify provider no longer returns the target.

### Site/network policy and forwarders

- apply policy to sites
- update site forwarders

Preflight:
- every network via `get_network`;
- target policy via `get_policy` where applicable;
- all resolved targets must belong to the mapped organization.

Readback:
- `site_policy_status` for policy assignment;
- `site_dns_config` for forwarder changes.

### Portal users

- invite user
- change user role
- send password reset

Scope:
- organization ID is injected when supported/required;
- role is restricted to DNSFilter's published role enum.

Preflight/readback:
- invite: validate target email + organization, then `user_lookup`;
- role change: resolve the target user under the mapped organization before execution, and verify after;
- password reset is a one-shot side effect. Readback verifies target identity/context, not email delivery. No automatic retry after an unknown outcome.

### Roaming agents

- reassign agent policy
- uninstall agent
- bulk remove agents

Preflight:
- target agent(s) must resolve inside the mapped organization;
- policy target must also belong to the mapped organization where applicable;
- bulk targets are bounded.

Readback:
- scoped agent query/device lookup confirms new policy/uninstall/removal state.
- destructive/uninstall operations are user-disruptive and always require explicit technician approval.

### Block page

- update block page

Preflight:
- `get_block_page` and organization relationship must match boundary.

Readback:
- `get_block_page` and compare normalized changed fields.

### Unblock requests

- decide unblock request

Preflight:
- `get_unblock_request`;
- request organization must match the boundary;
- decision must be one of the provider enum values.

Readback:
- `get_unblock_request` verifies resolution state/decision when returned.

## Execution-plan contract

Every mutation adapter must implement `prepare_governed_execution` and `execute_governed_execution`.

The prepared plan is secret-free and binds:

- canonical capability;
- selected provider `dnsfilter_mcp_mutation`;
- exact provider tool;
- mapped Autotask company ID;
- mapped DNSFilter organization ID;
- exact resource identifier(s);
- normalized mutation payload excluding credentials;
- server-injected `confirm=true`;
- symbolic/preflight resolutions used to prove target ownership.

At invocation the connector re-checks provider capability, tool name, target, normalized payload, and parameters against the approved execution plan before making the provider call.

## Confirmation model

DNSFilter's `confirm=true` is a provider-side safety gate only.

Jason injects it only inside the governed mutation adapter after:

1. exact capability resolution;
2. exact client boundary resolution;
3. target ownership verification;
4. authority grant evaluation;
5. explicit approval;
6. stable execution-plan fingerprint verification.

The caller cannot provide `confirm`.

## Retry and unknown-outcome rule

All mutation definitions use `maximum_attempts=1`.

If the provider request times out or returns an ambiguous transport result after the request may have reached DNSFilter:

- do not retry;
- perform only readback;
- classify success only when readback proves the approved target state;
- otherwise return unknown/verification failure and escalate.

## Production deployment and activation model

The read/write connector can be deployed while remaining non-executable.

Until separately approved:

- mutation capability lifecycle remains `BUILDING`;
- mutation definitions are registered as `BUILDING` only;
- the dedicated `dnsfilter_mcp_mutation` provider is registered as `PLANNED / UNKNOWN / BLOCKED`;
- the mutation invoker is not constructed or registered while the mutation profile/gate are absent;
- `policy_create_acceptance_v1` activates and registers only `dns.protection.policy.create` for the first controlled acceptance;
- `governed_v1` activates the full 25-capability mutation surface and is reserved for a later separately approved stage;
- every activation profile also requires `JASON_DNSFILTER_MCP_MUTATION_ENABLED=true`;
- authority remains a separate gate; the first acceptance uses only an `execute` grant for `dns.protection.policy.create` with `approval_required=true`;
- no generic arbitrary MCP action surface is exposed.

## Future acceptance sequence

1. source/security review of all 25 mappings;
2. full unit tests with fake provider responses;
3. execution-plan fingerprint/binding tests;
4. negative cross-organization tests;
5. negative caller-supplied scope/confirm tests;
6. one controlled AOT non-disruptive write acceptance;
7. provider-native readback;
8. rollback/compensation test where supported;
9. separate review for user-disruptive families;
10. source may be merged/deployed dormant after review; only after the controlled acceptance should production write gates, authority grants, and active write registration be considered.

## Controlled policy-create acceptance profile

The first live acceptance intentionally uses a single-capability profile rather than the full mutation profile.

Profile:
`JASON_DNSFILTER_MCP_MUTATION_PROFILE=policy_create_acceptance_v1`

Execution gate:
`JASON_DNSFILTER_MCP_MUTATION_ENABLED=true`

Effect:
- `dns.protection.policy.create` -> `ACTIVE`;
- `dnsfilter_mcp_mutation` -> `AVAILABLE / HEALTHY / APPROVED`;
- only the policy-create mutation invoker is registered;
- the other 24 mutation definitions remain `BUILDING` and unregistered;
- authority still must explicitly allow `dns.protection.policy.create`;
- capability approval remains required.

The first attempt before this profile existed failed closed with zero provider mutations because normal discovery excludes dormant `BUILDING` capabilities. That failure is accepted safety evidence, not a provider failure.

After the controlled create-policy acceptance and readback, return both mutation environment gates to unset unless a subsequent write test has separately approved scope.
