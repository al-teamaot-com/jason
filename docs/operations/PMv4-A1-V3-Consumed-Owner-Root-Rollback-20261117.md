# PMv4 A1 v3 — original signed Owner rollback recovery

Status: SOURCE-ONLY recovery tool and tests, no privileged execution or new Owner authentication. Run only against the precise November 17 failed v3 isolated shadow attempt; no release promotion.

## Original source and immutable transaction

- Original protected source `c999216a3df9d2422833b90403c31530c323f467`.
- Previously authenticated, consumed exact-action approval `owner-mcp-5bb561044cd444908d06280377822a9d`; NEVER replay it for deployment.
- Native v3 release refused `SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT`, caused by Docker 29's `HostConfig.Binds` reporting the exact approved named volume as well as its separate Type=volume mount.
- Root A1 audit, signed Owner proof, native pending receipt, initial empty shadow pointer and exact root-source artifacts must be independently read and verified under root. User-level file metadata is not a substitute for root audit verification.
- The running disconnected, healthy container is not a completed release. Only the signed original rollback to the empty baseline is authorized without a new approval.

## Recovery scope

A single root-owned, hash-pinned, one-use recovery script only accepts the previous original root installer SHA, exactly one prior signed parent/child Owner grant, historical signature validity, hash-chained root audit with no commit, original native receipt and production freeze/hold/breaker/Ticket Core checks. It requires the exact isolated original Docker container ID, OCI image, source labels, network=none, no ports, non-root user, read-only root, dropped caps, no-new-privileges, exact limits and named volume. Any other project container, host bind, additional mount or provider credentials fails closed. A fresh root preflight runs before mutation. Under both existing host locks, native shadow lock and original signed rollback entitlement, only the fixed approved shadow Compose project is brought down, **without `--volumes` or `--remove-orphans`**. Then the native pending receipt is reconciled, original root-staged files are exact-inode/hash-cleaned and the hash-chained original audit is appended. Failure leaves durable pending/review evidence for bounded recovery; no other container, provider, Ticket Core or freeze mutation occurs.

## Acceptance boundaries

- Source-only regression suite covers recovered original receipt, historical parent+child proof, exact vs foreign container identity, named-volume and arbitrary bind denial, fixed Compose down argv, no-volume-deletion and native rollback ordering under locks.
- A direct Docker 29 inspect validates the *read-only* rollback target security profile against the exact original container.
- Source checkout, source SHA, freeze and hold SHA and unmodified LKG are pinned before local root stage.
- Owner TTY root preflight must independently prove prior v3 root audit and original signed receipt. If it denies, STOP; do not delete root audit/receipt or use manual docker commands.
- Owner local `--recover` is bounded to the original approved rollback and uses no new Entra decision. Independent postflight must prove the shadow container absent, baseline pointer restored, original native receipt rolled_back, original audit terminal reconciliation, exact root source cleaned, Ticket Core healthy and production safety controls unchanged.

No source PR merge, unit test, or Docker container health status can be reported as the operational completion of A1. A subsequent new immutable v4 source/image release requires its own governed exact Owner approval after rollback.
