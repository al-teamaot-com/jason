# Governed Provider Read Catalog Activation

**Status:** Approved production direction  
**Updated:** 2026-09-11  
**Scope:** IT Glue and Autotask read providers

## Purpose

Jason must not require a developer to hard-code or separately activate every readable resource merely because a technician used different conversational wording or asked for a different entity. Once a provider itself is explicitly trusted for governed read access, Jason should discover and use the provider's registered read catalog dynamically.

The production profile implementing this behavior is:

`itglue-autotask-governed-catalog-v3`

## Governing rule

Provider admission remains an explicit security decision. Per-resource read activation does not.

For a provider admitted to this profile, Jason derives the readable capability surface from the provider's registered catalog at process start. A capability is activated only when all existing validation conditions pass, including:

- the provider is the expected external connector and its catalog matches the registered source contract;
- the capability is registered as provider-neutral;
- the capability is explicitly read-only;
- execution is deterministic-only;
- the capability does not require per-call action approval;
- the provider remains on the zero-cost foundation profile;
- the entire validation completes before any provider is made available.

Unknown activation profiles and catalog/contract drift fail closed.

## What this changes

Legacy profiles remain available only for rollback compatibility:

- `itglue-autotask-initial-read-v1`
- `itglue-autotask-document-read-v2`

Those profiles contain historical per-capability subsets. They are not the desired production architecture.

The governed-catalog profile removes the second per-resource activation allowlist. All currently registered IT Glue and Autotask governed read capabilities become discoverable when the profile is selected, subject to normal identity, client/tenant scope, provider enforcement, Central Orchestrator policy, and information-release authorization.

Adding a new read capability to an already trusted provider's registered catalog therefore does not require another production activation list entry. Adding a new provider still requires an explicit provider-trust decision.

## What this does not change

This profile does **not**:

- enable provider writes;
- enable Add/Edit/Delete operations;
- bypass Microsoft/Jason identity binding;
- bypass Autotask requester impersonation requirements;
- bypass IT Glue or other source-native authorization;
- bypass information-release authorization;
- permit direct MCP-to-provider execution;
- change Central Orchestrator as the execution authority;
- authorize a new provider merely because connector code exists.

## Autotask current blocker

As of 2026-09-11, Autotask service-account reads succeed but requester-impersonated Company/Ticket reads return HTTP 500. The evidence isolates the failure to the requester impersonation path rather than MCP capability discovery or provider credentials.

The approved least-privilege remediation is to configure Autotask so that:

1. the normal requester Resource security level allows that resource to be impersonated; and
2. the Jason API-only Resource security level permits impersonation for the required read/query entity operations.

Do not grant Add/Edit/Delete solely to make read access work. If Autotask's UI forces broader authority than the approved read/query scope, stop and obtain a new explicit approval instead of broadening permissions.

## Production acceptance

Before selecting `itglue-autotask-governed-catalog-v3` in production:

- focused provider-read activation tests must pass;
- capability discovery tests must pass;
- governed provider-read tests must pass;
- information-authorization boundary tests must pass;
- the current production image/container must remain available for rollback;
- production deployment must preserve all existing identity, OpenBao, network, and secret boundaries.

After deployment, verify:

- all registered IT Glue/Autotask governed reads are discoverable;
- no write capability is exposed;
- `direct_provider_access=false`;
- `write_tools_enabled=false`;
- execution remains Central-Orchestrator governed;
- an exact ticket request can resolve to the appropriate ticket search/read path without requiring a new hard-coded conversational capability;
- provider-native authorization still fails closed when requester authority cannot be proven.

## Design intent

A technician should be able to ask Jason for any information that is represented by an already trusted provider's governed read catalog. Jason should resolve the resource and operation dynamically. The security boundary is whether the provider/resource may be read and whether the resulting information may be released to the authenticated requester—not whether someone previously anticipated the exact natural-language question and added a one-off capability activation entry.
