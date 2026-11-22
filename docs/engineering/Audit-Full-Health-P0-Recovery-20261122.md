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

## Protected-Main trust-core pin correction after #2674 (November 22, 2026)

The first Root preflight on accepted Main `b3e20ef812f9f91106ed792a005d217910e231de` correctly stopped **before any installation or Owner challenge** with `AUDIT_P0_PREVIOUS_APPROVED_TRUST_CORE_CHANGED`. #2674 changed exactly the reviewed `tools/audit_journal_install.py` peer admission (and nothing about approved Owner identity or Root privileges); the P0 wrapper still pinned its earlier digest `75749e0acc4062e0a0160cb0d7ddc10504ea452f49fd432c0250193f02b86f81`. The actual exact Main Git blob digest is `64f451c03fe75b70c80462938d1199f35ce73b82f6b2ef4891e3c7d9c879e432`.

The correction updates **only the expected exact hash** in `tools/audit_full_health_p0_recovery.py`, retaining the real pinned `git show <exact-main>:tools/audit_journal_install.py` byte-for-byte comparison and independent Root lock/CI/Entra consent. A new CI test asserts that all four chained trust-source pins equal the committed bytes: P0→journal installer→documentation publisher→PMv4 E closure→PMv4 E dispatcher. A separate portable positive test exercises the actual reviewed nested Root bootstrap source path without requiring the GitHub runner to possess Jason's Root identity; the negative test confirms an intentionally stale pin denies before authorization. This is a test of source bootstrap, **not** a claim that an unprivileged runner executed production Root preflight.

Existing exact launcher referencing Main `b3e20ef8...` is superseded after this correction merges. The newly reviewed Main SHA must pass all required CI and the Root `--preflight-only` gate before *any* one-use real job is queued. The initial failed preflight did not consume or replay the Owner approval and did not change systemd, the breaker, or audit data.

## Genuine integrity PASS and failed Root finalization (November 22, 2026)

**Verified at 08:06 EST:** The approved one-use P0 Root worker 1103490 completed the full SQLite proof at 07:56:24 EST. Its full-health report was status PASS, zero failures, source exit 0, and full `PRAGMA integrity_check` = `ok` for the authority, replay, security-audit and canonical orchestration-audit SQLite databases. Backup/restore integrity and count parity passed, the trusted key registry had one active record, and there were zero expired active delegations. Normal fast health subsequently returned PASS. Native Root drift at 08:05:34 returned PASS with zero findings, but the breaker remained OPEN.

**Failure was in cleanup, not database integrity.** The P0 worker attempted to unlink its exact temporary 93 systemd override while running inside `jason-openclaw-authority-full-integrity.service` with `ProtectSystem=strict`. The reviewed unit did not grant `ReadWritePaths` to `/etc/systemd`, so its own Root worker could not remove that file. The worker logged OSError, exited 2, left its exact temporary 93 override installed, and did not reach its native breaker revalidation. No production data was reclaimed, cut over or deleted. Never re-run the consumed one-use worker or fake Root acceptance.

### Bounded finalization recovery

The source-only `tools/audit_full_health_p0_finalize.py` addresses only this approved unfinished cleanup, under a **new independently authenticated Owner exact-action** and new protected Main source. It executes directly from an authorized local Root terminal, outside the read-only service mount namespace, and does **not repeat** the expensive genuine full-integrity scan. The finalizer:

- Checks a clean exact Main SHA, required protected branch CI and its own exact Main-push workflow, reviewed four-hop trust pins and currently installed Entra Owner verifier, governing production release locks, freeze, hold, rollback LKG, exact source and image identities.
- Requires the Root-owned original one-use Owner claim for candidate `8f8228f83ff80250e1500f7da5fe7d3ca848dc26`, scope SHA256 `14da3648487c0edc9f624fd65fa0b409dc6e61db9fab39707f6fe4907c7b183a`, original Root source, one-use work-start evidence and exact failed result: genuine full-proof verified, OSError, unremoved temporary 93 and native breaker still OPEN. Any changed original record or alternate error denies.
- Independently re-verifies the fresh genuine four-database full integrity, backup/restore, key/delegation health, fast health after full proof, original live SQLite device/inode, exact 93 override hash and unchanged protected health 92 files, and refuses any unrelated native drift or breaker status.
- Obtains a fresh exact Owner identity and scope grant, persisting one Root-only one-use attempt before mutation. It unlinks only the reviewed exact 93 override, fsyncs its parent, reloads systemd, resets the failed full service to restore its original 92 configuration, and invokes existing native fast-health/three-distinct-drift-sample/breaker-revalidation mechanisms.
- Marks completion only after independent native circuit breaker CLOSED and Root-owned verification evidence. Any failure leaves the result FAIL and cannot authorize archive cutover. It never writes provider data, touches SQLite records, changes freezes, installs a new daemon, modifies shadow resources, restarts runtime/MCP/Ticket Core, or bypasses breaker checks.

The separately governed daily archive installer still requires full independent Root admission and the exact `ADOPT-EXACT-DAILY-AUDIT-JOURNAL` approval after this health finalization has verified native breaker closure. The archive objective is not complete without real event parity, subsequent writes, cold restore, scheduled daily archival and reclaimed root-drive space.

**Validation:** The synthetic source tests exercise older/altered/fabricated proof denial, exact authorization, foreign override and symlink refusal, one-use Root evidence, cleanup ordering and real native breaker enforcement. A network-isolated, no-host-mount Root fixture independently verifies Root custody and allowed file changes. These engineering tests do not substitute for actual production Root acceptance.

**Proof TTL compatibility:** The post-PASS finalizer accepts a real full proof only while it remains within the existing native fast-health source's 30-hour maximum. It independently requires fast health PASS observed after the full snapshot, and the exact old and new Owner approval source identities. No source proof is renewed or synthesized.

### Separate preproduction shadow OOM did not invalidate actual SQL proof

The exact isolated preproduction shadow's OOM exit was observed at **06:42:03 EST**, during the long P0 full-integrity scan, without affecting full SQLite results or other production peers. Subsequent live readback still shows the original canonical journal inode, full four-database PASS, backup/restore PASS, normal fast-health PASS and unchanged production freeze and LKG. The source-only audit health-finalization and daily audit migration gates now record the exact stopped preproduction shadow state without requiring an unrelated restart. This permits progress only if every original shadow isolation and image/source security invariant matches and **all production peers remain actively running and healthy**. This does not resolve the separate PMv4 Stage E shadow readiness objective, and it does not authorize modifications to the shadow container.
