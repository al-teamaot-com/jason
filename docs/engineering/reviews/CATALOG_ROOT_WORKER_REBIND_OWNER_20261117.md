# Exact catalog root-worker/projection rebind — 17 Nov 2026

**Source-only. Not an Owner approval, root installation, runtime/MCP promotion, or Autotask write.**

The previously approved catalog root bootstrap installed the original 17-file bundle. The four recovery units are now admitted to the effective production desired-state allowlist, and the native breaker has been independently revalidated closed. Source PRs #2554 and #2557 correct the root worker's trusted installed-file mapping and pin its native deployment helper's missing `pmv4_mcp_projection.py` dependency. Neither source merge changes the already-installed root worker.

`tools/catalog_root_worker_rebind_once.py` provides one narrowly bounded **root installation** using the read-only, canonical SHA-verified plan from `tools/catalog_scoped_projection_rebind_plan.py`. The root operation requires a root-owned 0500 script pinned by SHA256, original installed policy/worker hashes, current protected main and required CI, original production freeze, healthy native breaker/drift, a root-owned accepted one-use bootstrap retirement receipt with matching consumed Owner consent, the retired bootstrap timer still disabled, root-owned policy and module targets, active scoped rollback timer, both native production/PMv4 host mutation locks, and a fresh Entra Owner device login with exact typed consent.

The only authorized mutations are:

- Atomically replace the existing root-worker bytes with the exact protected-main blob and store the original root worker for rollback.
- Add exactly one root-owned, Git-hash-matching `pmv4_mcp_projection.py` sibling module.
- Atomically update exactly `source_sha` and `root_worker_sha256` in the installed root policy, leaving every other control unchanged.
- **Never change the already retired bootstrap timer**: its separate 18 Nov 2026 exact Owner-approved retirement must be proven by matching root-owned accepted and consumed audit receipts, an ancestry check against protected main, and disabled/inactive systemd state. Keep the scoped catalog rollback timer active and enabled.

The root transaction records Owner identity, exact confirmation, source/plan/freeze hashes, one-use audit and original bytes *before* the first mutation. It verifies both pinned native preflights in read-only mode, all five protected Docker container IDs/images/start times, frozen bytes, the accepted bootstrap timer retirement, scoped rollback timer state and installed file hashes. On failure it restores only the exact original worker and policy, leaves the previously retired timer disabled, removes the new module if still byte-matched, and reports unverified rollback as a hard blocker. It never starts, stops or replaces the runtime/MCP containers, unfreezes production, authorizes provider writes or extends Owner allowlists.

After installation, catalog offer staging, one-use Owner-signed runtime/MCP image promotion and governed inactive-service write/readback remain **separate, still unauthorized actions**. This installer cannot authorize any of them.

Acceptance tests cover the source-only plan hash and scope, unmodified raw Git bytes, required protected CI checks, exact worker/module/policy transition with separately approved timer retirement (including denial of forged Owner receipts or reactivation), and rollback on rejected pinned MCP preflight. Source PR merge alone must not run this file as root.
