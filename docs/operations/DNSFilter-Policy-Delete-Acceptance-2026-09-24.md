# DNSFilter Policy-Delete Governed Write Acceptance — 2026-09-24

## Result

**PASS — exactly one provider mutation attempt, exact target absence verified, no other DNSFilter mutation performed.**

This acceptance deleted only the unassigned test policy created by the first governed DNSFilter write acceptance.

## Authorized target

- Canonical capability: `dns.protection.policy.delete`
- Provider: `dnsfilter_mcp_mutation`
- DNSFilter MCP tool: `delete_policy`
- Autotask company ID: `0`
- DNSFilter organization ID: `1110483`
- Policy ID: `1506474`
- Policy name: `Jason DNSFilter Governed Write Test 2026-09-24`
- Force delete: **not supplied / not authorized**

## Governance evidence

- Approval ID: `approval_mcp_cf888a8fdc2b4254bb6cc556023fff74`
- Intent fingerprint: `5639f20c6aa28e6c4f6cc91e9706a99728ae12cfeda7cb5699bce1dbfe5a7da2`
- Execution-plan fingerprint: `3ed3769c4321d8ba7a7a488bcbb3a6b9a2311c58ce79d1c561f73216b783139c`
- Execution ID: `exec_mcp_action_afeaa87613a749fdbf826ece039568e5`
- Correlation ID: `corr_mcp_action_f9ed5100adbf47b8b0a565e6833348df`
- Provider mutation invocation count: `1`
- Governed ledger final state: `succeeded`

The execution plan bound:

- provider capability: `dnsfilter_mcp.delete_policy`
- action method: `MCP_TOOL_CALL`
- resource type: `dns_policy`
- resource identifier: `1506474`
- provider-relative path: `/tools/delete_policy`
- company ID: `0`
- organization ID: `1110483`
- `client_scoped=false`
- exact policy ID and exact policy name
- `policy_delete_acceptance_target_verified=true`

Provider confirmation remained server-injected through the governed mutation adapter.

## Pre-write evidence

The delete acceptance profile was `policy_delete_acceptance_v1`.

Before an execution plan could be prepared, the mutation adapter was required to prove provider-native evidence that:

1. policy `1506474` existed;
2. it belonged to DNSFilter organization `1110483`;
3. its name exactly matched `Jason DNSFilter Governed Write Test 2026-09-24`;
4. it was not a global policy;
5. every required assignment relationship was explicitly present and empty:
   - networks;
   - MAC addresses;
   - scheduled policies;
   - network subnets;
   - user agents / roaming clients;
   - agent local users;
   - collections.

The execution succeeded, which means this fail-closed preflight completed before provider invocation.

The global-inclusive policy inventory immediately before this acceptance was `40` policies: `38` regular plus `2` global. Policy `1506474` was the intentionally retained unassigned acceptance policy.

## Provider execution

Jason executed:

`dns.protection.policy.delete`

through provider:

`dnsfilter_mcp_mutation`

with exactly one provider attempt.

The governed action completed successfully with:

- status: `succeeded`
- stage: `completed`
- provider attempts: `1`
- error code: none

No retry occurred.

## Post-write verification

Provider-native governed policy search after the deletion proved:

- policy `1506474` is absent;
- global-inclusive policy inventory = `39`;
- regular policies = `37`;
- global policies = `2`.

The one-policy decrease from 40 to 39 is supporting evidence. The decisive verification is exact target absence.

Ordinary DNSFilter organization read also remained healthy and continued to resolve organization `1110483 / Atlantic Office Technologies`.

## Cleanup verification

After readback verification:

1. `JASON_DNSFILTER_MCP_MUTATION_ENABLED=false` was applied successfully to both `jason-runtime` and `jason-mcp-pilot`.
2. The retained `policy_delete_acceptance_v1` profile is inert while the execution gate is false.
3. The exact delete acceptance grant was returned to `inactive`.
4. The temporary client-0 policy-search observe grant was returned to `inactive`.
5. The Microsoft identity binding for `person-al` was restored to `client_id=None`.
6. All 25 DNSFilter mutation definitions returned to `BUILDING`.
7. The `dnsfilter_mcp_mutation` provider returned to `PLANNED / UNKNOWN / BLOCKED`.
8. Zero DNSFilter mutation invokers are registered on both runtime surfaces.
9. Exact discovery for `dns_policy / delete` returns no active delete capability.
10. Ordinary DNSFilter read capabilities remain available.

Production runtime revision during final cleanup verification:

`21f9c55c0230e86c16642236e7e3a93fda6520ab`

## Conclusion

The second bounded DNSFilter governed-write acceptance passed.

Project Jason has now demonstrated both directions of the reversible policy lifecycle under governance:

- create one unassigned DNSFilter policy with exactly one provider mutation and provider-native verification;
- delete that exact unassigned policy with exactly one provider mutation and exact-target absence verification;
- return the administrative surface to a healthy dormant state after each test.

No production client/site/device assignment was modified by either acceptance.
