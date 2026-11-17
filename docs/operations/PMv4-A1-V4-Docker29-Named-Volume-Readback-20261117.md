# PMv4 A1 v4 — Docker 29 named-volume readback correction

Source-only change. The signed v3 A1 release (candidate `c999216a3df9d2422833b90403c31530c323f467`, approval `owner-mcp-5bb561044cd444908d06280377822a9d`) was consumed and rejected during actual shadow activation with `SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT`.

## Evidence

The actual isolated `jason-pmv4-shadow-gateway` reports an approved Docker named volume both as a `Mounts` item of type `volume`, name `jason-pmv4-shadow-state`, destination `/home/node/.openclaw`, and as `HostConfig.Binds=["jason-pmv4-shadow-state:/home/node/.openclaw:rw"]`. Existing `DockerShadowAdapter._check_container_ownership` correctly verifies the first representation but incorrectly requires the second representation to be empty. The live container reports network `none`, root filesystem read-only, non-root UID/GID 1000, dropped ALL caps, no-new-privileges, no ports, no restart, and the signed 2 GiB / 256 PIDs / 1 CPU bounds. This incident has an original empty shadow pointer and an outstanding failed native recovery transaction: container health alone is NOT operational acceptance.

## Strict correction

Accept only `None`, `[]`, or the single exact named-volume bind form documented above, while keeping all separate `Mounts` type/name/destination checks. Arbitrary host paths, other named volumes, additional binds, wrong destinations and changed resource/security settings continue to fail closed. Do not change Docker settings, runtime permissions, other mounts, provider secrets, production Ticket Core or production freezes.

## Verification

- Focused PMv4 A1 + Docker adapter regression suite: 88 passed, 35 subtests passed.
- An actual live Docker 29 inspect readback passed the corrected isolated runtime security verifier, without changing any running object.
- No original v3 approval reuse, no root audit cleanup, no live Docker mutation or source deployment.

## Separate required recovery and release

The original signed v3 failed transaction must first be independently root-reconciled and the prior exact shadow container removed without deleting named volumes or touching Ticket Core. Only after the original root audit/receipt and empty baseline are verified may a new immutable source+image candidate be prepared for a separately governed, fresh Owner exact-action release. This source-only PR is not a production release, root-executor replacement or Owner consent.
