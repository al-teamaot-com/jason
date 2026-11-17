# PMv4 exact catalog-unit drift reconciliation

**Status: source-only until protected-main CI and one authenticated Owner approval.**

On November 17, four already-installed catalog-only root recovery systemd
units became active/inactive in the host inventory but were undeclared in
the root-owned effective drift-policy allowlist. The native watchdog correctly
opened the production breaker. Ticket Core and MCP remained healthy.

The scope is deliberately limited to four units:
jason-catalog-root-bootstrap-recovery.service,
jason-catalog-root-bootstrap-recovery.timer,
jason-catalog-scoped-recovery.service,
jason-catalog-scoped-recovery.timer.

The four units are added ONLY to the allowed system unit list. No change
to required units, permitted running containers, stopped rollback retention,
provider authorization, client data, freeze, breaker state, Core/MCP images,
or catalog timers is allowed.

Run only the existing jason-production-drift-watchdog.service one-shot
once after root-owned atomic config installation; it must pass with zero
drift problems before acceptance. The pinned native Entra Owner signer
issues a one-use exact-plan proof, independently reverified by root, with
one-time audit and exact baseline rollback on postflight failure.

The immutable builder verifies protected main and CI. Root independently
compares actual root-owned policy bytes, four installed unit-file SHA-256s,
current LKG, freeze, and drift. Any mismatch stops without mutation.

This policy repair does NOT close the native breaker, deploy Ticket Core,
perform a provider write, or authorize Stage D or retirement. After a clean
watchdog check, only native root breaker revalidation may close it. The
Stage C cutover separately needs an updated canonical policy baseline.
