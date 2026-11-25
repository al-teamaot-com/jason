# Exact catalog admission of reviewed licensed-Owner canary test (2026-11-19)

## Incident

Catalog V2 root namespace repair, Scoped Backport drift correction and native breaker closure all verified. New catalog Owner image-approval operator V3 now passes its nonmutating preflight. A subsequent authorized unsigned source-only stage, however, failed **before root enqueue** with `CATALOG_SCOPED_ADMISSION_CATALOG_SOURCE_BLOB_CHANGED`.

The entire discrepancy is **one reviewed test**: `implementation/mcp_service/tests/test_autotask_catalog_grant_admin.py`. The sealed candidate/feature SHA-256 is `327debb36f5555dcfd0cda392d9bd403a4628ca921a2a381db861521b5c06522`, while latest protected main inherited reviewed November 19 commit `4aa7b5fe5afb3c0948e7e18d9ca98e14a7cb891f` of SHA-256 `47b3419267a81928ca86a0aaa1ce655170a319acd2e3b98d5a2614f5af3a36ae`. Only one expectation changes: verified licensed Owner read access to provider-health canary status succeeds instead of being denied; unrelated grant write, self-only administration and audit assertions remain unchanged. The other six exact catalog source blobs remain byte-identical. The six shared MCP catalog function sources also remain identical to the sealed approved snapshot.

## Narrow source-only change

Keep every executable catalog module, catalog grant boundary and image/digest unchanged. For only this one existing test file, the root source validator accepts either the sealed snapshot bytes or the exact 47b3... protected reviewed test revision. It independently requires immutable Git at the reviewed `4aa7...` commit to match the current blob exactly and requires that commit to be an ancestor of the current protected main. Any different test edit, feature blob edit or runtime catalog source edit is denied. No broad test or source exclusion; all seven scoped files remain verified. Existing protected CI remains mandatory.

## One-use native root trust update

The root-installed admission code is SHA-pinned by its root-private `catalog-scoped-promotion-installed.json`. To execute the new verified source admission, `catalog_admission_owner_canary_root_repair_once.py` requires exact reviewed protected Git, actual old installed admission hash, host/router unchanged, native root lock, freeze and LKG, breaker CLOSED, clean independent root watchdog, six protected container identities and no existing catalog root transaction. It then obtains fresh authenticated AOT Owner Entra OAuth and exact typed approval **only for two root-owned files**: the admission module and its one SHA256 field in the root-private install receipt. Atomic rollback restores exact original bytes on error; one-use Owner approval is recorded before any write. No release promotion, provider rights, network resets, PMv4 restart, image changes or unfreeze.

After native installed-source trust verifies, use the **separate** approved catalog V3 Owner image release transaction with its own exact signed image-pair proof. Never recycle or modify previous Owner approvals. The successful test source correction does not itself authorize a provider write or image activation.
