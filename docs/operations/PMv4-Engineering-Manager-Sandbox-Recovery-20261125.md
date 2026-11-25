# PMv4 engineering manager sandbox recovery

**State: source-only preparation; no installation or activation authority.** Relates to #1069, #2300 and #2400.

## Actual incident and recovery

The authenticated exact engineering resume at 13:20:42 EST was rolled back following the first real 13:25 scheduled execution. The existing native admission guard correctly rejected its root-owned Stage E receipt as untrusted inside the user manager's implicit user namespace. On the host the receipt is UID/GID 0:0, mode 0444; in the exact hardened user-service sandbox it is 65534:65534, while the namespace maps only 1000 to 1000. The scheduled worker's independent production health reader also requires actual root custody. Do not accept UID 65534, relax ownership checks, or remove sandbox isolation.

The native watchdog opened the release breaker because the engineering service failed. The exact authorized rollback restored the original pause bytes (SHA256 4a5de8286bf9d77842ca94dafe6f1d38c1a835e8f12bc0dfda46b7a3cf867747), retained immutable approval and failure evidence, and cleared the failed-state latch only after the pause was restored. Native drift evaluation passed and the existing root transition revalidated LKG d1b8c196dadd4b672ec8ba47075f27bb61c98d63 at 13:28. The production freeze and promotion hold remain unchanged. No application container restart or provider write occurred.

## Verified isolated correction

A disposable system-manager oneshot running **User=al, Group=al**, NoNewPrivileges=yes, PrivateTmp=yes, ProtectSystem=strict and ProtectHome=read-only retained actual root UID visibility. Its real installed worker health reader returned native_readback_live_core_and_authority_verified with production_authority=false. It did not execute a production engineering pipeline.

A separate provider-free Git fixture under /srv/jason/archive/engineering-artifacts/engineering-manager-fixture-20261125-xb4mW3wT demonstrated that allowing only the pinned checkout's .git metadata and the existing worktree output path to be writable permits local fetch and worktree creation. The pinned checkout remained read-only, HEAD unchanged and worktree clean. No provider call occurred. The live source checkout's .git was previously read-only even in the system-manager sandbox; this narrow path is required.

## Prepared source and remaining exact release

The generated successor unit/timer and policy delta preserve original worker commands, both original gates, pause, cadence, sandbox, and existing writable paths, add unprivileged system-manager identity and the narrow Git metadata path, and require a separate native root-controlled successor receipt/guard. The source-only generator has no install or activation command. Do not enable either candidate unit by copying these files.

Complete the existing manager-aware native release path, not a new scheduler or bypass:
- Retain the original accepted Stage E marker and immutable historical receipt. Implement a separately authorized root-owned successor admission receipt/guard that binds the exact prior Stage E marker, candidate, rollback, scope and system unit hashes, and fails closed unless the original user timer and service are retired.
- Adapt the canonical Release Manager schedule alignment and watchdog to independently verify that same manager routing evidence. Preserve the same scheduled-control names, require the system timer active and user timer absent/inactive, and keep incident intake durable. Do not grant the unprivileged watchdog root systemctl authority; its queued incident can be consumed by the existing five-minute system timer.
- Review exact before-images, effective desired-state policy manager membership, installed worker/module identities, actual .git symlink target, lock and protected peer state. Prepare one native transaction and rollback that uses the existing exact authenticated Owner verifier and native locks, while retaining the pause during topology cutover. Disable/retire the user trigger before enabling the system trigger; never run both. Rollback restores the exact original manager topology and files; keep the engineering pause if acceptance fails.
- Require protected-main CI, root admission review, exact Owner authorization, real systemd sandbox proof, same-runtime native drift/LKG/breaker readback, then a real normal scheduled engineering cycle with actual dependency claims, overlap denial, fresh health, and unchanged protected peers before claiming completion. No new feature admission ahead of these gates.

The candidate intentionally does not include a native installer, successor receipt issuer or the live Release Manager/watchdog routing adaptation yet. Historical root source/approval records and the live host remain unchanged by these source changes.
