# Catalog root bootstrap / image promotion ledger namespace correction — November 19, 2026

## Incident evidence
Owner Entra exact approval `owner-mcp-64357f084a4d414ea82ea312017347c1` was created for release `release-755fa5fe3f75958f`. Native request `90010d21613c41eb907976d7069656ca` failed `CATALOG_SCOPED_PROMOTION_CONSUMPTION_LEDGER_UNEXPECTED_FILE` **before** `durable_intent` and `consume_once`. Runtime/MCP image IDs and protected PMv4 Ticket Core/Runbook processes remain unchanged; production freeze/hash and closed breaker pass readback. Original signed proof is immutable, unconsumed but time-limited; never overwrite or replay it after expiry.

The original bootstrap installer `tools/catalog_scoped_root_install_native.py` creates `/var/lib/jason-catalog-scoped-promotion/consumed-owner-approvals/catalog-root-owner-{uuid}.json` and a root-only installer journal. The image promotion adapter subsequently enumerates the same ledger but previously accepted only `owner-mcp-{uuid}.json`. This is a *namespace incompatibility*, not evidence to justify deleting or resetting a valid bootstrap authorization.

## Minimal source-only repair

`tools/catalog_scoped_promotion_host.py` reads the ledger with two **strictly separate** namespaces:
- `catalog-root-owner-{uuid}.json`: require exact bootstrap schema, `catalog_root_install_only_v1` action, one-use, valid SHA/Owner, and read-only exact matching root-owned `root-installer-audit/release-{source}.json` with verified completed installation. These entries **do not enter** the image approval consumed-ID set.
- `owner-mcp-{uuid}.json`: require image promotion approval schema, ID/path agreement, one-use and exact release ID. Only these entries enter the image approval replay set.

Unexpected filename, symlink, foreign owner/mode, malformed JSON, missing/mismatched bootstrap journal, forged ID or multiple bootstrap entries fail closed. No existing ledger record is removed, reclassified, or changed.

`tools/catalog_root_consumption_ledger_repair_once.py` is a separately Owner-authenticated exact one-use **root source installation only**. It pins the root worker, root trust policy, existing host before-image, approved new host blob, original images, immutable freeze, closed breaker, live PMv4 health, protected main with green CI, no catalog transaction/active overlay, the original signed Owner approval and the existing root-only ledger. The privileged preflight evaluates the new source's ledger reader against real root-only evidence before it requests Owner confirmation. It changes exactly the catalog host adapter file, under the two existing release locks, backing up and journaling the previous bytes plus Owner intent. Postflight independently verifies the trusted root module, stable PMv4/container state and freeze; any failure restores the previous exact file.

The installer **does not** promote runtime/MCP, broaden Autotask write grants, pause PMv4 development, restart services, remove freeze, modify the consumed ledger, or reuse the signed image approval. Promotion is an independently governed follow-up permitted only while the signed Owner approval remains valid. Once that proof expires, a fresh exact Owner image approval and an auditable replacement lineage are necessary; do not change timestamps or delete the original proof.

## Acceptance
Catalog regression tests cover: valid historical bootstrap + zero image approvals, mixed valid IDs with only MCP IDs returned, unexpected files, forged/changed/missing audits, malformed IDs/claims, fake multiple root approvals, one-use Entra authenticated root installer and exact old-file rollback. All protected GitHub checks are mandatory before Owner-authenticated installation.
