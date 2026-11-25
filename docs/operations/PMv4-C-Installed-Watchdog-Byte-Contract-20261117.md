# PMv4 Stage C — exact installed watchdog-policy byte contract (2026-11-17)

**Purpose:** Repair source-only release packet generation after the protected root preflight rejected the first Stage C packet with `C_WATCHDOG_BASE_CHANGED`. **No production policy has been edited. No root release action or Owner approval was consumed.**

## Evidence and cause

Owner-supplied read-only privileged `diff -u` compared Stage C packet `production-desired-state.base.json` to `/etc/jason/release-readback-recovery/production-desired-state.json` (2026-11-17). The reported difference was the JSON object property order and the order of the two `required_system_units` / `required_user_units` arrays. Field names, types and membership were unchanged; all other arrays retained their ordering. The source config is still the byte sequence with SHA-256 `db3eaf92b16ccfb3d0bad6bd351ab99bffb84bd9a338bb8321ac7c0691562b50`. Reconstructing the observed installed formatting (`json.dumps(..., indent=2, sort_keys=True)` with the two required-unit arrays sorted) yields expected SHA-256 `9d3d4a634f2b347b760da80e0dc2bb057d3b35ddcbaf88293bffd47971d0c804`.

The latter SHA is **derived from the supplied complete diff, not a privileged hash readback**. The independent root preflight retains its original byte-for-byte SHA check and must verify the actual installed file before *any* authenticated Owner approval. If the reconstruction is not exact, the release still fails closed with no production changes and must be investigated rather than bypassed.

## Narrow fix

`tools/pmv4_c_immutable_builder.py` now serializes only the two explicitly known order-insensitive required-unit arrays lexicographically, then writes object keys in sorted order with two-space indentation and the original terminal newline. Duplicate or nonstring required-unit entries are rejected. The base artifact and proposed one-worker allowlist addition derive from that **same** normalized baseline; the signed plan pins their exact hashes. The tracked `config/production-desired-state.json`, Stage A1 acceptance tests, root policy, strict root SHA checker, release freeze and promotion hold remain unchanged. The only candidate policy addition remains the optional `jason-pmv4-ticket-core` container.

## Release governance

The old source `baca40acdbf98938c93ebb8edcaeeca446696a5f` packet is superseded, not reused. Since unrelated source merges also advanced protected `main`, Stage C needs a freshly reviewed protected main SHA, image label/image digest, immutable release packet and root preflight; no prior approval applies. The root preflight is also required to revalidate current source/CI, protected runtime/MCP identities, credential and provider-state paths, SQLite/WAL identities, freeze/hold, breaker, root watchdog bytes, and exclusive host-release controls. No production restart, mount migration or worker activation is permitted before exact Owner authorization. After release, verify two distinct real provider scans and zero duplicates, or follow the already signed rollback contract.
