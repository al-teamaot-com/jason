# Datto RMM Site Variable Governance

## Purpose

Jason may use Datto RMM site variables as client-scoped operational configuration, but variable access must remain governed because variable values can contain credentials, enrollment tokens, identifiers, or other sensitive configuration.

## Current production state — 2026-09-21

- `management.site.variable.list` is active through the governed Jason capability registry.
- The read path is client/site scoped and remains behind Central Orchestrator authority with `direct_provider_access=false`.
- Create and update operations are not currently active in the live capability registry.
- Delete is intentionally not part of the approved site-variable capability surface.
- Site-variable values must not be exposed to non-administrative users merely because the underlying provider can return them.

## Information-release rule

Site-variable names, presence, and values are operational configuration data. Jason must evaluate requester authority before releasing them.

Default handling:

1. Administrators with an authorized operational need may read values through the governed capability.
2. Non-administrative requesters must not receive site-variable values.
3. Where useful, a non-administrative requester may receive a safe statement such as "the required variable is configured" or "the required variable is missing" without receiving the value.
4. Values that appear to be credentials, tokens, secrets, keys, passwords, enrollment strings, or equivalent sensitive material must be treated as secrets even for administrative workflows and released only when the specific workflow requires the value.
5. Ticket notes, chat responses, Grafana labels, logs, and audit summaries must not copy secret variable values.

## Planned write behavior

Create and update are intended governed actions, not general-purpose provider access.

Required controls before activation:

- exact site identity and client binding;
- exact variable name;
- bounded value payload;
- administrator/Owner authority;
- policy evaluation by Central Orchestrator;
- one provider mutation attempt;
- no cross-client fallback;
- provider readback confirming the intended value/state;
- audit record containing the variable name and evidence reference without unnecessarily recording the secret value.

A playbook may use a site variable only within its approved client/site scope. A missing required variable should place the workflow into a blocked/dependency state rather than borrowing a value from another site.

## Delete policy

Deletion remains disabled by default. Removing a site variable can break deployments or managed components and therefore requires a separately designed capability, explicit business justification, rollback handling, and approval policy before it is ever exposed.

## Playbook use

Playbooks that depend on Datto RMM site variables must state:

- required variable names;
- whether only presence is needed or the value must be consumed;
- who is permitted to view the value;
- expected behavior when missing;
- whether create/update is allowed;
- post-write verification;
- secret-redaction requirements.

This document does not itself grant create/update authority. Runtime capability registration and Central Orchestrator policy remain authoritative.
