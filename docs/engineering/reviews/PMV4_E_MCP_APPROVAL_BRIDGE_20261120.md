# PMv4 Stage E approval bridge — draft source review

## Observed problem

The installed Stage E bootstrap reads a short-lived signed Owner request from
`owner-proof.json`. The previously approved candidate is
`510243494efcd592a1585c681a3fa28a29296e17`, with rollback
`d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. The observed candidate
directory contained expired proofs and no current `owner-proof.json`. The
installed root host reconciler does not admit a Stage E action. The connected
operator session is UID 1000 and does not provide the governed root execution
path needed to replace the reconciler or install a new trust bundle.

The approved candidate is an ancestor of protected main observed at
`fb1d5f57c57c3675896eb06ca88b236c7718d6e8`, but the existing
`verify_pinned_candidate_against_main` denies it because later protected
commits touch release controls and scope. Of the 60 files in that historical
Stage E review, `tools/release_manager_host_runner.py` changed. A newer
candidate requires a new exact review. The old approval must not be silently
transferred to a different SHA.

## Draft implementation

- The feature-gated MCP tool verifies the authenticated Entra Owner, exact
  decision and protected main, checks the live freeze fingerprint, reuses the
  existing Ed25519 signer, and queues the typed Stage E request. The source
  activation profile defaults to **off** and rollback also forces it off.
- The proposed root worker accepts only the typed Stage E action, independently
  checks a root-owned exact candidate/rollback/scope/manifest/freeze policy,
  verifies the original Owner signature and active identity, and preserves the
  signed decision in a root-only journal before invoking the pinned bootstrap.
- The same signed request passes through the bootstrap and native entry; both
  original root gates independently verify it. The existing proof-file route
  remains available.
- Before bootstrap the proposed worker refreshes root-owned protected CI
  evidence with the existing hash-pinned GitHub verifier. Required check runs
  are paginated and validated completely; existing evidence is preserved.
- Before staging and activation, the original JES-005 source check is rerun
  against the freshly advertised protected main under the original host
  transaction and freeze-verification boundary. The freeze boundary verifies
  bytes; it is not a separate operating-system lock.
- The native ledger checks source and CI within that boundary before writing
  its STARTED receipt or activating units. The native ledger remains the sole
  six-unit execution and rollback authority.

The proposed implementation is source only. Synthetic tests do not verify a
live Owner session, install the issuer or root worker, or authorize a release.
A failed bootstrap attempts only signed inert cleanup using the same
root-journaled proof; native receipts block that cleanup and remain subject to
the native rollback ledger. A signed approval is preserved on dispatch failure,
but automatic resumption or reissuance after a consumed or expired one-use
proof is not implemented.

## Remaining release gates

1. Independently review the complete diff and resolve interrupted transaction
   recovery and single-decision retry semantics without weakening proof expiry
   or replay controls.
2. Merge and verify protected CI for an exact current candidate. Recompute
   source scope, manifest and freeze digests from that candidate, and resolve
   the exact SHA authorization under the governing rules.
3. Prepare and review a byte-exact root bootstrap/dispatcher installation and
   rollback, with a root-owned policy and journals. Install it through an
   authorized root path. Install and enable the MCP issuer through its separately
   governed release path and verify publication in the authenticated session.
4. Verify current CI, preflight and live state, consume the Owner decision,
   run the bounded six-unit transaction, then independently verify ticket
   ownership, scheduling parity, rollback readiness and protected services.

No production release, root execution, live approval consumption or cutover is
claimed by this draft.
