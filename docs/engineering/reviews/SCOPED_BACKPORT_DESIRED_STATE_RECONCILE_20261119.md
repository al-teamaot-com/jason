# Scoped Backport production desired-state repair (2026-11-19)

## Observed incident and authority

Existing owner-approved scoped-backport release controller installation created four root-owned systemd units. The installed bytes match the protected `6adc19744fc7464ef3ba34d1ce0b3b20e9e69684` Git blobs for `infrastructure/scoped-backport-release/` exactly. The root-owned public attestation agrees with this source. Native production drift evidence at 2026-11-19 19:35Z shows only four undeclared unit errors and the protected production breaker OPEN; Ticket Core, PMv4 Shadow Gateway and Runbook Management remain healthy. Catalog V2 root recovery refused before any new root or runtime/MCP mutation.

The watchdog's **active policy** is `/etc/jason/release-readback-recovery/production-desired-state.json`, not the public old-release file under `/opt/jason/current/config`. Never overwrite its preexisting catalog or PMv4 allowances with the public file. Do not stop/remove any scoped-backport units; those are separately approved operational recovery/request controls.

## Exact-source-only correction

A scoped, one-time, signed Owner installer adapts existing `pmv4_catalog_drift_reconcile_*` governance mechanisms. Its only desired-state delta is adding the four exact names to `allowed_system_units`, preserving all existing keys and values. The root executor checks source/CI SHA, latest protected `main`, immutable source script hashes, current root policy bytes and digest against an independently archived previous approved policy, frozen release revision and freeze/hold digests, four installed root-owned unit hashes, exact live drift, approval signature and one-use audit.

The builder initially uses the historically signed root overlay candidate from the prior four-unit catalog reconciliation as **expected baseline**; root preflight MUST independently match that hash against actual current root-owned policy. If it does not, stop without modifying anything and prepare a new reviewable candidate from root-owned evidence; never silently adapt scope after approval.

Before any mutation, authenticate the Owner through Entra MFA and typed exact-action consent. Under the native release transaction lock, create an immutable attempt receipt before replacing precisely the root desired-state policy bytes. Trigger the existing watchdog oneshot and demand a clean native drift PASS. Then invoke the existing immutable root-governed `revalidate_circuit_breaker` against the LKG revision and require breaker CLOSED. If any assertion/health/revalidation step fails, restore the exact original policy bytes and leave the breaker fail-closed. All other production components and frozen files remain unchanged. Retain audit for successes and failures. No provider write, image promotion, new standing authority, PMv4 code deployment, container restart or unit removal.

## Separate catalog release

After native breaker CLOSED and a fresh PMv4 preflight PASS, use the already prepared `owner-complete-catalog-recovery-v2-20261119.sh` exact procedure with fresh Owner Entra authorization. The old catalog V1 root Owner action was consumed by a verified rollback and must never be reused. Exact runtime/MCP image pair readback, protected PMv4 health, original freeze and native rollback are mandatory. Catalog service/bundle provider writes remain separately governed and out of scope.

## Status

Source engineering only; production root execution requires separate exact Owner authorization. Do not call production-ready until required protected CI and root preflight have passed. Incident: #2644.
