# One-use signed Owner recovery — relocated authority-health journal

**Status:** Source-only preparation. This code has not been installed or executed with root privileges.

## Why a new action is necessary

The live `jason-openclaw-authority-health.service` failed because its expired emergency adapter still targets `/var/lib/jason/openclaw/orchestration-events.sqlite3`. That old path is absent. The actual `/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3` is a mode-0600 UID-1000 real file; a read-only SQL schema probe succeeds. Protected production drift opened the circuit breaker. The previous root one-shot helper requires a *timeout* outcome, but current full-health evidence is a stale PASS for the **old path**; executing the old helper cannot lawfully be made eligible by editing that evidence.

Owner approved genuine bounded relocation remediation: existing runtime/MCP/PMv4/Teams/OpenBao must not restart; freeze and signed root pins must stay unchanged; no emergency waiver, synthetic PASS, or premature breaker reset.

## New governed transaction

`tools/authority_health_live_recovery_root.py` is a strict, **one-use** root-only recovery transaction. It accepts only an immutable seven-payload manifest (exact Git code, two service drop-ins, existing signed checker/writer), exactly one fresh 15-minute Ed25519 Owner signature from the separately authenticated Entra Owner identity, and the unchanged freeze/hold, prior LKG `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`, existing OCI runtime/MCP image digests and current *failed-system-unit* breaker incident. It records an exclusive root attempt before staged work. A native release lock protects staging and is released **before** the long scan so the watchdog can run.

It root-installs **only** the verified health-only code and `92-owner-live-audit-location.conf` drop-ins, then starts the already-present bounded full-integrity oneshot. The new root-installed wrapper passes the exact relocated `--orchestration-audit` argument to the **unchanged** checker, with a 5,400s deadline and isolated cleanup. Four real SQLite integrity results, real authority backup/restore counts and integrity, key-registry/delegation checks, exact live audit path, and zero provider contact must genuinely PASS. Only then does it remove the SHA-pinned expired emergency health override, restart the *health* oneshot (not runtime/MCP/PMv4), obtain three separate native watchdog PASS observations and use the existing root-governed circuit-breaker revalidation channel. Every irreversible step is audited. A failed attempt preserves evidence, reinstates the old expired adapter if removed, rolls back only the new root files/drop-ins and stays fail-closed. The production freeze never changes.

`tools/authority_health_live_recovery_owner.py` separately runs as UID 1000, verifies the root public-key pin and signer byte hashes, requests one interactive Entra device-code Owner authentication, requires an explicit typed confirmation, signs only the exact source/manifest/scope/freeze with the protected service signing key, and creates one 0400 approval file. No private signer or OAuth token is printed or persisted.

`tools/authority_health_live_recovery_bundle.py` builds the exact immutable payload from `git show SOURCE_SHA:FILE`, not mutable worktree files, under `/home/al/.local/share/jason/authority-health-live-root-SHA_PREFIX`. Its manifest and all code are 0400 under an owner-only 0700 directory. The bundle generator mutates no live root state.

## The root bootstrap authorization boundary

**A user-owned script is never automatically a trusted root executable.** The installation procedure must use an *independently pinned full SHA-256 of the reviewed root runner* in the exact `sudo /usr/bin/python3 -I -c` command; that short verifier checks the runner's bytes *before* invoking it with `runpy`. The runner independently verifies the root-pinned Owner public key and exact signed decision **before creating any root file or systemd drop-in**. Root signer private material remains inaccessible to the root process. A direct `sudo python3 mutable-worktree/tools/... --execute` call, a `docker` workaround, reissuing an expired waiver, altering the native breaker JSON, or claiming source-only tests as live health is **not approved**.

After the protected PR and staging checks pass, the separate UID-1000 Entra sign-in and one SHA-pinned sudo invocation are the concrete Owner terminal interactions. Signatures expire after 15 minutes and are one use. Do not ask for or transmit passwords in chat.

## Acceptance criteria

- Protected GitHub checks pass for exact reviewed recovery source; source blob and stage hash readbacks match.
- Fresh Owner signature verifies against the root-owned Ed25519 public key, release source, rollback SHA, scope, manifest and frozen production state.
- Root source/install scope is limited to the two health units and scoped root code; transaction records are root-owned; no ticket or provider writes.
- Bounded full-proof result is *fresh* PASS and references the actual relocated audit path; genuine backup/restore proof is complete.
- Fast-health pass, three distinct watchdog passes and native breaker closure are verified.
- Runtime/MCP/PMv4/Teams/OpenBao container IDs/images/start times remain unchanged and production freeze SHA unchanged.
- The financial statement scheduler is **not** installed or started. Its separate approved transaction is resumed only after health recovery independently verifies complete.

This document does not claim production installation or health restoration.
