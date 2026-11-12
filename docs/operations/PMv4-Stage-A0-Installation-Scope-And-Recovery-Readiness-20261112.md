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

## November 12 live-state refresh: separate native release and new breaker

At approximately 05:07 ET, an **independent, separately approved**
Constant Contact production release transaction
`release-4235c0f377094356` temporarily removed the freeze via its
recorded one-transaction exception. This was NOT a PMv4 operation. The
release later reported FAILED; the existing `production-deployment-freeze`
returned **byte-identically** to SHA-256
`bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`,
the promotion hold remained unchanged, and original runtime LKG
`690250b4d21f32cce79cab9f5b4c18cf93e7e94a` remained installed.

An unrelated Grafana assurance systemd oneshot subsequently returned
DRIFTED at 05:08 ET. The root watchdog opened a NEW breaker at
10:11:58 UTC with `problem_kinds=["failed_system_unit"]`, identifying
`jason-grafana-assurance.service`. Later that service completed a PASS
check and returned inactive/success, but its earlier transient failure did
not thereby close the already opened root breaker. **Stage A admission
must remain blocked until a new root-governed, independent fresh-health
revalidation explicitly closes THIS new breaker with exact current LKG
and immutable evidence.** Do not reuse the earlier `root_verified_closed`
permit or directly clear the failed-unit state without approved controls.

The machine readback now distinguishes the 09:29 historical breaker
closeout (original LKG) from the **CURRENT** protected breaker/LKG
revalidation. This prevents a future legitimate, separately approved
production release from invalidating historical recovery evidence, while
preserving the mandatory current-source, current-breaker and fresh-drift
checks. A successful service timer retry is not itself breaker authority.

This packet remains **preproduction scope/recovery preparation only**;
no Stage A deployment approval should be solicited while the current
breaker is OPEN, `/etc/jason` root-only target metadata is unverified,
or the trusted governed root installer and its real recovery/rollback
acceptance are incomplete.

**Bounded read-only recovery classification:** After Grafana assurance returned
PASS, a subsequent root drift readback reported `pass` with zero problems,
but the protected breaker remained OPEN. Running the pure, non-mutating
`release_breaker_recovery_manager.decision(...)` against that snapshot
reported `status=blocked`,
`next_action=accumulate_distinct_root_drift_passes`, one distinct fresh
observation and no new root attempts for this new breaker. The existing
policy requires three distinct clean root observations and a new root
revalidation transaction before closure. This classification does not
consume a permit, run the manager, change a timer or edit protected state.


## Disposable-root UID/GID/mode acceptance extension

The source-only Stage A0 CI now executes a *second* acceptance on a
**disposable GitHub-hosted Ubuntu runner** using that runner's root account.
This is not run against Jason's host, secrets, containers, or root state.
The test harness hard-restricts every target to a private canonical
`/tmp` sandbox and rejects arbitrary live host paths.

This acceptance validates real `chown` and `chmod` metadata for all
11 directories and 13 files against the exact reviewed UID/GID/mode
manifest, then proves empty-baseline rollback. It injects a foreign
GID on an otherwise intact installed code file and requires rollback
to refuse without deleting or changing that file. Finally it interrupts
installation after three files and verifies strict partial rollback to
absence. The corresponding GitHub job must succeed before its isolated,
non-secret acceptance receipt is published.

**Important scope distinction:** isolated CI root permissions prove the
installer's *metadata contract* but are not evidence that live protected
`/etc/jason` parent, native root release transaction, exact Owner-signed
Stage A authorization, immutable journaling or real root rollback have
been deployed. Those remain separate production acceptance gates.

## Source-only signed Owner admission contract

`tools/pmv4_stage_a_admission.py` supplies an independently testable,
**non-mutating** signed Owner admission primitive to be used only by a
future native root installer. It requires an exact protected-main and CI
callback, a clean exact-source checkout, a canonical Stage A0 scope with
all installations limited to declared new objects, the exact immutable
Stage A0 manifest, and a verified short-lived one-use Ed25519 release
decision bound to source SHA, zero rollback SHA, scope hash, manifest hash,
freeze hash and Owner identity.

It also requires independently root-verified current production health,
a CLOSED current breaker, verified empty target baseline, and root-only
target-parent metadata. Missing/altered signature, replayed proof, expired
authority, changed freeze, unapproved source/CI, modified path inventory,
or open breaker all reject. The immutable proof's public trust is read
from the existing root-owned Owner pin in production; caller-provided
test keys are allowed only in disposable tests. This is not a second
signer or a parallel approval system.

**Important:** This module cannot obtain an authenticated Owner session,
mint a signed approval, acquire protected production locks, install files,
write an authorization receipt, or satisfy root installation by itself.
The future native release boundary must obtain trusted root health and
the actual Owner decision independently, perform this check *while holding*
the cross-release lock, journal exact actions before each write, then
read back/rollback as necessary. Passing tests do not authorize deployment.
