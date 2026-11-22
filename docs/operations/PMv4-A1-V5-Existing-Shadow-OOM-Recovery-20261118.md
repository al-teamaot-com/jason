# PMv4 A1 v5: restore a healthy isolated shadow from existing accepted release

**Status: source-only, November 18, 2026. No production deployment or Owner approval issued by this source PR.**

## Current production evidence

The live root A1 shadow release pointer is
75f2b4c0c48a15bd17d700b9f039fe56623e3f52. This is NOT the
empty-release baseline. Its root-owned prior release tree, protected
manifest and scope, protected gateway token and immutable receipt and
hash-chain audit must be preserved. The previous release
c999216a3df9d2422833b90403c31530c323f467 has a historical
rolled-back-to-zero receipt; that receipt cannot authorize the current
rollout or rollback.

The exact existing jason-pmv4-shadow-gateway container is stopped with
OOMKilled true, exit 137, and an effective 2147483648-byte (2 GiB)
memory budget. Kernel cgroup logs recorded repeated memory-limit kills.
A separate approved source change increases only the shadow Compose
memory budget to 4 GiB; the reviewed native Docker adapter also now
requires the actual Docker memory budget to equal the candidate's
SHA-bound signed Compose budget, while accepting the previous signed
2 GiB release for rollback. The container network remains none,
provider mutations forbidden, read-only filesystem, UID 1000, all
capabilities dropped, no automatic restart, and no production provider
credentials.

The production global freeze, promotion hold, PMv4 shadow freeze,
runtime and MCP image IDs, native LKG and breaker all remain unchanged.
The active watchdog allows the shadow container, and independent
Ticket Core is healthy with external worker hosting.

## Exact v5 release model

The source-only immutable packet builder is
tools/pmv4_a1_v5_existing_release_builder.py. It is a deliberately
narrow versioned adaptation of the existing v4 authenticated root,
Owner signer and launcher, NOT a second signer or release manager.
Only the exact prior source 75f2b4c0c48a15bd17d700b9f039fe56623e3f52
is admitted as rollback. Source-only packet, manifest, SHA-256
reviewed scope, immutable Git blobs, existing pinned OCI image, host
snapshots, and root executor hashes must match protected main and
required CI. The builder writes no production state.

The generated root --preflight runs BEFORE new Entra Owner consent.
It verifies the previous root-owned release bundle and immutable
manifest/scope, trusted original token and its permissions, committed
hash-chain root audit, accepted prior signed one-use Owner receipt,
all historical receipts, expected current pointer, OOM-stopped
prior Docker container, both native host locks, root watchdog allowance,
closed breaker, unchanged global freeze/hold, native LKG, core/MCP health,
and exact protected main. Unknown or changed status fails closed.

One authenticated Entra Owner device-code ceremony and the exact
phrase APPROVE-ONE-EXACT-PMV4-A1-V5-SHADOW-RECOVERY signs only the exact
v5 root and child release with the same approval ID and 15-minute
release lifetime. No Teams approval or standing release grant is
required. The root consumes the exact single approval before mutation.

Within the existing native transaction, root preserves the prior release
directory, original token, original audit and history. It stages the new
release, atomically replaces only the two root-owned latest-manifest
and latest-scope files (audited before and after), and invokes the native
ShadowController with an independently SHA-checked 4 GiB candidate.
On success the shadow is healthy and disconnected; Ticket Core, MCP,
freeze, LKG and watchdog must pass final independent postflight.

On failure, the native controller restores the exact prior release
pointer and root manifest/scope. Docker Compose creates the prior
2 GiB shadow container WITHOUT starting it (preserves prior stopped
state). The old pinned image and exact reserved state volume remain.
Only newly created v5 files are removed, and native plus root receipts
record the prior rollback. If rollback is interrupted, a separate
versioned --recover command requires the ORIGINAL signed v5 Owner
proof and verifies its timestamp and cryptographic scope; it never
issues a second Owner authorization. A native accepted receipt is
never silently downgraded to rolled-back on a late root error;
that condition requires independent review.

No PMv3 timer, root drift/boot watchdog, release-manager profile,
Ticket Core, MCP, Runbook service or production provider is restarted,
disabled, impersonated or released by this isolated recovery. The
PMv3 retirement and replacement-controller parity remain separate
governed Stage E actions, even after a healthy shadow is accepted.

## Production status

Not deployed. CI and synthetic tests are engineering evidence only.
The immutable candidate must be regenerated from the final protected
main SHA and checked without Owner consent before one local, interactive,
exact authenticated root release. The current authenticated Owner's
approval of Stage C or D is NOT reusable.
