# PMv4 A1 shadow gateway: bounded 4 GiB memory candidate

**November 18, 2026 - source-only. Not deployed or authorized.**

## Evidence for a narrow capacity correction

The isolated jason-pmv4-shadow-gateway is stopped with exit 137 and
OOMKilled=true. Its Docker HostConfig memory limit is 2147483648 bytes
(2 GiB), pids limit 256 and one CPU. Kernel journal around 01:19-01:21 EST
on November 18 recorded repeated CONSTRAINT_MEMCG OOM kills of
openclaw-gatewa in the exact shadow container cgroup. At source review
the host had 31 GiB total RAM and around 26 GiB memory available.
This is container-cgroup exhaustion, not proof of host-wide memory shortage
or proof that a larger limit alone will cure the underlying workload.

## Reviewed source change

One Compose setting in config/pmv4-shadow/docker-compose.yml:
mem_limit: "2g" -> mem_limit: "4g". All other bytes remain identical to
protected parent revision e88befc72cb3600702e3492246b1b44dc10294e0.
Network none, empty ports, UID 1000, read-only FS, dropped capabilities,
no-new-privileges, pids 256, CPU 1.0, no automatic restart, no provider
token mounts, isolated state volume, and health probes remain unchanged.
The pre-existing Compose default memory+swap behavior may change with the
memory ceiling; a governed deployment review must explicitly check live
host swap headroom and Docker's effective MemorySwap after creating the
replacement candidate.

The source-only dry-run with a synthetic image and non-provider token yields
Docker Compose memory cap 4294967296 bytes. Existing A1 safety regressions
plus exact parent-to-candidate source-delta test passed (60 tests, 35 subtests).

This source PR does NOT recreate, restart or attach the shadow gateway,
rotate a token, alter production runtime/MCP/Ticket Core/freeze,
change global drift policy, consume Owner approval, or prove replacement
controller parity. Any activation is a separate exact authenticated
Owner scope with immutable prior shadow rollback, root trust checks,
bounded memory monitoring, acceptance and rollback. If memory usage rises
again, investigate rather than raising the ceiling indefinitely.
Do not retire PMv3 on this source result.
