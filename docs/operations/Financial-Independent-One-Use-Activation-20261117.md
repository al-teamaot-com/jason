# TODO-FIN-001 — Exact independent 05:00 organizer release

**Status:** Source-only preparation until the protected PR passes CI, then one
fresh Entra Owner exact-action proof and SHA-pinned isolated root action.
The root installer from PR #2546 is installed; no MCP overlay/replacement is needed.

## Reviewed release inputs

- Existing independent service candidate SHA
  `c205bb4ac163e7d433796f2f4839a90c7cc1f56b` (protected-main ancestor,
  all 31 check runs successful as verified through GitHub API).
- Existing OCI image **ID**
  `sha256:913322f47c96ae56f5ae9bb4c6e742ebe36691dc28ca56c202b124bf969ea195`.
- Already staged immutable component bundle:
  `/home/al/.local/share/jason/independent-component-financial-release-c205bb4ac163`.
  Its manifest canonical SHA256 is
  `56d7b12c6ee716e522aac66323fe59258256542ba6e6d104182807e3d7ec638e`,
  scope SHA256 is
  `ee36d69187b2b0aabb6ba19521c48adde71af95d5e8621855b590a5c03755f9c`.
- Exact configuration: independently verified accounting drive and intake root,
  AOT accounting tenant, enabled=true, local 05:00 America/New_York; single
  validated SharePoint-write boundary and dedicated OpenBao AppRole.
- Existing live read-only provider preflight for this exact image, app and drive
  returned `read_verified`, 21 intake children, zero mutations. This is NOT
  yet proof of a provider move/write or a real scheduled run.
- Previously installed independent controller SHA
  `675b99e73c33c228a8531c2797eb3db53c399ad8` with pinned
  `independent_component_release_root.py` and shared PMV3/PMv4 locks.

## Smallest safe activation

The source-only `tools/financial_component_oneuse_release_owner.py` uses
Jason's existing Entra Owner device-code authentication and root-pinned
Ed25519 signer, no Teams transport. It signs **one exact** first release
`release-c205bb4ac163e7d4` with rollback SHA `000…000`, candidate,
manifest, scope and production freeze. It stores no raw OAuth token.

The independently SHA-pinned `tools/financial_component_oneuse_release_root.py`
checks that signature against Jason's root-owned public key *before any root
state is created*. It independently checks the pinned source, already-built
OCI image, current GitHub main ancestry, actual complete protected CI checks,
dedicated OpenBao input file permissions, exact source/config/boundary bytes,
current closed native breaker, current live protected services, and unchanged
freeze. It creates one root-controlled receipt, copies only the reviewed
financial component's five immutable files into the root controller's release
directory, publishes a fresh root-owned CI attestation and exact Owner-signature
outbox receipt. Finally it invokes **only** the previously installed
`independent_component_release_root.py promote --candidate-sha …`, never
Docker CLI with raw imperative production authority. The native controller
rechecks locks/signature/freeze and allows only its one Compose project.

On any failure the controller attempts component-only rollback, preserves
the one-use incident evidence, leaves the freeze in place, and does not restart
runtime/MCP/PMv4/Teams/OpenBao or alter any accounting records. The root
release staging is not a global authority grant or waiver. An unrelated
protected drift (including failed service or excessive rollback containers)
must be resolved and freshly revalidated through existing native controls,
not suppressed.

## Acceptance — distinguish stages

1. **Source-only**: Protected PR CI, all focused regression tests, exact
   source-hash and issuer preflight passed. No production activation.
2. **Activated**: New single Compose service running from exact OCI ID,
   root receipt accepted, root active record, unchanged runtime/MCP/PMv4/Teams/
   OpenBao images/start times and production freeze. This is NOT full
   05:00 completion.
3. **Operationally complete**: On a genuine local 05:00 scheduled invocation,
   inspect real SharePoint discovery and audit, ensure valid bank/LOC/credit-card
   filings and readbacks, duplicate/ambiguous preservation, and run again to
   prove idempotency. No fake test documents in client SharePoint, duplicate
   deletions, or synthetic success receipts.

The financial scheduler cannot be considered done merely because the
controller is installed, or because an image is staged, or because the
schedule is configured. A future 05:00 live run is required for the original
issue #2294 acceptance criteria.
