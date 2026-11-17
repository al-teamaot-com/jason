# PMv4 Stage C - one-Owner atomic Ticket Core cutover

Status: source-only release implementation. Nothing here authorizes production until the generated immutable candidate passes protected-main CI, privileged root preflight, and one fresh authenticated Owner consent for its exact scope.

## Objective

Separate Ticket Core processing from the HTTP runtime without replacing Jason's existing governed identity, policy, provider connectors, Autotask write controls, or MCP surface. Runtime and MCP remain on the protected PMv3 LKG during Stage C. Only the new non-HTTP Ticket Core worker uses the new Stage C source image.

## Exact transaction

The generated action is pmv4-c-one-owner-exact-ticket-core-cutover-v1. One Owner consent explicitly covers the bounded restart of jason-runtime and jason-mcp-pilot, relocation of the exact allowlisted SQLite families on the same filesystem, the two reviewed mode repairs (0644 to 0600), a single desired-state allowlist addition for jason-pmv4-ticket-core, creation/start of that worker, and continuation of normal governed Ticket Core processing after activation. It does not authorize PMv4 D/E, PMv3 retirement, arbitrary service restarts, a new provider identity, or changes outside the signed plan.

All container/data mutations occur while holding both existing PMv3 and PMv4 host-release locks. The original worker is required idle immediately before the container stop. Root then confirms no SQLite producer remains open before any RENAME_NOREPLACE operation. The approximately 41 GB orchestration SQLite database is not copied; its database/WAL/SHM inodes move on the same ext4 filesystem with fsynced hash-chained root evidence.

## Service boundary

The new infrastructure/pmv4-ticket-core/Dockerfile has no exposed ports and starts jason_runtime.ticket_worker_service. Effective Docker acceptance pins UID/GID 1000, read-only root, all capabilities dropped, no-new-privileges, no published/exposed ports, one CPU, 2 GiB RAM, 256 PIDs, private 32 MiB /tmp, jason-core only, exact reviewed state mounts and individual read-only credential files. Docker health uses the durable Ticket Core scan heartbeat.

The worker forcibly disables HTTP conversation handling, release/mobile/Owner approval workers, PMv2 control, production-deployment repair, procurement purchase/web profiles, Windows Time/DRMM/support auxiliary loops, and Microsoft group administration. Existing governed ticket remediation, provider reads, Datto component execution, DNSFilter remediation, Autotask notes/updates, Backup.net, QuickBooks read, hosted ticket semantics, universal query, and completion notification remain subject to current provider and orchestrator controls.

## Rollback

Before the new worker starts, rollback restores the exact original SQLite inodes/paths, the two original file modes, the original root watchdog policy, and the original runtime/MCP containers.

After the new worker has started, old SQLite paths are never restored. Rollback instead removes the external worker and returns ticket ownership to the old verified runtime image in embedded mode against the new canonical databases. This preserves every write, ticket claim, notification, and provider-result state that may have occurred after activation. The watchdog policy is then returned to its original exact bytes because the external worker is no longer running.

## Operational acceptance

A successful container start is not acceptance. Postflight requires:

1. exact runtime/MCP LKG images and the exact Stage C worker image;
2. exact effective Docker security/mount/environment readback;
3. original SQLite base inodes at their new canonical paths;
4. read-only production drift evaluation PASS before watchdog persistence;
5. two distinct real Autotask scans after the cutover-time baseline, each with provider items/evaluated items greater than zero and duplicate_items=0;
6. normal production drift watchdog PASS with the Stage C allowlist;
7. a root-owned final receipt tied to the same authenticated Owner approval.

Any failure during acceptance invokes the post-write embedded fallback above.
