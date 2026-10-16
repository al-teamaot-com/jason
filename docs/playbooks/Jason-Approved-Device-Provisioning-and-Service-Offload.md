# Jason Playbook: Approved Device Provisioning and Service Offload

**Status:** Owner-approved engineering design; **not activated** until runtime/authority implementation and acceptance succeed.
**Tracking:** TODO-OPS-013; [GitHub #1459](https://github.com/al-teamaot-com/jason/issues/1459)
**Owner:** AOT Owner / Jason Architecture Authority
**Applies to:** Approved AOT-managed or expressly authorized client-owned device, exact device identity and exact approved service/role.
**First controlled target:** Claw2-PC, Datto UID `13eda165-08e0-ec79-026a-985b37e2eb9e`.
**Excluded:** Production OpenClaw host `aoteq-OptiPlex-3040` (Claw), all unapproved devices and workloads.

```yaml
playbook:
  id: approved_device_service_offload
  name: Approved Device Provisioning and Service Offload
  version: 0.1.0
  owner: aot_owner_jason_architecture_authority
  target_type: endpoint
  trigger:
    provider: jason_governed_worker_registry
    match: eligible_exact_device_and_owner_approved_role_assignment
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 2
  recheck:
    enabled: true
    cadence: 15m
    stale_after: 24h
  verification:
    authoritative_source: jason_central_orchestrator_plus_endpoint_and_workload_readbacks
    success_condition: role_converged_healthy_and_isolated_work_completed
  completion:
    terminal_disposition: verified_ready_or_human_review
  autonomy:
    allowed_branches: [read_inventory, reconcile_approved_non_disruptive_desired_state, health_check, safe_retry, drain_and_reassign_work, routine_approved_maintenance]
    approval_bound_branches: [first_device_role_enrollment, change_service_or_role_manifest, new_secret_permission_or_tenant_scope, generic_adhoc_shell]
    disruptive_branches: [reimage, destructive_disk_operations, reboot_with_workload_impact, wipe, irreversible_cleanup]
```

## 1. Section Goal

**Goal:** Jason shall provision, update, monitor, repair, drain, retire, and replace **explicitly approved devices** hosting **explicitly approved Jason services, functions, or helpers**, so approved work can be offloaded from Jason's main host without creating another independently administered system.

**Success means:** one trusted enrollment enables role-bounded, repeatable and audited desired-state convergence; work is securely executed on an eligible worker; no unique work or production secret lives on the worker; health/self-heal, safe maintenance, safe reboot, rescheduling and rebuild are demonstrably recoverable; production and cross-tenant permissions never expand.

**Authorization decision, 2026-10-16:** The Owner grants Jason standing authority to perform routine **non-disruptive** provisioning, upkeep, monitoring, and self-repair within an approved device's **approved versioned service-role manifest**. This is *not* arbitrary host execution authority and is *not* automatic approval to enrol new devices, expand roles or secrets, or perform disruptive actions. Existing per-run generic shell protections and release controls remain effective. Claw2-PC has separately been designated and authorized for the development-worker pilot.

## 2. Trigger

A signed/owner-approved role assignment links the exact provider device UID and verified organization/site to an approved service-role manifest/version, with a persisted work request to provision, reconcile, upgrade, maintain, recover, drain, or retire. Discovering an available spare device alone is not an enrollment trigger.

## 3. Scope and Boundaries

**In scope:** approved AOT worker hosts (and later separately approved tenant scopes); Datto RMM inventory and governed provisioning transport; role-based dependencies, packages and containers; worker registration, bounded service offload, controlled ongoing configuration drift repair, monitored updates and safe task reassignment; replacing a failed worker without duplicating work.

**Out of scope:** unapproved endpoints/clients, production Claw, unreviewed services/roles/privilege changes, free-form remote shell as standing-safe, exporting production credentials, worker-initiated production deploys, governance/config mutation from a worker, automatic destructive disk operations and user-affecting reboots. `direct_provider_access=false`; Central Orchestrator, exact grants, provider/client boundaries and audit govern every action.

A worker never becomes an alternate Jason. Workers are data-plane executors without authority to approve work or production releases. AWS/cloud future workers use the same declared role/tenant boundaries.

## 4. Initial Identification

1. Resolve exact device UID, device name, immutable identity, Datto site and AOT/client ownership; verify authenticated inventory.
2. Prove active management and suitability; enumerate OS/version, CPU/RAM, partitions, volumes, filesystem capacity, running services, agents, attached volumes and business/production dependencies. Absence of telemetry is unknown, not proof of suitability.
3. Require the exact approved *device + role + role version + organization* binding from the central registry. Approval is not inferred from a user sentence or model interpretation.
4. Reject ambiguous, retired, missing, production-critical or mismatched assets. Verify no preexisting important workload would be overwritten.
5. Create or associate an authoritative work case. When linked to a service ticket, apply the shared ticket work-start/CI association gates; otherwise document `No applicable Autotask ticket/CI association` and use the worker lifecycle audit record.
6. Preserve enrollment and environment fingerprints and previous desired-state revision.

## 5. Expected State

The host is enrolled to exactly one approved role assignment (or explicitly defined compatible roles); a constrained worker identity and certificate/credential lease are valid; declared OS baseline, packages, runtime/services, resource limits and network/egress permissions match the manifest; readiness and health checks pass; there are no undocumented services or conflicting protected workloads. Task queue leases and artifacts remain central. Production secrets and production release authority are absent.

## 6. State Model

`candidate -> identity_verified -> suitability_checked -> enrollment_approved -> provision_pending -> provisioning -> verifying -> verified_ready -> running -> draining -> maintaining -> recovering -> verified_ready | blocked | human_review -> retired`.

Persist exact device/tenant/role/version, owner approval record and fingerprint, work item/idempotency key, state, last observed configuration fingerprint, role hash, desired-versus-actual drift, before/after change evidence, job IDs, lease/heartbeat, health status, scheduled rechecks, retry counts, draining state and final disposition. Never store unredacted credentials. Restarts resume from the last confirmed checkpoint without repeating destructive work.

## 7. Diagnostic Workflow

**Step 1 — Identity and dependency inventory.** Evidence: `endpoint.device.search/read`, `endpoint.audit.read`, approved role registry and governed host diagnostics. Prove exact Datto UID, company, OS, memory, disk partition/volume map, service inventory and dependencies. Missing identity/dependency facts -> `blocked`, no provision.

**Step 2 — Manifest and authority.** Evidence: central role registry, approved exact version, owner enrollment and policy/effective capabilities. Compare requested package/role/secret/maintenance privileges to the approved manifest. Unknown or changed profile -> `human_review`.

**Step 3 — Desired-state drift.** Evidence: remote signed/attested role-state report, package/service health, configuration fingerprints, agent status. Classify safe reconcilable drift vs disruptive/unknown state.

**Step 4 — Control-plane capacity.** Evidence: task leases, shared durable queue, checkpoint/object storage, GitHub permissions and release coordinator. Reject unsafe duplicate execution and production-credential exposure.

## 8. Decision Gates

Before **any** action: exact approved enrollment; same-tenant boundary; no protected role conflict; role manifest approved and current; exact narrowly scoped capability; no active incompatible job; recoverable backup/checkpoint when action needs one; non-disruptive classification or exact separate disruption approval. If the only available execution transport is the generic Datto `Run Ad Hoc Command (Shell) [MAC] [LIN]` component, it remains forced `per_run` with exact human instruction for that invocation; an approved role does not silently downgrade this rule. Implement deterministic, pre-reviewed role operations for unattended provisioning.

## 9. Remediation

**A. First enrollment (approval-bound):** verify owner-authorized device/role, generate a scoped non-exportable worker identity and register it centrally; no credential recycling from the production host. Approval must bind device UID, organization, role ID/version, allowed services and environment.

**B. Provision/repair (standing role-scoped when nondisruptive):** calculate desired-state diff; validate signatures/hashes, dependencies, repository sources, quotas and network boundaries; dispatch pre-reviewed, narrowly scoped package/service operations; preserve idempotency key and rollback point; read back terminal job result and actual state. Do not use broad free-form `eval` as the unattended implementation.

**C. Upgrade:** staged role release with exact version, health gate and rollback; no unauthorized new permissions.

**D. Reboot/maintenance:** drain running work and checkpoint; verify no user/client impact; if disruption remains possible obtain separate technician approval for the exact action. Reboot only when allowed by role policy and supported verification; rejoin, revalidate and resume.

**E. Replace/retire:** quarantine failed identity, expire leases and tokens, reassign centrally checkpointed work exactly once, provision an approved replacement, verify equivalent role readiness and revoke old worker access. Wipe/reimage only under an explicit separately authorized destructive plan.

## 10. Retry Policy

At most two bounded attempts for a particular drift fingerprint/action, each with pre/post evidence and a retry-safe idempotency key. Never redeliver an unknown-state command merely because output retrieval failed; query the original job by job UID. Escalate conflicting/ambiguous output or failed rollback.

## 11. Periodic Rechecks

Poll worker liveness, desired-state hashes, pending maintenance and task lease health approximately every 15 minutes while active. Apply backoff during provider outage; record no-op checks in the ledger without flooding notes or Teams. Missing heartbeat triggers safe draining/reassignment after a versioned lease timeout, not blind duplicate task launch.

## 12. Aging / Stale Condition

Flag unrecoverable or authorization-blocked enrollment/verification after 24 hours; fail closed after bounded retries. No indefinite `in progress` state. A worker that goes offline is unavailable rather than retired; do not delete its data or reassign a possibly still-executing lease without fencing.

## 13. Dependency Handling

For missing enrollment, capability/permission, telemetry, host-managed configuration, central queue, credential lease, network, or Release Manager prerequisites: find the existing development/support issue; attach fingerprint and exact failing gate; create a single dependency if authorized; persist `blocked`; schedule engineering re-evaluation automatically. Approved, non-disruptive missing *implementation work* must reenter the engineering queue rather than wait for a repeated owner `proceed`. New authority, secret scope, role version, tenant, or disruptive action is an explicit decision gate, not a routine retry.

## 14. Documentation Requirements

Use central lifecycle/audit record as the source; if an Autotask ticket exists, follow normal concise technician note policy. Include state, next action, exact endpoint/organization/role, approval binding, expected/actual state, job IDs, provider evidence, verified outcomes, rollback, time and remaining risks. Never record secret values or full sensitive shell output.

## 15. Failure Handling

Record denial, failed provider read, missing approval, enrollment mismatch, unexpected workload, incomplete output, offline host, conflicting lease and failed verification as distinct structured conditions. Mark non-operational while blocked. Never treat a successful GitHub merge, shell return code or job dispatch alone as readiness proof.

## 16. Escalation Criteria

Escalate new tenant/privilege/role scope, uncertain device production dependencies, disruptive action needing specific approval, secrets exposure, irreversible changes, lease fencing failure, exhausted recovery attempts, unexpected provider authority failure or incompatible service. Alert Owner/technician via governed Teams and associate tracked support/development blocker.

## 17. Verification

Independently read back enrollment, service identity, approved role hash, package/services/health, network isolation and restricted credentials. Prove one real bounded task completes on the worker with output/artifacts persisted centrally and without main-host ticket processing interruption. A partially configured, unverified, blocked, or revoked worker must never be eligible for task admission. Verify rollback, drain/rejoin and replacement with no double-execution.

## 18. Completion Criteria

Complete the worker admission only after: identity/suitability and role approval verified; provisioning readback passed; declared health sustained; task execution and checkpoint/lease behavior proven; unwanted privileges absent; required audit present; central registry state `verified_ready` independently read back. Full program implementation is not complete after only one command works.

## 19. Final Resolution Note

Record target and exact role version, purpose of offload, owner authorization, initial state, commands/capabilities and bounded attempts, service health/task result, final gate outcomes, residual work and next maintenance/recheck.

## 20. Required Capabilities

Available/partly available: `endpoint.device.search`, `endpoint.device.read`, `endpoint.audit.read`, `automation.component.search`, `automation.component.execute`, job search/output read, GitHub engineering and existing Release Manager. Still to implement and promote: durable owner-approved device-role enrollment and revocation; versioned role manifest validation; scoped noninteractive worker identity and secret delivery; safe deterministic provisioning/reconciliation capability; central work dispatch/leases/fencing/checkpoints; declarative health/drift and repair; safe drain/rejoin/retirement; owner notification and durable operational metrics. Existing ad-hoc shell pilot alone does not satisfy these gaps.

## 21. Acceptance Test

**Target:** Claw2-PC on the AOT site, Datto UID `13eda165-08e0-ec79-026a-985b37e2eb9e` — **never production Claw**.

1. Exact provider inventory, active roles, hardware, partitions, OS and dependencies.
2. Explicit device-role approval and forged/wrong-device/wrong-tenant denial; prove no provider attempt on denial.
3. Install approved development-worker role from a signed immutable manifest; verify idempotent second run and independent state readback.
4. Induce bounded harmless service/config drift; autonomously repair; verify no unrelated changes.
5. Run one approved isolated engineering TODO to a tested GitHub PR; no production release authority on worker.
6. Exercise lost connection, stale lease, safe drain, checkpoint/resume and no double execution.
7. Reboot only after approved disruption gate and drain, then verify rejoin.
8. Simulate recovery/replacement and revoke old identity.
9. Reject generic ad-hoc shell as standing-safe, out-of-role package actions, new secrets/roles/tenants and any production Claw mutation.
10. Verify audit, blocked-to-engineering readmission, proper owner notifications, metrics and acceptance closure.

## 22. Section Goal Closure

Only after live acceptance: record exact source SHA/release ID, verified configuration and worker UID, manifests and approvals, test artifacts/CI, runtime readbacks, rollback evidence, supported/unsupported service roles, Grafana status, owner notifications, remaining TODOs and proof that the role can be rebuilt on a second approved host. Until then mark implementation `not production accepted`.

## 23. Autonomous Execution Eligibility and Owner Review

Owner's October 16, 2026 directive approves the **policy concept and bounded engineering implementation** and standing routine actions **after** validated device-role binding and live acceptance. It does not pre-promote an unimplemented playbook. The server-side durable promotion must bind the exact `approved_device_service_offload` version, role/tenant/device grant, capability set, source fingerprint and allowed non-disruptive branches. A material role, policy, identity, capability or source version change requires review. Generic ad-hoc shell, impactful reboot, reimage, wiping and authority expansions remain approval-bound. This separates durable platform authority from prompt wording and prevents future reauthorization requests for already-approved routine work.
