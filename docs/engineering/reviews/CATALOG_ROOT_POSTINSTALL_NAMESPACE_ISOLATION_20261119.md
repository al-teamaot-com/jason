# Catalog root namespace import isolation — source-only recovery v2 (2026-11-19)

## Observed failure and verified rollback

The Owner approved exact root-only ledger/Owner-signature lineage repair under action `catalog-root-bootstrap-mcp-consumption-ledger-separation-v1` for protected main `19b2e2d543619ae963f15520e5cba16051c3690b`. The three catalog trust files were replaced temporarily, but the subsequent post-install check raised `CATALOG_SCOPED_ROOT_IMPORT_NAMESPACE_UNTRUSTED` from the **unchanged trusted root host-reconcile worker**. The installed v1 source performed read-only validation of the new catalog host in the same Python interpreter first. That imported `tools`/`implementation`, then its post-install check called the native loader in that contaminated interpreter. The native loader correctly refuses inherited mutable namespaces.

The v1 installer caught the error, restored the three original bytes, and raised an exception. Operator readback subsequently confirmed the original catalog host SHA256 `a502f33320dc006be78a7e0676c29cfdd4974eaeeaa38b51cb1077defd5ad1ff`, router `382cadc5a199788cb36a14317611dc808fee8105df81022c2bb67f2453b4c5a9`, runtime/MCP original images, closed production breaker, unchanged freeze SHA256 `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`, and independent PMv4 Ticket Core/Runbook PASS. No image or provider write was performed.

## Exact repair and approval boundary

Add `tools/catalog_root_consumption_ledger_repair_v2_once.py` as a **new**, separately Owner-approved, one-use root installer. Do **not** replace or retry the previous consumed v1 root action, delete or overwrite its journals, alter native loader namespace protections or retime any signed image approval.

The v2 installer permits exactly the same three root-only files, original/new SHA pin values, source scope and rollback guarantees as v1:
- `/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_host.py`
- `/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_root.py`
- `/etc/jason-owner-release/catalog-scoped-promotion-installed.json` (only catalog source SHA and host hash advance).

It first validates the previous v1 root-owned journal contains the exact v1 approved intent and `failed.json` with `{"status":"rolled_back","rollback_verified":true}` and no successful receipt. It then uses fresh authenticated Entra Owner identity, the *new* exact decision phrase and exact source SHA. The new durable v2 audit directory is separate from v1. It checks the same two native release locks, pinned before/after hashes, original images, unchanged freeze, closed breaker, current protected CI, root-owned files, original signed image approval and historical consumption evidence.

The only post-install change is: launch `/usr/bin/python3 -I -c <reviewed built-in verification code>` with a fixed minimal environment and `cwd=/`. In that **clean process** import the original pinned root worker from its absolute path, call its **unchanged** `_trusted_catalog_scoped_promotion_module(source)`, and perform `CatalogPMv4ProtectedHost.enforce_installed_production_trust()`. Require a bounded, SHA-bound JSON receipt. This prevents the earlier false inherited-namespace failure **without bypassing the worker's original `sys.modules` guard**. Any nonzero exit, malformed receipt, source mismatch, image/PMv4 regression or changed freeze triggers the same exact three-file rollback, and records failure in the v2 journal.

V2 is **not** approval for runtime/MCP image promotion, Autotask writes, PMv4 changes, a breaker override, or reuse of the expired original image release proof. The image promotion still requires a separate new signed Owner decision and the native two-image rollback health gates.

## Regression gates

The new isolated repair regression verifies: exact three-file success; five atomic swap/import/health failures restore **all three** original files; child process really starts with absent `tools` and `implementation` even when parent imported them; fail-closed nonzero child/forged JSON; required `python3 -I`, fixed `cwd`, minimal environment without `PYTHONPATH`; original v1 failed/verified-rollback journal is required before v2; and root namespace guard continues to exist unmodified. Protected security CI must pass before merging. Live root installation requires fresh exact Entra Owner consent through a new reviewed hash-pinned launcher.

**Operational status:** This PR is source only. No root installation or production image promotion occurs on merge.
