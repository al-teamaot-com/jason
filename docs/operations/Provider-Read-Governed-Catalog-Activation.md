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

The governed-catalog profile removes the second per-resource activation allowlist. All currently registered IT Glue and Autotask governed read capabilities become discoverable when the profile is selected, subject to normal identity, client/tenant scope, Central Orchestrator policy, provider boundaries, and information-release authorization.

Adding a new read capability to an already trusted provider's registered catalog therefore does not require another production activation list entry. Adding a new provider still requires an explicit provider-trust decision.

## Temporary Autotask requester authorization mode

Autotask provider-native requester impersonation is currently blocked by an HTTP 500 after the requester identity mapping succeeds. To restore read availability without broadening Autotask permissions, Jason temporarily supports requester authorization mode:

`JASON_AUTOTASK_REQUESTER_AUTH_MODE=jason_managed`

This temporary mode means:

- the dedicated Autotask API-only service identity performs the provider read;
- Jason does **not** add `ImpersonationResourceId` to that request;
- service-account fetch authority does not automatically become requester release authority;
- release is allowed only for a registered Autotask read capability after Jason has a positive authenticated human binding, an allowed JKD-001 authority decision, a validated authority context, observe-only permission mode, and Central-Orchestrator-governed execution;
- sensitive evidence remains subject to the existing information-sensitivity and derived-output controls;
- provider writes remain disabled.

The legacy provider-native mode remains available as:

`JASON_AUTOTASK_REQUESTER_AUTH_MODE=impersonated`

Unknown requester-authorization mode values fail closed.

## Priority long-term fix

**Priority:** replace the temporary Jason-managed Autotask requester-authorization mode with a durable provider-native/delegated authorization design. This work is tracked in GitHub issue #175.

The long-term work must determine and correct the Autotask impersonation HTTP 500 root cause, including the provider security-level/impersonation contract and requester identity-alias handling. Microsoft tenant/object identity should remain the stable authenticated identity; mutable email aliases should be mapping data rather than the root authority. The final design should restore provider-enforced requester authorization where practical without requiring broad Add/Edit/Delete permissions and without making matching ChatGPT, Microsoft, and Autotask email strings a prerequisite.

Until that work is complete, `jason_managed` is a compatibility mode, not the intended permanent architecture.

## What this does not change

This profile and temporary requester mode do **not**:

- enable provider writes;
- enable Add/Edit/Delete operations;
- bypass Microsoft/Jason identity binding;
- bypass JKD-001 requester authority;
- bypass client/tenant scope;
- bypass IT Glue or other source-native authorization;
- bypass information-release authorization;
- permit direct MCP-to-provider execution;
- change Central Orchestrator as the execution authority;
- authorize a new provider merely because connector code exists.

## Production acceptance

Before selecting `itglue-autotask-governed-catalog-v3` and the temporary Jason-managed Autotask requester mode in production:

- focused provider-read activation tests must pass;
- capability discovery tests must pass;
- governed provider-read tests must pass;
- information-authorization boundary tests must pass;
- Autotask requester-mode tests must prove no impersonation header/resource lookup occurs in `jason_managed` mode;
- tests must prove release remains denied when trusted binding, authority allowance, validated authority context, human requester, or observe permission is absent;
- the current production image/container must remain available for rollback;
- production deployment must preserve all existing identity, OpenBao, network, and secret boundaries.

After deployment, verify:

- all registered IT Glue/Autotask governed reads are discoverable;
- no write capability is exposed;
- `direct_provider_access=false`;
- `write_tools_enabled=false`;
- execution remains Central-Orchestrator governed;
- an exact ticket request can resolve to the appropriate ticket search/read path without requiring a new hard-coded conversational capability;
- Autotask reads no longer fail because of requester impersonation in `jason_managed` mode;
- requester release still fails closed when Jason authority cannot be proven.

## Design intent

A technician should be able to ask Jason for any information that is represented by an already trusted provider's governed read catalog. Jason should resolve the resource and operation dynamically. The security boundary is whether the provider/resource may be read and whether the resulting information may be released to the authenticated requester—not whether someone previously anticipated the exact natural-language question and added a one-off capability activation entry.
