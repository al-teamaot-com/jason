# PMv4 Stage C — root preflight and exact legacy WAL/SHM mode reconciliation

**Status:** SOURCE-ONLY corrective change. Existing approved Owner proof for prior candidate `cf79f1a806e76c554310a13c58eae53201befdf3` is *one-use* and must not be reused. Current Stage C external worker remains undeployed; existing production runtime and MCP were restored to their original containers after the failed attempt. No legacy permissions were changed by this development effort.

## Evidence, confirmed on the live host without mutation

The prior one-owner release passed exact SHA, watchdog, root preflight, native Owner proof, and authenticated exact-action consent. After both approved production services stopped and their containers were renamed for rollback, SQLite-family handoff declined the `0644` mode on `autonomy-targeted-wakes.sqlite3-wal` with `HandoffDenied:C_SQLITE_UNTRUSTED_FILE`. Pre-activation rollback restarted both original runtime/MCP containers; their original images and production LKG remained present, drift was `pass`, breaker `closed`, and two subsequent read-only ticket scans each returned 128 provider items and zero duplicates. The failed attempt did not activate `jason-pmv4-ticket-core`, relocate any DB family, or commit Stage C acceptance; the old signed release proof must not be replayed.

Independent read-only mode inspection of all 23 active SQLite DB, WAL, SHM and owner-lock files found exactly **six** legacy files at `0644`:

- `governed-execution.sqlite3`
- `resolution-memory.sqlite3`
- `autonomy-targeted-wakes.sqlite3-wal`
- `autonomy-targeted-wakes.sqlite3-shm`
- `resolution-memory.sqlite3-wal`
- `resolution-memory.sqlite3-shm`

The old Stage C executor already normalized the two main DBs but **omitted the four allowed sidecars**. The standalone `pmv4_c_sqlite_family_handoff.py` correctly and strictly requires every relocated file to have mode `0600`. It must NOT be weakened to allow 0644. Some source WAL/SHM files may disappear after producers stop and checkpoint; absence is allowed, unexpected ownership, world/group write access, symlink/hardlink, device mismatch, or unreviewed mode is denied.

## Exact correction

`tools/pmv4_c_atomic_root.py` now has an immutable allowlist of the six exact legacy basenames, with source root UID/GID `1000:1000`, mode `0700`, same device, regular-file `nlink=1` and no symlink. During the **privileged read-only preflight before Owner consent**, inspect every database main file and present WAL, SHM, and `.owner.lock` sidecar; refuse any `0644` file outside that allowlist, or any other unreviewed mode. Print the exact number of proposed mode changes before asking for authentication. This read-only inventory was executed against the live host for the previous packet and found precisely six names with no mutation.

Only under the existing exact Owner-signed root transaction and after **both** `jason-runtime` and `jason-mcp-pilot` are stopped and verified quiescent, normalize just those existing allowlisted `0644` files using `fchmod` of a pinned inode opened with `O_NOFOLLOW`, preserving UID/GID, inode, size, and content. Keep originals in an in-memory rollback map **before** each change; record a root audit `legacy_mode_normalized` event listing exact file basenames. Re-evaluate every SQLite-family mode and require `0600` before the existing zero-copy, inode-preserving handoff begins. On pre-activation failure, the original modes are restored from this map along with the original state paths; no other files are modified. Do not auto-correct unknown file modes or set broad directory permissions. The governed root SHA and Owner exact-action controls remain authoritative.

The static source-only tests cover six known files (including the four omitted sidecars), no-byte-copy inode/content preservation, successful `0600` handoff planning, original-mode rollback, interrupted partial chmod cleanup, symlink/hardlink/world-writable denial, unreviewed sidecars, missing optional WAL/SHM, and immutable pre-cutover DB-mode binding. These tests are now part of the required Stage C CI.

## Release and production acceptance

No edits to active WAL files, directory permissions, running services, release locks, root policy, or old signed proof are authorized here. Build an entirely new source candidate from protected main, a matching offline image and immutable release packet. Before any Owner device-code login, pass protected-source CI, pinned native Owner proof preflight for both eligible identities, signed watchdog baseline, read-only exact legacy sidecar inventory, current production source/container/DB identity checks, and root host controls. **Only then** one new authenticated Owner exact-action approval may authorize the bounded production transaction. Stage C is accepted only after the external worker is running, two distinct real provider-backed ticket scans have passed with zero duplicate items, and root postflight receipt is verified. PMv4 Stages D/E remain unauthorized.
