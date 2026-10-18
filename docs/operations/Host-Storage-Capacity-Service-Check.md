# Jason host-storage capacity assurance

**Status:** source-only proposal until separate exact-commit production release approval. **Scope:** Jason's Ubuntu production host, not clients' Windows Low Disk Space playbook.

## Existing scheduled service — no new scheduler

Reuse `jason-self-heal-watchdog.timer`, which runs the existing `jason-self-heal-watchdog.service` approximately every **five minutes**. The read-only `storage_capacity_failures()` probe is a detector inside that service; it does not create a second timer, Teams bot, approval engine, job runner, or filesystem scraper.

Monitor two independent mounted filesystems:

| ID | Mount | Role |
| --- | --- | --- |
| `root` | `/` | OS, Docker images/build cache/volumes, Jason runtime and Git worktrees |
| `archive` | `/srv/jason/archive` | The physically separate Samsung archival SSD |

Source and configurable, validated limits: `config/operations/host-storage-capacity-v1.json`.

| Condition | Warning | Critical |
| --- | --- | --- |
| Disk usage, measured with available-to-unprivileged semantics as `df Use%` | 80% or above | 90% or above |
| Allocatable capacity remaining | less than 30 GiB | less than 15 GiB |
| Inodes used | 85% or above | 95% or above |
| Required archive mount missing | — | Investigate immediately; do not write archive paths onto root |
| Unreadable mount/statvfs/policy | Unknown/degraded, not healthy | Investigate monitoring defect |

Any condition triggers an incident; critical takes precedence over warning. The state includes exact observed used/available GiB, use percentage, inode pressure, and volume/path (but **never customer filenames or secrets**).

**Current October 18 measured baseline:** Intel primary `/`: 233 GiB (df display) / 201 GiB used / 21 GiB available, 91% `df Use%`; Samsung `/srv/jason/archive`: ~11 GiB used / 222 GiB available, 5% used. The root is **critical** now. No unapproved deletion is to be inferred from this report.

## Governance and deduplication

- The existing `issue_resolution_engine` maps `host_storage_*` to a dedicated `host_storage_capacity` incident family. Stable family fingerprint reduces repeated five-minute alerts into a durable single Support incident; retained readbacks show progression and resolution.
- A warning gets P1 attention; a critical (>90% full, less than 15 GiB, severe inode pressure or archive unmounted) gets P0. Degraded/unavailable probe is P1 unless otherwise independently critical.
- **Repair level 3**: `automatic_execution=false`, `requires_owner_action=true`. Jason may diagnose, record evidence, propose an exact bounded cleanup or storage relocation and present an approval. The watchdog itself **cannot** remove files, prune Docker, restart production, move worktrees, grant permission or initiate a provider change.
- Existing self-heal attempts remain bounded to 2; no direct remediation path responds to the `host_storage_` prefix. The existing support/Teams communications governance decides what notification is allowed and prevents duplications.
- A cleanup proposal must itemize exact paths, image/cache ownership, production/rollback references, expected recoverable capacity, approvals, verification and rollback readiness; don't assume Docker's "reclaimable" estimate is deletion-safe.
- Preserve approved images, production volumes, backups, Git worktrees used by active engineering, signed approval records, audit evidence, and client data. The archive mount must be present and verified before moving any data.

## Verification and milestones

1. **Unit tests:** healthy, warning, critical, absolute free space, inode exhaustion, archive missing, invalid policy, unreadable filesystem, no automatic cleanup and full detector integration.
2. **Safe preproduction:** run the pure probe read-only on the current host in an isolated worktree to show it reports the existing 91% primary root as critical and the archive healthy.
3. **Protected merge/release:** require normal GitHub checks, release-manager build and immutable preproduction, CCC, host drift and rollback, separate explicit Owner approval for the *exact* merged production commit. A source-only merge alone does not activate a running service.
4. **Production readback:** verify installed canonical watchdog hash, timer active, one `host_storage_capacity` persisted incident with accurate mounts/available bytes and correct repair-level approval boundary, and no file or container deletion.
5. **Recover and close:** after a **separately authorized** cleanup or storage relocation, rerun `df` and the watchdog; close only on actual capacity improvement, restored archive mount, and cleared detector evidence.

Current cleanup work is independent of code: use read-only inventory to decide whether old build cache/images, logs or archived worktrees can be safely reclaimed; never treat the monitoring threshold as permission to delete.
