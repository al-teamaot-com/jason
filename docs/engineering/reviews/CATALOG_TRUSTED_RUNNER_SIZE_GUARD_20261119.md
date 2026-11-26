# Catalog-only trusted native runner size guard — 19 November 2026

## Exact production defect

After the Owner-authenticated catalog root rebind succeeded, the first source-only catalog stage request `26ab43aa155b46f687b7b664bf81f52a` returned `CATALOG_SCOPED_TRUSTED_FILE_INVALID` before creating an offer. A read-only inspection of every root-owned catalog trusted file showed a single mismatch: the **original installed native release-manager runner is 425,154 bytes**, but the root worker applies a universal 262,144-byte ceiling.

The runner was installed from immutable reviewed source `01ba71c54d9dd0391734b16a92d0b292fc457ae9`, SHA256 `b194084a9a54fe024ae89784e2e75d54a26e1369ed65d824abed4ce958f58edf`. Current protected main contains a different, larger version of that source file because PMv4 engineering has progressed. Replacing the runner with current-main source would unnecessarily touch PMv4 code, contrary to the approved catalog-only scope.

## Narrow change

The trusted worker allows **512 KiB only** for `tools/release_manager_host_runner.py`; every other trusted file remains at 256 KiB. It continues to require root ownership, no symlinks, no writable group/other modes, exactly one hardlink, and byte-exact Git readback. It additionally pins the original native runner to both its **immutable original reviewed Git commit** and its exact historical SHA256. All other trusted sources remain bound to current protected main.

Read-only end-to-end validation using the exact installed catalog bundle and the current protected-main source resolved and imported the trusted root module successfully. The change is covered by narrow regression tests and standard SEC-007 CI.

## Root installation boundary

This PR is **source-only**, does not deploy images, change the freeze, replace the native release-manager runner, or authorize Autotask writes. `tools/catalog_root_trusted_runner_repair_once.py` performs only a separately authenticated, one-use **root worker + two-field installed policy** correction. It requires prior root-rebind Owner audit, exact immutable prior worker/policy and frozen marker, pinned native runner and verified original source, protected-main required CI, live breaker/drift health, scoped recovery timer, exact host locks, a fresh Entra Owner device-code sign-in and exact typed-action approval. Before mutation it durably records the new Owner identity and original bytes. After mutation it validates a full, root-only catalog trusted-module import and unchanged six protected containers, and restores both old files if checks fail.

**No image promotion, production freeze removal, restart, PMv4 Ticket Processing change, Runbook Management change, or provider-write grant is included.** The native catalog one-transaction release manager and rollback remain responsible for subsequent separately approved image promotion.
