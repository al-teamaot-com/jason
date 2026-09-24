# DNSFilter Policy-Create Governed Write Acceptance — 2026-09-24

## Result

**PASS — exactly one provider mutation attempt, provider-native readback verified, no client/network/device assignment changed.**

This acceptance exercised only the narrow `dns.protection.policy.create` production profile against the AOT master DNSFilter scope.

## Authorized target

- Canonical capability: `dns.protection.policy.create`
- Provider: `dnsfilter_mcp_mutation`
- DNSFilter MCP tool: `create_policy`
- Autotask company ID: `0`
- DNSFilter organization ID: `1110483`
- DNSFilter organization: `Atlantic Office Technologies`
- Policy name: `Jason DNSFilter Governed Write Test 2026-09-24`

## Governance evidence

- Approval ID: `approval_mcp_d541173d9ac54c6a93bcd0239e924c23`
- Intent fingerprint: `7d37065ee8212ed3a2e99f580667ea29216133d2f11a62a936c097d7330f837f`
- Execution-plan fingerprint: `3109d82344b61d7148b02a1b371564df920b59d109de6d61e12b47be90c17966`
- Execution ID: `exec_mcp_action_f1250eb8c26a4eceb97f956b5fe891ed`
- Correlation ID: `corr_mcp_action_f0133e01f98c43daa7ea7b418a39b198`
- Provider mutation invocation count: `1`

The bound normalized provider payload was:

- `name = Jason DNSFilter Governed Write Test 2026-09-24`
- `organization_id = 1110483`
- `confirm = true` — injected by Jason, not supplied by the caller

Symbolic resolution recorded company `0`, organization `1110483`, `client_scoped=false`, and the validated AOT boundary.

## Pre-write evidence

Jason:

1. validated Autotask company `0` -> DNSFilter organization `1110483`;
2. read the current DNSFilter policy inventory;
3. observed `39` policies;
4. confirmed there were `0` exact matches for the authorized test-policy name.

No provider mutation occurred until approval and the bound execution plan were consumed.

## Provider result and readback

Exactly one `create_policy` provider mutation was attempted.

The provider invocation returned to Jason as `CONNECTOR_AUTHORIZATION_DENIED`. Jason did not retry the mutation.

Provider-native readback then proved the side effect had occurred:

- policy inventory increased from `39` to `40`;
- created policy ID: `1506474`;
- policy name exactly matched the approved name;
- organization ID was `1110483`;
- networks: none;
- user agents / roaming clients: none;
- local users: none;
- collections: none.

The test therefore passed by conclusive readback rather than by trusting the provider's error result.

## Engineering findings

### Provider-relative execution-plan path

The mutation adapter prepared `mcp://dnsfilter/tools/create_policy`, while Jason's execution-plan contract requires a provider-relative path.

The accepted path is:

`/tools/create_policy`

The durable source fix changes all DNSFilter MCP mutation plan paths to `/tools/<tool_name>` and rejects the legacy absolute MCP URI form.

### Ambiguous provider error after a successful create

The provider can perform the create and still return an execution error. The governed adapter therefore must never automatically retry.

For policy creation specifically, recovery is allowed only when:

1. preflight proved zero exact-name matches before the provider call;
2. exactly one provider mutation attempt occurred;
3. provider-native readback resolves exactly one policy with the approved name under the approved organization.

If those conditions are not met, the result remains unknown and escalates without retry.

### Mutation gate-off cleanup

After the acceptance, the exact acceptance authority grant was returned to inactive and the temporary `person-al -> client 0` identity context was removed.

The first attempt to set `JASON_DNSFILTER_MCP_MUTATION_ENABLED=false` failed deployment health and automatically rolled back because the runtime treated a present activation profile plus a disabled execution gate as an invalid startup combination.

The corrected contract makes the execution gate a true kill switch:

- `JASON_DNSFILTER_MCP_MUTATION_ENABLED=false` or unset -> healthy dormant mutation foundation;
- all DNSFilter mutation definitions -> `BUILDING`;
- mutation provider -> `PLANNED / UNKNOWN / BLOCKED`;
- no mutation invoker registration;
- a retained profile string is inert while the execution gate is off;
- `gate=true` with no valid profile still fails closed.

## Acceptance policy object

Policy `1506474` is intentionally left in place for inspection and for a later separately governed deletion acceptance test.

Do not delete or assign this policy as part of this acceptance record.

## Read-plane verification

After the write acceptance, ordinary DNSFilter reads remained healthy:

- organization `1110483 / Atlantic Office Technologies` read successfully;
- policy inventory returned `40` policies;
- policy `1506474` was present;
- no client/network/device assignment was introduced by the test.

## Post-cleanup production verification

Cleanup was completed successfully on production revision `7a74946637077edf69df34a555429c5fa873e086`.

Both `jason-runtime` and `jason-mcp-pilot` are healthy with:

- `JASON_DNSFILTER_MCP_MUTATION_PROFILE=policy_create_acceptance_v1` retained for provenance;
- `JASON_DNSFILTER_MCP_MUTATION_ENABLED=false`;
- all 25 DNSFilter mutation definitions at `BUILDING`;
- `dnsfilter_mcp_mutation` at `PLANNED / UNKNOWN / BLOCKED`;
- zero DNSFilter mutation invokers registered;
- the exact acceptance authority grant `grant_person_al_dns_protection_policy_create_acceptance_20260924` at `inactive`;
- `dns.protection.policy.create` absent from the live governed write-capability list and absent from exact `dns_policy / create` discovery.

Ordinary DNSFilter reads remain healthy. A post-cleanup policy search returned 40 policies when global policies were included: 38 regular policies plus 2 global policies. Policy `1506474` remains present under organization `1110483` with zero networks, zero user agents, zero local users, and zero collections.

This closes the first policy-create write acceptance. The test policy remains intentionally undeleted for a future separately governed deletion acceptance.


## Follow-up deletion acceptance

The next separately governed acceptance is deletion of this exact unassigned test policy using the narrow `policy_delete_acceptance_v1` profile. The plan is documented in `DNSFilter-Policy-Delete-Acceptance-Plan-2026-09-24.md`. The deletion profile authorizes no other policy target and does not use conversational imperative auto-approval; an explicit governed approval is required before the single provider mutation attempt.
