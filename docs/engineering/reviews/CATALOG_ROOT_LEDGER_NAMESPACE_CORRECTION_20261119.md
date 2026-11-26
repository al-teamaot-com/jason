# Catalog root ledger namespace and signed-release recovery — 2026-11-19

## Verified incident and no-mutation state

Native request `90010d21613c41eb907976d7069656ca`, on the exact catalog release `release-755fa5fe3f75958f`, returned `CATALOG_SCOPED_PROMOTION_CONSUMPTION_LEDGER_UNEXPECTED_FILE` before durable intent or image-approval consumption. The production image pair stayed on its original immutable runtime/MCP images, the original freeze SHA256 was unchanged, breaker remained closed and independent PMv4 Ticket Core / Shadow Gateway / Runbook Management readback passed.

This was not an Entra failure. The original governed root catalog installer writes a permanent `catalog-root-owner-<uuid>.json` consumption record, while the next native catalog image promoter's reader recognized only `owner-mcp-<uuid>.json` in the same protected directory. **Never delete, rename, suppress, migrate or reset either approval record.**

The first exact Owner signed runtime/MCP approval (`owner-mcp-64357f084a4d414ea82ea312017347c1`) remained unconsumed but expired 2026-11-19 17:41:57Z. It cannot authorize production after that time or be altered/replayed.

## Independent native production-breaker recovery (verified)

At 2026-11-19T18:02:47Z, the separate root drift watchdog opened the release breaker on an `undeclared_running_container` observation. Later independent drift returned PASS and zero problems; neither passing drift nor source CI by itself closed the breaker. The existing **unmodified LKG-pinned** `release_breaker_recovery_manager.py` (SHA256 `0da723693829172171ae663a5f65e0c25864887f551a7dcb45ef747ee8a568c8`) was run against its exact Git revision `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. It required three distinct clean root drift observations (`18:19:54Z`, `18:21:55Z`, `18:22:55Z`), consumed one bounded native revalidation request, and recorded `root_verified_closed`. Root independently revalidated revision `d1b8c196...` and set the protected breaker `closed` at **18:23:58Z**. The original production freeze SHA, runtime/MCP image pair, and PMv4 Ticket/Runbook processes remained unchanged. Historical incident evidence and recovery ledger were preserved.

## Narrow production correction

Exactly three root-owned catalog-only trust files are proposed for a separately approved, one-use installation:

- `/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_host.py`: strictly validate both root bootstrap and MCP image-approval consumption namespaces. The bootstrap record requires exact schema, original one-use action/ID/Owner/source/plan, and matching root-only completed installer journal; those IDs are **excluded from MCP approval authority**. MCP IDs remain one-use with strict shape. Unknown/malformed evidence fails closed.
- `/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_root.py`: retain previous source-only offer-restage checks; permit restage only when a signed predecessor has **expired and remains unconsumed**, and when new protected main is its descendant and all catalog candidates/rollback/image/environment/scope fields are unchanged. The signed proof remains immutable. The production root selector verifies a strictly linear, cryptographically signed, append-only Owner renewal lineage, the exact predecessor's hash, previous expiry, identical verified Owner OID and unchanged candidate/rollback/scope/freeze. The **terminal** signed proof is then subjected to the original current-time 15-minute root validity and consumption checks.
- `/etc/jason-owner-release/catalog-scoped-promotion-installed.json`: update **only** `source_sha` to current protected main and `host_module_sha256` to the reviewed new catalog host. All other trust policy controls are preserved byte-for-byte.

The one-use `tools/catalog_root_consumption_ledger_repair_once.py` handles only those three files under both existing native release locks; fresh Entra Owner identity and an explicit typed decision are required. Before any mutation it checks exact old hashes, reviews protected main and required green CI, validates the historical ledger read-only using the pinned new module, verifies the signed offer is unconsumed, confirms both original image IDs and independent PMv4 services, freezes and breaker. It writes durable original bytes and exact Owner intent first. It installs and reads back the three files, independently tests trusted root import, unchanged containers and freeze. A failure restores all three original files without deleting or modifying Owner/consumption evidence. **This root action never deploys images or grants provider writes.**

The source-only `tools/catalog_scoped_owner_approval_renewal.py` issues a new Owner-signed exact release with a fresh 15-minute deadline only after Entra OAuth and explicit terminal consent. It preserves the expired primary proof and writes a separate immutable file under `owner-approval-renewals/<release-id>/<new-owner-mcp-id>.json` with the predecessor ID and SHA256 commitment. Signed proof lineage is independently verified again by the root promotion consumer. Predecessor proofs never become production authority merely because they remain on disk.

## PMv4 isolation and rollback

Only the existing catalog runtime and catalog MCP image pair is a deployment target. The installed `CatalogPMv4ProtectedHost` checks Ticket Processing Core/Shadow Gateway and Runbook Management health, stable container identity and PID, and JSON playbook registry count/generation **inside** the catalog native two-image rollback transaction. PMv4 Stage E, legacy-to-JSON migration, and active Ticket/Runbook production services are not deployment targets.

The native image approval remains a distinct fresh Owner decision after root-only repair and after source-only offer restaging. Autotask Services and Bundles provider writes remain separate high-risk governed actions requiring exact service-identity grants and approved nonbillable acceptance; no billable catalog changes are authorized by this release.

## Required verification

Source CI and tests are **not** production deployment. Before release, verify 3 pinned old/new hashes, current source and required green checks, production breaker closed, freeze unchanged, strict Owner root ledger, nonconsumption and expiry of old signed image proof. After Owner-authenticated root change verify installed 3 files and trust, native timer, original images, PMv4 health. Then issue fresh signed Owner image approval and run the existing protected image promotion with built-in rollback; verify final transaction receipt, two candidate image IDs and configured source/environment, exact freeze, independent PMv4 unchanged and healthy, and no provider writes.
