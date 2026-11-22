# P0 — Genuine Current-State Full SQLite Proof Before Archive Adoption

**Status: SOURCE ENGINEERING / NO ROOT ADOPTION YET.** The protected native breaker remains authoritative. This is the bounded repair of #1324 that precedes the daily archive release merged via #2672. Source merge is not permission to start a production scan.

## Verified live incident, November 22, 2026

The canonical live file is `/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3`, roughly 45.36 GB (11,074,041 pages, 4096 bytes/page) plus approximately 1.16 GB WAL on the 96%-used NVMe. The independent archive filesystem has approximately 176 GiB free.

The full-integrity service exceeded the original 5,400-second child deadline and recorded `operational_health_timeout` / exit 124. The frequent native health check subsequently failed with `full_integrity_proof_missing_stale_or_invalid`, producing one root drift finding for `jason-openclaw-authority-health.service`; the breaker correctly became OPEN. A previous Owner V2 recovery's pinned emergency `91-owner-emergency-full-proof-degraded.conf` was deleted by a separately approved later installation. The old V2 Root `--check-only` fails with a redacted FileNotFoundError; it is no longer a valid recovery procedure. Never recreate this expired override or accept its old approval.

The existing full/fast `92-owner-live-audit-location.conf` systemd fragments are Root-owned, installed, and SHA-pinned. Runtime/MCP/Ticket Core still use the original known LKG and canonical audit path. There is no observed corruption proof; the problem is an incomplete full integrity check.

## Exact repair scope

The repair introduces **one reviewed, Root-owned, one-use worker** and an updated FULL proof wrapper:
- `tools/audit_full_health_p0_recovery.py` — Root-only, clean protected-Main source, exact scope, CI, independently authenticated Owner, Root peer/current-inode/installed-override/freeze/drift checks, one-use attempt before writes, bounded child supervision and post-proof native revalidation.
- `tools/audit_full_health_p0_snapshot.py` — same four full SQLite checks, authority backup/restore parity and semantic proof verification; child timeout raised to 21,000 seconds solely for this one-use repair; still fails on timeout.
- `tools/audit_full_health_p0_operational.py` — retains `PRAGMA integrity_check` (never `quick_check`), adds only an SQLite page-cache bound `cache_size=-65536` for the oversized live WAL file.
- `tools/openclaw_authority_health_snapshot.py` — unchanged proven atomic output helper, exact source copied into the immutable Root-owned directory.
- `config/audit-full-health-p0-recovery.conf` — a **temporary** exact 93 drop-in on the already-declared `jason-openclaw-authority-full-integrity.service`. No new named systemd service, no desired-state exception, no persistent timer or daemon.

The scanner runs as `al` (UID 1000) even though its immutable supervisor is Root-owned. SQLite remains read-only at the application level, apart from normal WAL lock/sidecar operation. One 6-hour full-health oneshot is queued, so the authorized Owner's terminal need not remain open. The existing nightly timer is not changed. The worker may only execute within that existing systemd unit and only once under its audited immutable Owner claim.

**Before native revalidation**, the Root supervisor verifies the actual fresh four-database `integrity=ok`, current canonical audit path, exact authority backup/restore/count parity, key/delegation state, no provider access, and trusted output ownership/mode. It then **removes only its exact temporary 93 drop-in**, reloads systemd without restarting runtime, starts the existing frequent health check, requires its real PASS, observes three distinct independent root drift PASS samples, and invokes only the existing native release-manager breaker revalidation. The trusted script itself does not edit breaker or freeze JSON, provider data, Autotask, Ticket Core, active audit events, or root production-desired-state.

On failure, source interruption, invalid proof, foreign inode, changed override, interrupted systemd run, or timeout, the result remains FAIL. The supervisor attempts only exact-byte cleanup and leaves the breaker OPEN. The immutable one-use attempt and result remain for audit. No prior proof can be replayed.

## One-approval production execution boundary

Root must check an exact clean reviewed Main checkout; the newly merged Main SHA must have the independent **Audit Full Health P0 Recovery** workflow PASS and the complete required protected Main CI. The trusted existing Entra Owner verifier must independently verify the permitted Owner and bind the exact new source SHA, rollback LKG, source hashes, live SQLite device/inode, installed health override hashes, original release state and six-hour resource exposure to **`RECOVER-EXACT-AUDIT-FULL-SQLITE-PROOF-20261122`**. Owner browser verification and exact-action confirmation are not a Teams approval.

First use `sudo /usr/bin/python3 -I -B <clean-exact-main>/tools/audit_full_health_p0_recovery.py --candidate-sha <exact-main-sha> --preflight-only`. Only after true Root preflight PASS and Owner's authenticated exact-action grant, execute the same script with `--apply` in the local authorized terminal. It installs only the reviewed one-use Root source and temporary 93 drop-in, queues the existing full-integrity systemd unit and returns. Do **not** execute either phase from an unmerged branch or while source/CI/current Root state are not exact.

This recovery approval does **not** by itself approve the subsequent archive install, runtime/container replacement, archive data reclamation, production freeze removal or any other provider action. The existing separate archive installer must independently pass its native Root preflight and exact Owner source/scope authorization after the genuine full health PASS and CLOSED breaker.

## Completion evidence and rollback

**Source accepted** requires the negative/positive pytest matrix, real disposable SQLite corruption tests, native health compatibility, and the no-network/no-host-mount isolated UID0 Root custody, one-use claim, symlink/foreign rollback refusal fixture, CI, clean exact source and documentation control.

**Recovery accepted** requires a Root-owned receipt `/var/lib/jason-owner-release/audit-full-health-p0-20261122/result.json` with `status=verified`, full four-DB proof and restored parity PASS, real fast-health PASS, removed 93 override, independent native drift PASS, and CLOSED native Root breaker. A queued job is not completed recovery. The original historical recovery/Owner audit records are retained.

**Whole archive objective** requires a separately verified post-install event-parity / cold restore / ongoing current writes / daily timer / reboot mapping / actual source reclamation. Source-only code is not sufficient.

If a proof cannot finish even under the bounded current-state repair, return FAIL/124 and design the next independently reviewed recovery; **never** extend an expired emergency adapter or manufacture a PASS. The original 92 drop-ins remain the rollback configuration, and failure may leave the original full unit failed as expected.

## Exact protected-peer dependency correction (November 22, 2026)

The original one-use P0 source copied a **Stage E generic six-peer health**
helper. Live readback found that the running, separately signed preproduction
shadow gateway (4 GiB memory limit) is reporting UNHEALTHY because its
15-second CLI probe times out under isolated CPU/memory pressure. That shadow
uses `network_mode:none`, immutable preproduction-only image+source label,
read-only filesystem, no provider writes, no ports, dropped ALL capabilities
and no production audit database mount. Its health does **not** enter native
Root drift (`production-drift.json` reports only the failed production
fast-health one-shot), and this recovery never touches its image or resources.

The reviewed `tools/audit_journal_release_scope.py::protected_peer_inventory`
now explicitly verifies all **six** pinned production/current images, identity,
start, running state, and production peer health. For the isolated preproduction
shadow alone, it verifies its exact image/source and complete nonproduction
containment before recording its actual health (`unhealthy` remains visible)
without blocking a Root health-only SQLite repair. Any unexpected image,
network bridge, data bind, source label, missing isolation, privileged
capability, stopped container, or unhealthy production peer fails closed.

This is an *admission dependency correction for the bounded P0 repair and
journal data-only migration*, not a broader Stage E acceptance waiver or
a change to native watchdog policy, production circuit breaker, A1 shadow
configuration, memory limit, or independent production approval. The shadow
health incident remains separately actionable; never report it HEALTHY.
