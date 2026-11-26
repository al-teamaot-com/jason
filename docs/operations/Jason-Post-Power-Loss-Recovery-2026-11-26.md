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
