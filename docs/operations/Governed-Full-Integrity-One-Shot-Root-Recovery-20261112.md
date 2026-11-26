# Owner-authenticated, one-shot real full SQLite integrity proof recovery

**Date:** 2026-11-12. **Status:** SOURCE ONLY; NOT INSTALLED OR EXECUTED. This is a scoped emergency health-evidence repair, not a release freeze bypass, authority waiver, alternate integrity standard, Docker deployment, ticket workflow mutation or standing root capability.

## Verified incident and immutable host baseline

- [#1324](https://github.com/al-teamaot-com/jason/issues/1324): the existing daily full SQLite integrity/authority-backup proof timed out after the prior 3,600-second bound, with FAIL/124. The full audit database is ~36.6 GB decimal (8,950,336 SQLite pages); the authority DB ~4.1 GB. Earlier full runs finished in ~50m (11/07) and ~57m (11/08), but no current genuine PASS snapshot exists.
- The separately authorized emergency degraded-read-safe five-minute fast-health adapter expired at 2026-11-12T15:00:00Z as designed. The authority-health systemd one-shot failed; root production drift watchdog opened the root circuit breaker. At 16:09 UTC, the only remaining drift cause was failed `jason-openclaw-authority-health.service`. A concurrent Grafana assurance transient independently healed; this runner never suppresses other failed units.
- Current independently verified complete root LKG, host, runtime and MCP: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. Runtime image `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`; MCP image `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`. Freeze SHA256 `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`.
- Protected main merged #2390 at `9c2143c2c2f6dcc30aeeb13d0f042bff3074f04b`, including a fully unchanged actual checker, bounded 5,400-second parent-owned full proof and private archive backup cleanup. The updated source is NOT installed into the production release. The existing restored Owner Ed25519 signer is still read-only mounted into MCP. Independent archive drive `/srv/jason/archive` has ~185 GiB available.
- Source-only Constant Contact OAuth MCP credential projection #2462 also merged. OpenBao OAuth client secret (version 1) and AppRole were independently verified; no OAuth consent, AOT account binding or contact import has occurred.

## Purpose and exact-action authorization

A root-pinned, one-shot runner `tools/owner_full_integrity_recovery.py` allows **only** a single full `PRAGMA integrity_check` across the four canonical SQLite files, existing authority SQLite backup/restore/count parity, and a gated return to normal systemd health and native root breaker revalidation **after a genuine complete PASS**. It reuses the already installed root-owned Entra JWT verification and signer trust, never passes through an unverified Teams account. It prints an exact-action device-code challenge and independently verifies signed Owner OID/tenant/audience/scope. Approval is bound to the immutable root-installed script bytes, checker/snapshot bytes, baseline LKG images, full 90-minute scan, archive scratch and freeze digest.

**This scan may use host disk bandwidth and CPU for up to 90 minutes.** It runs under `al` at Linux `nice -n 19` and `ionice -c3` (idle I/O class), reads live SQLite and makes temporary authority backup/restore copies only on the independent archive volume. The root supervisor bounds it to 5,700 seconds, terminates the entire scan subprocess group on timeout/interruption, and records actual failure without clearing the breaker. It does not restart any user-facing service, runtime, MCP, network connection or ticket worker; it starts only the existing read-only authority-health and drift-watchdog one-shots *after* a real integrity PASS. The archive scratch directory is parent-owned and cleaned even on timeout.

## Fail-closed conditions

No execution unless:
1. Root-owned `/usr/local/lib/jason/owner_full_integrity_recovery.py`, two root-owned pinned checker source files under `/usr/local/lib/jason/full-integrity-recovery-20261112/`, and root-owned exact manifest `/etc/jason-owner-release/full-integrity-recovery-policy.json` have byte-for-byte matching SHA256, no symlinks or writable parents. Ledger is root-owned mode 0700 and does not already contain this action.
2. Root reads the actual control/drift, exact LKG/containers and signer bind. Production breaker is genuinely OPEN because only known health one-shot failures are present, the most recent canonical full snapshot truly failed from a timeout, the full integrity service is not running, the two normal health timers are active, original freeze bytes have not changed and archive has at least 24 GiB free.
3. Fresh authenticated Owner signs into the existing Entra device-code flow, sees the exact action and confirms before the long scan. No prompt includes or logs Constant Contact credentials, encrypted tokens or ChatGPT conversation contents.
4. Scanner completes with nonzero errors refused; an authoritative full PASS requires fresh mode-0600 `al` file with *all four* SQLite `integrity=ok`, authority `backup_integrity=ok`, `restore_integrity=ok`, count parity, trusted key registry and no expired active delegated authority. Provider contacted must be false; prior stale or simulated PASS is denied.
5. Only then existing five-minute health unit is restarted and checked `status=pass`; the native drift watchdog runs **after** releasing the shared production transaction lock. Independent `release_manager_host_runner.revalidate_circuit_breaker()` executed as `al` requests the existing root-governed transition. Root independently verifies LKG, root drift and health before closing breaker. The recovery helper never writes the protected root circuit breaker directly.
6. Root-owned one-shot attempt and result receipt persist with action scope, timestamps, signed Owner OID, source SHA and true/false results. Failure after a real proof may leave breaker OPEN, not fabricated CLOSED. No automatic replay.

## Validated local installation boundary (Owner terminal, after exact CI/source review)

Review the final immutable PR SHA, root installer paths and source hashes. Do not run from a mutable worktree if its checked-out HEAD or dirty state differs from the reviewed commit. Install only these files using existing Owner sudo; installation does **not** start a scan:

```bash
cd /home/al/jason-worktrees/owner-full-integrity-proof-recovery-20261112
git status --porcelain
git rev-parse HEAD
python3 - <<'PY'
import hashlib, json
from pathlib import Path
p = json.loads(Path('config/full-integrity-recovery-policy.json').read_text())
for k, f in [('source_script_sha256','tools/owner_full_integrity_recovery.py'),
             ('snapshot_sha256','tools/openclaw_authority_health_snapshot.py'),
             ('checker_sha256','tools/openclaw_authority_operational_health.py')]:
    assert hashlib.sha256(Path(f).read_bytes()).hexdigest() == p[k], k
print('PREINSTALL_EXACT_HASHES=PASS')
PY
sudo install -d -o root -g root -m 0755 /usr/local/lib/jason/full-integrity-recovery-20261112
sudo install -o root -g root -m 0555 tools/owner_full_integrity_recovery.py /usr/local/lib/jason/owner_full_integrity_recovery.py
sudo install -o root -g root -m 0555 tools/openclaw_authority_health_snapshot.py /usr/local/lib/jason/full-integrity-recovery-20261112/openclaw_authority_health_snapshot.py
sudo install -o root -g root -m 0555 tools/openclaw_authority_operational_health.py /usr/local/lib/jason/full-integrity-recovery-20261112/openclaw_authority_operational_health.py
sudo install -o root -g root -m 0444 config/full-integrity-recovery-policy.json /etc/jason-owner-release/full-integrity-recovery-policy.json
sudo install -d -o root -g root -m 0700 /etc/jason-owner-release/full-integrity-recovery-ledger
sudo python3 -I /usr/local/lib/jason/owner_full_integrity_recovery.py --check-only
```

**Separate authenticated exact-action execution, only after an explicit Owner decision on the potential 90-minute production I/O impact:**

```bash
sudo python3 -I /usr/local/lib/jason/owner_full_integrity_recovery.py --execute
```

Keep this Owner terminal open while the full proof runs. The one-time Entra code is issued by the root helper, not this document; its actual Owner identity must pass native JWT checks. No plaintext secrets are printed. If the process fails, do not restart it or clear the breaker without reviewed new evidence.

## Post-execution continuation (not automatic permission)

Once proof and root breaker are independently VERIFIED, prepare a **separate** native, immutable, exact-SHA/rollback production release of #2390's persistent 90-minute full-health code and systemd unit. Keep unrelated PMv4 Stage A0 issuer activation disabled and do not silently promote broad main. Verify the next scheduled full integrity and the five-minute health timer; preserve core ticket service health. Only then install the independently source-reviewed Constant Contact OAuth MCP credential projection #2462 with its distinct fresh signed Owner approval, verify real OAuth/account/list and consent-backed 1–3 contact import/readback, and enable the independently governed GET-only scheduler with its approved root units.

The code in this PR is **source-only**. No live health service, SQLite record, callback, OAuth token, contact or production freeze is modified merely by merging it.
