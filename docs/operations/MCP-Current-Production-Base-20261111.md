# Governed MCP preproduction base after initial Teams-free cutover

## Problem observed November 11, 2026

The historical MCP builder base `jason-mcp:generic-governed-8f1e864947a2`
was removed in an earlier incident. The one-time V2 fallback recognized only
the V2 protected LKG revision `c43e88e072c0b35c5b342d5e712fe34565b3e0cd`.
After the successful Teams-free production release
`ee46ef631e04678a16f2543c76a8ee08ec974265`, the LKG is no longer V2,
so preparation of the **status-indicator-only** candidate
`54049b026b0e6d6cf444dd9b5090d43e0b1c0d08` stopped **before a release
record, any MCP build or production mutation** with
`missing MCP builder base and no root-attested V2 recovery base`.

## Safe correction

The controller continues to prefer the exact historical immutable generic MCP
base, and preserves its one-time V2 pinned fallback without relaxing the
digest. If both are unavailable, a current non-V2 base is accepted only when:

- the root **protected last-known-good** manifest is complete, contains a
  valid 40-character revision and exact SHA-256 MCP/runtime image IDs, and
  declares the verified `owner_reviewed` release mode;
- the independent root breaker is **closed** and revalidated at precisely that
  protected revision;
- live MCP and runtime revision/alignment match the root revision, and their
  actual image digests match the root-pinned digests byte-for-byte;
- the images are present locally at the immutable `sha256:` references; and
- a deterministic `jason-mcp:attested-lkg-<revision>-<digest>` **nonproduction
  tag** is absent or resolves to that same root-attested image. A substituted
  tag fails closed rather than being overwritten.

The only permitted artifact change is creating this non-production builder
tag; no live container, provider, ticket, root policy, release approval, source
revision, LKG, drift, freeze, or service is mutated. The actual base image ID
is returned and retained in the subsequent release manifest.

Unit acceptance covers both original V2 fallback behavior and new verified
current LKG, denied open/mismatched root, mismatched image digests, misaligned
runtime/MCP and substituted tags. An isolated preproduction build must
subsequently prove the complete runtime and MCP image suitability.

This fix is **source only** until separately reviewed and merged. A release
built from the new source still requires fresh scope review, preproduction
acceptance and authenticated Owner approval bound to that exact SHA. Do not
reuse `release-ee46ef631e04678a` approval or disturb its production freeze.

Integration coordination: #2430 #2427 #2428
