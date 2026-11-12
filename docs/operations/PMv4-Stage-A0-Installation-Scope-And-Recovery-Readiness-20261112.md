# PMv4 Stage A0 — exact root host bootstrap / rollback preproduction packet
**November 12, 2026 — source-only, NOT a production installation or approval**

This packet follows the Project Jason Governance Handbook/Canon, immutable
Owner exact-action decisions, the existing release/production freeze, the
native root release transition and the PMv4 separation design. Source-only
PR #2443 was merged at `ada389d3d2deeca0fa2b6270ee19d0927132b198`.
Protected `main` subsequently advanced; **the exact installation SHA must
be recomputed from the final protected-main release**, never copied from
the previous PR or assumed unchanged by this document.

## A0 scope boundary (machine-reviewed inventory)

`tools/pmv4_stage_a_packet.py --scope --source-sha <exact-local-HEAD>`
emits a canonical, hash-bound, 57-file-independent **A0 bootstrap** inventory.
The CLI rejects a non-HEAD or dirty worktree. The emitted
`scope_sha256` is SHA-256 of the canonical compact JSON packet without its
own digest field. The 7 trusted source-module hashes are additionally bound
by the established `reviewed_code_manifest` bundle digest. The new
`.github/workflows/pmv4-stage-a-readiness.yml` retains the complete,
non-secret source-scope JSON and synthetic rollback receipt for independent
review. A new final merge SHA requires new CI and packet regeneration.

**New A0 objects ONLY:**

| Destination | Owner:group / mode | Payload or purpose |
| --- | --- | --- |
| `/usr/local/lib/jason/pmv4-trusted` with `tools/` and `implementation/kernel/` | root:root dirs 0755; source files root:root 0400 | 7 hash-pinned existing PMv4 trusted host modules and signed Owner verifier (no signer material) |
| `/var/lib/jason/pmv4-shadow` with `control/`, `releases/`, `receipts/` | root:1000 dirs 0750 | Separate shadow-only namespace, never PMv3 ledger |
| `.../control/signed-owner-decisions` | root:1000 dir 0770 | Bounded existing MCP Owner issuer receipt outlet, not yet enabled |
| `.../control/host-mutation.lock` and `shadow-release.lock` | root:root files 0600 | Independent transaction lock plus per-shadow lock; existing PMv3 transaction lock held simultaneously |
| `.../control/shadow-freeze.json` | root:1000 0640 | Shadow remains frozen; no active release |
| `.../control/docker-compose.yml` | root:1000 0640 | Exact static disconnected read-only candidate profile |
| `.../releases/0000000000000000000000000000000000000000/baseline.json` | root:1000 0640 | No prior shadow runtime, not PMv3 production LKG |
| `.../current` | symlink | Exact relative target `releases/0000000000000000000000000000000000000000` |
| `/etc/jason/pmv4-shadow/entra-audience.json` | root:1000 0640; parent dir 0750 | Matches the existing Jason MCP Entra client audience; no new authentication identity |

The exact code paths, file bytes, hashes, modes, expected UID/GID, new
directories and single pointer are machine-listed in the scope artifact
(11 new directories, 13 files, one symlink). No generic file copy or arbitrary
host paths are accepted by this scope. The existing `/etc/jason` parent must
be validated as root-owned/non-symlink by the independently privileged installer.

**Existing objects to preserve byte-for-byte / do not touch:**
`/opt/jason/current`, the entire `/var/lib/jason/openclaw` production
tree (including ticket/approval SQLite/WAL, immutable receipts and all PMv3
release control), the exact root-owned public Owner trust pin, service-owned
private signing key, systemd state, currently deployed containers/images,
and production freeze/automatic-promotion hold.

**Explicitly NOT in A0** (separately authorized later): a running shadow
container; MCP deploy/restart or Owner issuer activation; gateway token;
new reviewed shadow-release manifest and signed decision; active external
ticket worker; Runbook Management container; protected desired-state
changes; independent recovery-timer activation; PMv3 retirement or service
restarts. A0 must leave all existing services unchanged.

## A0 rollback: zero/empty baseline, NOT the PMv3 LKG

The correct A0 control rollback SHA is `0000000000000000000000000000000000000000`.
It identifies **absence of Stage A controls before installation**; it is
not an executable old container/image or existing runtime rollback. The
existing live production LKG remains
`690250b4d21f32cce79cab9f5b4c18cf93e7e94a` (subject to fresh
authoritative root readback at approval time).

Offline acceptance runs root-free in an isolated `/tmp` sandbox. It builds
all 11 new directories, hashes all 13 new files, verifies modes and the
relative empty-baseline symlink, and removes ONLY the declared objects. A
second acceptance injects an interrupted installation after three files;
partial rollback verifies the incomplete known set and restores absence.
Tampered content/modes, unauthorized files/symlinks, redirected sandbox
parents, wrong current pointers, and a foreign live target all FAIL CLOSED.
Sentinels representing the old runtime ledger and Owner trust are preserved.

**Production rollback is NOT authorized or proven by these synthetic tests.**
A native root installer still must implement/verify an immutable,
Owner-signed exact-stage transaction journal, backup/restore of any
pre-existing target (or refuse if no empty baseline), crash/retry
reconciliation, post-write root UID/GID/mode/digest/lock readback, and
symmetric rollback while holding the existing host transaction lock.
Never recursively erase an unknown or drifted root folder.

## Verified root recovery evidence — independently read, NO mutation

On 2026-11-12, three clean root observations at 09:25:29, 09:27:29,
and 09:29:30 UTC were stored in the bounded recovery ledger. One governed
root revalidation request at 09:29:39 UTC returned
`root_verified_closed`, and the protected control readback reports the
breaker `closed` at 09:29:42 UTC, bound to source/LKG
`690250b4d21f32cce79cab9f5b4c18cf93e7e94a`. Subsequent protected
drift readbacks were PASS with an empty problems list. The root-owned
control and drift files are mode 0600; their non-root protected-readback
copies are evidence, **not a substitute** for the independently privileged
root verifier at the last pre-mutation boundary.

The bounded root policy remains: minimum 3 distinct PASS observations,
at least 15s between observations, 90s open cooldown, max age 180s,
at most 2 authorized requests per breaker, and 300s spacing after a prior
request. This historical successful close does **not** grant a new permit or
justify directly editing the breaker. When breaker is already closed, the
recovery manager must remain a no-op.

A0 final root prerequisites:
1. Source is the exact protected-main release SHA with all required CI
   and a recomputed reviewed scope / trusted bundle checksum.
2. The existing root-owned trust pin and private signer metadata are valid,
   **without reading/copying/rotating the private signing key**.
3. Authoritative root-owned LKG, independent healthy live Ticket Core,
   container source identities, protected drift and closed breaker agree.
4. Existing production freeze/incident hold hashes are preserved; any
   allowed one-transaction exception must be separately approved and
   automatically restored, not manually deleted.
5. Existing PMv3 `production-transaction.lock` and new PMv4 root lock are
   acquired in deterministic order by the trusted root installer.
6. Future PMv4 A0 host-root, `/etc/jason` parent and target absence are
   independently root-verified. Non-root access to the `/etc/jason` target
   is currently insufficient to prove its absence: **root-only readback
   required**.
7. The separately authenticated Owner exact-action signature binds source,
   reviewed scope, immutable A0 manifest, zero rollback, and protected
   freeze. This source-only packet does not mint that signature or install
   a new approval channel.
8. Root postflight must prove no running shadow container, no new provider
   permission, preserved production/hold hashes, stable ticket/MCP health,
   and source install digests, or rollback/fail closed.

## Status and authorization boundary

**Completed:** actual root breaker recovery, full machine-readable A0
file/permission inventory, source bundle hashes, offline full + interrupted
installation and rollback tests, and independent CI configuration.

**Not yet production-accepted:** root-only check of inaccessible
`/etc/jason` target, native root installer authorization/transaction
integration, real root UID/GID readback, final protected-main source SHA,
exact live SHA-bound Owner decision, and production rollback proof.

Do **not** request or infer Stage A installation authorization from earlier
source-only promotion. No root actions, protected-control edits, service
restart, production unfreeze or runtime deployment occur in this package.
