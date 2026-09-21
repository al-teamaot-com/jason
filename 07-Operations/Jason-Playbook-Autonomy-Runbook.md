# Jason Playbook Autonomy Runbook

**Status:** Active  
**Owner:** Jason Architecture Authority  
**Governing decision:** ADR-010 — Playbook-Level Autonomy Gating

## Purpose

This runbook defines how AOT reviews, approves, verifies, and revokes standing autonomous authority for a Jason playbook. It does not itself grant authority.

## Preconditions

Before approving a playbook for autonomous use, confirm:

- the playbook is registered and enabled for runtime use;
- the playbook has a stable version;
- required diagnostics, remediation, verification, rollback/escalation, retry, and idempotency behavior are defined;
- the allowed capability list is explicit and no broader than required;
- blast radius is bounded with a maximum target count;
- disruptive actions that require per-instance approval remain outside standing autonomy;
- representative and adversarial tests have passed; and
- the approving person has authority to grant standing playbook autonomy.

## Approval record

Record all of the following in the playbook registry:

- `mode: approved_autonomous`;
- `approval_status: approved`;
- `approved_version`;
- `approved_source_sha256`;
- `approved_by`;
- `approved_at`;
- `allowed_capabilities`;
- `maximum_targets`; and
- `review_expires_at` when a time-bounded approval is desired.

Do not enable the global autonomy gate merely to test whether a playbook approval record is valid. Validate the record and gate logic independently first.

## Activation sequence

1. Verify the exact playbook source hash and version.
2. Confirm the approval record matches that exact version/hash.
3. Confirm the allowed capability list and maximum target count.
4. Confirm all higher-level Jason safety policies remain active.
5. Verify Grafana shows the playbook as autonomy-approved.
6. Only after approved playbooks are ready, enable the global autonomy gate through the governed configuration process.
7. Confirm Grafana shows Global Autonomy = ON and only the intended playbooks as approved.
8. Start with a bounded pilot and review audit evidence after the first autonomous executions.

## Automatic invalidation

A version or source-hash change makes the prior standing approval invalid. Jason must fail closed until the changed playbook is reviewed and approved again. Adding a new capability to the playbook does not inherit prior approval.

## Revocation

To immediately stop autonomous execution:

- preferred emergency control: set global autonomy to OFF;
- for one playbook: set its autonomy approval status to not approved or change its mode away from `approved_autonomous`;
- disable the playbook entirely when runtime use should stop.

After revocation, verify the corresponding Grafana indicators return to OFF/0 and preserve the change in audit/change records.

## Verification

The live gate must return denial when any of these conditions occur:

- global autonomy is off;
- playbook is disabled;
- playbook is not registered;
- autonomy approval is absent;
- version differs from the approved version;
- source SHA-256 differs from the approved hash;
- capability is outside the approved list; or
- target count exceeds the approved maximum.

## Current production posture

As of 2026-09-21, global autonomy is OFF and all registered playbooks are non-autonomous. This statement is operational context only; verify the live registry and Grafana before relying on it later.
