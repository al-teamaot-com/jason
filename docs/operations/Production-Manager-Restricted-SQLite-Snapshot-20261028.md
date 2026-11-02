# Production Manager P0: restricted-owner SQLite snapshot

Preproduction requires a faithful, internally consistent copy of operational SQLite state. The normal host-side readonly SQLite online backup covers the live Runtime bind database files owned by the operator. A root-owned historical database cannot be read by the unprivileged operator, even though the existing live Runtime can access it. The first P0 snapshot attempt failed closed on this permission boundary; no production process or source data changed.

The general fallback for a database the operator cannot read is a separate, short-lived helper container using the existing production Runtime image. It does not run privileged code inside the running Runtime process. The helper:

- Accepts only a safe top-level `.sqlite3` filename under the `docker inspect`-verified live Runtime bind mount.
- Mounts live OpenClaw data **read-only** and mounts only a private, isolated preproduction staging directory writable.
- Runs with `--network none`, `--read-only`, `--security-opt no-new-privileges`, `--cap-drop ALL`, `--cap-add DAC_READ_SEARCH`, a 32-process limit and a 256 MiB memory limit. The one readonly DAC capability is required because the live bind directory is mode 0700 and the file belongs to UID 0.
- Uses a readonly SQLite source and SQLite's online backup API; committed WAL transactions are included without copying volatile WAL/SHM/journal sidecars. Only the isolated snapshot is converted to standalone DELETE journal mode.
- Returns the cloned file through `docker cp` so the destination is owned by the invoking operator and mode 0600. Confirms SQLite quick-check and standalone journal mode. Removes the helper container, staging directory and partial target on failure; an inability to clean up fails closed.
- Retains the existing per-database time and disk-space bounds and never uses a mutable developer checkout as operational source.

This is a general permission-boundary method, not an Autotask-specific exception or additional provider read/write authority. An unknown container, mismatched mount, unsafe filename, failed snapshot, nonprivate target, or invalid integrity result must not be treated as preproduction acceptance.

A live readonly canary on the root-owned `teams-identity-bindings.pre-aot-member-jit-20260921T1130.sqlite3` database succeeded with a private, operator-owned, integrity-checked copy and zero output sidecars. No production services were restarted or disconnected, and no production data was modified.

The production deployment freeze stays active. Source changes still require protected CI, exact-source candidate-controlled preproduction, complete impact review, one exact-SHA Owner approval and independent CCC material review, and governed deployment with postflight verification and rollback.
