# ADR-010 — Playbook-Level Autonomy Gating

**Status:** Accepted  
**Date:** 2026-09-21  
**Owner:** Jason Architecture Authority

## Decision

Jason autonomous execution is governed by a two-key model:

1. a global autonomy gate must be explicitly enabled; and
2. the exact playbook version being invoked must carry an explicit standing autonomy approval.

Global autonomy never creates authority by itself. A playbook approval never broadens authority beyond the Central Orchestrator, Identity and Authority Service, provider allowlists, client isolation, blast-radius controls, or non-overridable safety rules.

## Required playbook approval binding

A standing autonomous approval is valid only when it is bound to all of the following:

- playbook ID;
- exact playbook version;
- exact source SHA-256;
- named approver;
- approval timestamp;
- explicit allowed capability list; and
- maximum target count.

Optional review expiration may further narrow the approval. Missing or contradictory approval data fails closed.

## Change invalidation

Any source change that changes the approved hash, any version change, or any requested capability outside the approved capability list invalidates standing autonomy. The changed playbook must be reviewed and approved again before autonomous execution resumes.

## Safety precedence

Playbook autonomy can reduce authority but cannot override higher-order policy. A playbook marked autonomous still cannot bypass per-instance approval requirements for user-disruptive actions such as reboot, shutdown, forced logoff, or other actions designated disruptive by policy.

## Default state

The playbook registry defaults to:

- `global_enabled: false`;
- `default: deny`; and
- no playbook autonomy approvals.

Therefore enabling the global gate without separately approved playbooks authorizes no autonomous action.

## Observability

The playbook metrics exporter exposes:

- `jason_playbook_global_autonomy_enabled`; and
- `jason_playbook_autonomy_approved{playbook_id=...}`.

The Jason Playbook Control Center dashboard displays these controls so operators can immediately see whether the global gate is enabled and which playbooks currently carry standing autonomy approval.

## Rationale

Jason should earn autonomy at the smallest useful deterministic unit. Binding autonomy to an exact reviewed playbook prevents a broad global switch from silently authorizing new or changed remediation behavior and makes autonomous authority auditable, revocable, and resistant to configuration drift.
