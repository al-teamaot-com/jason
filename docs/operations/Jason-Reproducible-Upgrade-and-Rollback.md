# Jason Reproducible Upgrade and Rollback

Issue #751 defines the v1 candidate upgrade and rollback contract.

An upgrade is planned from two authoritative Deployment Manifests, not from release names alone.

## Required pre-upgrade checkpoint

Every upgrade requires a verified and restorable recovery-package receipt bound to the exact current deployment identity.

The upgrade is blocked when:
- the checkpoint is missing;
- the checkpoint belongs to a different deployment identity;
- the recovery package digest is invalid;
- verification or restorable status is not explicitly true.

## Schema migration contract

Schema versions are compared per named state store.

Any changed schema requires an exact migration edge declaring:
- migration ID;
- store;
- from-version;
- to-version;
- reversibility;
- rollback strategy.

Unknown transitions, new undeclared stores, or store removal block the upgrade before release switching.

## Rollback classes

- code_only: no schema/config/provider change; release and manifest can return to the prior identity automatically.
- reverse_migrations_then_restore_configuration: all migrations are explicitly reversible and a checkpoint is available.
- restore_checkpoint: irreversible schema, configuration, or provider-state change requires the verified pre-upgrade recovery package. This path is never treated as automatically safe.

The non-production candidate executor can prove release switching and rollback on a temporary root. It refuses the live filesystem root.

An irreversible candidate failure does not automatically restore state. Checkpoint restore must be explicitly authorized and supplied to the executor.
