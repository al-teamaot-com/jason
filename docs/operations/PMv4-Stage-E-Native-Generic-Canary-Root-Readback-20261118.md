# PMv4 Stage E — accepted native generic canary, exact root readback

**Date:** 2026-11-18. Source-only attestation extension. NO production mutation.

The one-Owner canary command completed with status accepted_and_removed,
approval owner-mcp-215fd672872d4f84a99ee17a25cf6fd5, accepted source
d85faad76881439953527d391c314df0f5d2967a, and installer source
c39545d31603f3f29db77ba880971838e20fcf26. The exact action
pmv4-e-oneowner-providerfree-native-canary-and-cleanup-v1 reported
native generic acceptance and bounded rollback, identical protected
container fingerprints, no provider calls, no changed PMv3 units, and
the original freeze and desired state restored.

Independent immediate host checks: jason-runtime and external
jason-pmv4-ticket-core healthy; live MCP and isolated shadow running;
native breaker closed and drift PASS; three real 141-item ticket-core
scans with no duplicate items; exact canary container and private
network both absent; Stage D runbook-read active. Current root-only
receipts are not accessible from the unprivileged engineering session.

The new exact root-only, read-only utility
tools/pmv4_e_canary_acceptance_readback.py validates the historic
transaction using only installed trusted signing identity and immutable
root-controlled files. It checks:

1. The accepted terminal receipt from the one-use root transaction and
   initial started root receipt, source/manifest/scope/approval binding,
   exact original protected baseline and explicit no-PMv3/zero-provider
   fields.
2. The native generic component accepted journal with the same approval,
   candidate, zero rollback SHA, freeze, manifest and scope.
3. The actual Ed25519 Owner signature on that native journal against
   the independently pinned root public-key policy, checked at the
   *historical native transaction start time* (never by extending the
   signature's original expiry).
4. The root-owned read-only canary manifest digest and provider=none
   scope, original protected root policy hash and production freeze.
5. No exact canary container, private Docker network or active pointer.
6. The existing protected C/D/A1 readback including the independent
   A1 hash-chain, protected policy and required legacy unit baseline.

All report fields are non-secret. The verifier requires root UID; it
denies missing, symlinked, writable, wrong-owner, modified or truncated
root receipts and signer artifacts. It never replays the release, uses
a provider, stops services, removes containers or modifies desired state.

**Source CI and synthetic signing tests do not themselves establish a
root readback.** The later separately authenticated exact retirement
root preflight must run an immutable reviewed copy of this utility
and treat status native_providerfree_canary_accepted_and_removed as
required evidence. The returned flags explicitly leave
pmv3_retirement_authorized=false and
replacement_scheduler_parity_accepted=false.

Next: demonstrate in an isolated test that all six new scheduling
callbacks function while old callbacks are disabled; migrate the
watchdog/reconciler legacy restart logic before building an exact
six-unit cutover and rollback transaction. No standing approval or
breaker override is provided.
