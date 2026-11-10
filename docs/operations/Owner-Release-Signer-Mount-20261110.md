# Native MCP private signer mount for non-Teams Owner release decisions

**Status:** Source-only implementation and tests. No private key in Git; no
production key provisioned, process restarted, policy unfreeze or root-control
mutation by this change.

The signed Owner release decision code already exists in protected source.
A separate, verified Ed25519 signing key must be accessible to the
unprivileged MCP service, and the root public policy must independently pin
the matching public key. A missing signing key must not degrade silently to
Teams, unsigned ChatGPT text, a Boolean `approved` flag or a fake signed
receipt.

## Source-bound contract

- **Private host path:** `/var/lib/jason/runtime-secrets/owner-release/private_key`
  (32 bytes, UID/GID 1000, file mode `0400`, never a symlink).
- **MCP path:** `/run/jason-secrets/owner-release/private_key`
  (read-only bind; MCP runs as UID 1000).
- **MCP environment:** `JASON_OWNER_RELEASE_ED25519_KEY_PATH` points to
  the container path, not a secret string.
- **Root-pinned public policy:**
  `/etc/jason/owner-release/verified-owner-public-key.json`
  (root-owned, non-symlink; parent and file not writable by group/others).
- **Preflight:** exact owner/mode/32-byte test plus independent Ed25519
  private/public matching; no key bytes printed. Missing, mismatched or
  substituted signer stops release before any Docker replacement.
- **Postflight:** the running unprivileged MCP worker must read the private
  signer securely from the exact mounted path, with no change to provider,
  tenant or technician execution permissions.
- **Rollback:** native MCP rollback explicitly clears the new signing-path
  environment entry and omits this single read-only signer mount. All other
  existing Docker mounts and environment controls remain unchanged; the
  omission is forbidden for runtime containers, forward deployment, or
  without exact rollback image selection.

This is not a new Owner approval or a waiver of the production freeze,
root circuit breaker, active drift, complete candidate scope/manifest, or
independent runtime/health acceptance. The one-time local administrator
provisioning of private/public keys is a separately authorized,
audit-recorded bootstrap and does not activate the release controller.

## Work remaining

Complete the audited private/public key provisioning and immutable
readback; restore the exact protected previous V2 LKG through authorized
root recovery; retire the CCC scheduled units under the approved
exact-byte-verified host action; build/test the final protected-main
candidate and rollback; obtain one authenticated exact Owner decision;
deploy via the native serialized release manager; verify tickets/health.
