# Production Promotion Mutation Entrypoints

**Status:** Proposed under #764
**Owner:** Jason Architecture Authority
**Authority:** J-CHANGE-003; Jason Deployment System
**Canonical registry:** `config/production-mutation-entrypoints.json`
**Last reviewed:** 2026-10-02

## Purpose

Jason must have one Production release/configuration authority boundary even though implementation uses multiple component-specific helpers.

The authoritative Production capability is:

`jason.deployment.apply`

A script being able to run Docker, systemd, install files, or change a release pointer does not make that script an independent Production authority.

## Classification rule

A mutation is a Production promotion when it changes released application code, image identity, configuration, policy, playbooks, schema/state migration, systemd/service definitions, deployment topology, or a release pointer.

Operational recovery is separate. Restarting an already-declared stopped service or recovering the same previously accepted runtime state may use an approved operational-recovery control, but it must not select a new artifact/configuration or silently become a release mechanism.

## Gated Production helpers

The current gated helper set includes the runtime and MCP production wrappers, Teams cutover/rollback, the immutable runtime candidate wrapper, and the generic live-container replacement helper.

Those helpers may execute only after the exact-plan Owner approval has produced a trusted signed single-use Production permit. Permit verification and durable claim occur before the first material Production mutation.

Candidate/staging helpers and read-only discovery tools have no Production release authority.

## Legacy direct installers pending migration

The registry currently marks the following classes as `legacy_pending_promotion_gate`:

- host-service/systemd reconciliation;
- observability assurance and dashboard installers;
- CCC scheduler installation;
- OpenClaw authority-operations installation;
- autonomy flight-recorder deployment;
- KFS collector runtime installation/update.

These scripts are existing implementation utilities, not supported independent Production deployment lanes.

Until they are migrated behind the common Production runner, their registry entries explicitly declare `production_release_authority=false`.

## Autonomous repair

The former J-CHANGE-002 autonomous Production apply path is classified as blocked legacy behavior.

`deployment.repair.apply` is approval-required and non-current. `jason-autonomy-worker` has no standing execute grant for repair deployment. Repair preparation may hand a prebuilt candidate to the J-CHANGE-003 Production lane only after exact-plan Owner approval.

## Enforcement against new bypasses

`tools/tests/test_production_mutation_entrypoints.py` scans high-risk host mutation scripts and requires them to appear in the canonical registry.

A newly added deploy/install/reconcile/cutover/rollback helper that contains Docker/systemd/release-pointer mutation patterns fails validation until it is explicitly classified.

Only classifications representing the exact-plan gated lane may declare `production_release_authority=true`.

Legacy pending, discovery, bootstrap, candidate, repair-preparation, and operational-recovery paths cannot claim Production release authority.

## Production activation boundary

This registry and the #764 code are non-production controls until separately approved.

Production activation requires the remaining legacy installers to be migrated or technically denied direct Production release authority, the trusted permit key/claim-store boundary to be installed, and #765 acceptance to prove missing/tampered/replayed authority causes zero Production mutation.

Passing CI, merging these controls, or closing #764 does not itself authorize activation in Production.
