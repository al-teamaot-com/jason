# DNSFilter Policy-Delete Governed Write Acceptance Plan — 2026-09-24

## Purpose

Validate Jason's governed DNSFilter policy-deletion path by deleting only the unassigned test policy created by the first successful policy-create acceptance.

This plan authorizes no other DNSFilter mutation.

## Exact target

- Canonical capability: `dns.protection.policy.delete`
- Provider: `dnsfilter_mcp_mutation`
- DNSFilter MCP tool: `delete_policy`
- Autotask company ID: `0`
- DNSFilter organization ID: `1110483`
- Policy ID: `1506474`
- Policy name: `Jason DNSFilter Governed Write Test 2026-09-24`

## Narrow activation profile

Use:

`JASON_DNSFILTER_MCP_MUTATION_PROFILE=policy_delete_acceptance_v1`

and:

`JASON_DNSFILTER_MCP_MUTATION_ENABLED=true`

The profile activates and registers only `dns.protection.policy.delete`. Every other DNSFilter mutation remains `BUILDING` and has no mutation invoker.

For this exact hard-bound acceptance profile, the authenticated owner's explicit conversational imperative to proceed is the approval signal. The authority grant still requires approval, and Jason persists/binds that approval to the exact execution before provider invocation.

## Preflight requirements

Before an execution plan can be prepared, Jason must prove all of the following from provider-native data:

1. Autotask company `0` maps to DNSFilter organization `1110483`.
2. Policy `1506474` exists in organization `1110483`.
3. Its name is exactly `Jason DNSFilter Governed Write Test 2026-09-24`.
4. It is not a global policy.
5. Each of these relationship collections is present and empty:
   - networks;
   - MAC addresses;
   - scheduled policies;
   - network subnets;
   - user agents / roaming clients;
   - agent local users;
   - collections.
6. The active mutation profile is `policy_delete_acceptance_v1`.
7. The requested tool is exactly `delete_policy`.

A missing relationship is not equivalent to an empty relationship. Failure to prove any item above must stop before provider mutation.

## Execution-plan contract

The approved plan must bind:

- canonical capability `dns.protection.policy.delete`;
- provider `dnsfilter_mcp_mutation`;
- provider-relative path `/tools/delete_policy`;
- policy ID `1506474`;
- company ID `0`;
- organization ID `1110483`;
- normalized provider payload;
- server-injected `confirm=true`;
- validated target-name and no-assignment evidence;
- intent fingerprint;
- execution-plan fingerprint.

The acceptance test does not require or authorize `force=true`. If deletion unexpectedly requires force, stop and review rather than widening the approved payload.

## Provider invocation and retry rule

Perform exactly one provider mutation attempt.

Do not automatically retry if DNSFilter returns an error, timeout, authorization-like error, or other ambiguous result after the request may have reached the provider.

For this exact acceptance profile, a provider error may be recovered as success only because preflight proved the exact target existed and was unassigned. Recovery requires provider-native readback to prove policy ID `1506474` no longer appears in the organization policy inventory.

If the policy remains present, or absence cannot be proven, return unknown/verification failure and stop without retry.

## Successful verification

A successful acceptance must prove:

- provider mutation invocation count = `1`;
- policy ID `1506474` is absent on provider-native readback;
- ordinary DNSFilter reads remain healthy;
- no other DNSFilter policy was changed;
- no client/network/device assignment was changed;
- no second delete was attempted.

Policy counts are supporting evidence only. The decisive verification is exact target absence. If no unrelated policy changes occur during the test, the current 40-policy global-inclusive inventory would be expected to become 39.

## Cleanup

After the acceptance:

1. set `JASON_DNSFILTER_MCP_MUTATION_ENABLED=false` or unset it;
2. leave the delete acceptance profile inert or remove it;
3. return the exact delete acceptance authority grant to inactive;
4. remove any temporary owner-to-client-0 identity context used solely for the test;
5. verify all 25 DNSFilter mutation capabilities are `BUILDING`;
6. verify `dnsfilter_mcp_mutation` is `PLANNED / UNKNOWN / BLOCKED`;
7. verify zero DNSFilter mutation invokers are registered;
8. verify `dns.protection.policy.delete` is absent from live governed action discovery;
9. verify ordinary DNSFilter reads remain healthy.

## Acceptance record

After execution, preserve the approval ID, intent fingerprint, execution-plan fingerprint, execution ID, correlation ID, provider invocation count, pre-write relationship evidence, provider result, post-write readback, and final dormant cleanup state in a dedicated acceptance record.
