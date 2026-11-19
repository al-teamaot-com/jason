# Catalog image approval operator/root transaction boundary (2026-11-19)

## Evidence

The Owner-authenticated Scoped Backport correction completed, the native Release Manager breaker was independently root-revalidated CLOSED, and PMv4 Ticket Core, Shadow Gateway, Runbook Management and freeze checks passed. An exact authenticated Owner catalog root V2 repair then changed only three pinned trust files and returned `CATALOG_LEDGER_ISOLATED_TRUST_REPAIR_V2_VERIFIED=owner-fe2ca6029e674d2ca35e140eb6c80f0d`, with readback hashes PASS.

The catalog image approval stage stopped **before a new image Owner login/proof** at `approve_and_promote_catalog_renewal.py:137` because uid 1000 called `Path.exists()` below root-owned mode-0700 `/var/lib/jason-catalog-scoped-promotion/transactions/`. The log showed `PermissionError: [Errno 13] Permission denied` rather than an existing journal. No runtime/MCP image promotion occurred. There is no evidence in that exception that a prior native transaction exists.

## Source-only correction

Add `tools/catalog_owner_renewal_operator_v3.py`, a byte-preserving copy of the exact legacy renewal operator except for a single `root_existing_attempt` replacement. It verifies only the root-owned, non-symlink, mode-0700 transaction namespace *parent*, which uid 1000 is permitted to inspect, and NEVER descends into the protected transaction directory. No chmod/chown, privilege escalation, public representation of private journal state, or override of one-use authority. Do not reuse stale/expired image proof. Existing installed catalog host and router hashes remain pinned.

The **installed SHA-pinned native root worker is exclusively authoritative**: `NativeCatalogHost.deny_unresolved_previous_attempt` checks `transactions/release-755fa5fe3f75958f.json` and `active.json` under its native root transaction lock, and `durable_intent` checks the same root path with O_EXCL one-use journaling. The native source-only restager checks the existing root journal before mutating an offer. No root file or authority guard is edited here.

Add regression checks for inaccessible private directories, wrong uid/mode/symlink, root-only duplicate-transaction enforcement, preserved signed Owner renewal lineage and protected environment. Preserve the existing operator artifact unchanged. After protected CI merge, create a new read-only release wrapper that pins the **new exact reviewed script hash** and all previously reviewed root/freeze/PMv4 hashes, and run its `--check-only` without Owner proof. `--execute` must be run in the authenticated Owner terminal; exact new image approval and native paired rollback still apply. Catalog provider writes remain separately governed.

## Non-goals

No extra unit installation/removal, no production freeze change, no PMv4 migration, no Autotask provider writes, no replacement of runtime or MCP outside the existing separately approved image pair, and no bypass of root-owned replay/transaction checks.
