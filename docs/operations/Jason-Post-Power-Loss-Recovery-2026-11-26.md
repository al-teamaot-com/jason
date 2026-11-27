# Post-power-loss recovery, 2026-11-26

Scope: recover the already-installed external ticket worker only after the observed missing transient credential bind mount; ensure SQLite WAL files exist before the independently sandboxed runbook reader starts, and retain an idle read-only anchor during its lifetime. No provider permissions, registry rows, ticket authority, breaker policy, release freeze, or application images are changed.

Host installation targets (new release approval required):
- tools/jason_boot_recovery.py -> /usr/local/sbin/jason-boot-recovery (root:root 0750).
- tools/runbook_wal_prepare.py -> /usr/local/lib/jason/runbook-management/prepare_wal.py (root:root 0644).
- infrastructure/pmv4-runbook-management/jason-runbook-wal-prepare.service -> /etc/systemd/system/jason-runbook-wal-prepare.service (root:root 0644).
- infrastructure/pmv4-runbook-management/jason-runbook-management-read.service -> /etc/systemd/system/jason-runbook-management-read.service (root:root 0644).
- implementation/autonomous_remediation/runbook_management_read_service.py -> independently installed runbook component via its governed release path, not an unrelated application deployment.

Acceptance: synthetic exact-failure, intentional stop, missing mount, existing worker/lock, health check, and production transaction tests; synthetic WAL preparation with unchanged database hash and current writer visibility; reader sandbox and socket acceptance; then exact authenticated Owner approval, component backups and rollback readback, controlled installation, host service/worker/lock and socket verification. Do not reboot production for a test without separate authorization. Do not close the breaker automatically. Rollback must restore the exact pre-install file contents and modes and remove only newly added unit/helper; maintain the existing production freeze and preserve data.

The live incident was restored separately without deploying this candidate. This document does not grant authorization.

## Integration and scoped release evidence

PR #2700 at e19a88665c8298c82fd9676d1df15435ce8cf03f adds procurement workflow approvals to the same MCP server file, but does not modify the autonomy status snapshot. The merge-tree simulation with this repair succeeded; the two changes remain separate. Review again if the other PR head changes.

The MCP-only status revision 3ef8dc7f15d305bc02fd178d41ad8852681bd732 changes only the status projection and its regression tests relative to the actual deployed source d1b8c196dadd4b672ec8ba47075f27bb61c98d63. The isolated candidate image sha256:bd7a45c8127e39cc115c069384c021c5fdc3b33d98c01b5b4d2b9bddc7709fff retains the exact rollback image sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477 layer prefix and service UID. This is build evidence, not production admission. Do not promote the combined main revision.

The host/runbook source candidate 352049dabea5a9ddcd8ceace862e6a3dacaccf5e remains a separate file-scoped release. Live baseline SHA256 values for rollback verification:
- Boot script: 2572d60d5b43c3c75d980c7623976c9074905dbafd5915ddb796b59b126f2a2a.
- Runbook reader unit: 8251faaa4b7aafbac87243cd5f645c385483e0e23ed19ed8b6d6da79d3574a0d.
- Runbook reader source: a615ef6a91c88822562778d1731a48ac616684f877f48038064d86219d4062dd.
- Production freeze (unchanged): bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f.

The original status reports end-of-scan occupancy as though it were available capacity. The new projection requires two fully observed no-progress intervals for a sustained stall; it retains unhealthy-worker and stale-scan classifications. These changes neither create new ticket work nor modify existing admission authority.
