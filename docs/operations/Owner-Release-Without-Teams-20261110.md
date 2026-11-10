# Authenticated Owner release without Teams: governed source contract

**Status:** Prepared source and tests, not a deployed production release.
**Owner objective:** Retire the mandatory Teams-signed approval dependency, not
merely reroute Teams cards. Preserve existing ticket processing, root authority,
rollback, CCC, production freeze, and independent Owner identity verification.

## Exact Owner identities, no Teams dependency

Either separately authenticated AOT Entra OAuth Owner principal may authorize
the exact reviewed release, without needing a Teams license:

- licensed regular account object ID `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`,
  Jason principal `person-entra-bee80bdcffb04c50b453c09d4d411f5f`;
- already-connected privileged Owner account object ID
  `c848022d-e13b-4457-84b0-e2f5c00dcaf6`,
  Jason principal `person-entra-c848022de13b445784b0e2f5c00dcaf6`.

Only **release approval**, after the existing MCP Entra OAuth middleware has
verified the live bearer token signature, issuer, audience, expiry, tenant
and active identity binding. Neither account acquires authority grants,
permission to change live providers or any other Owner tool from this policy.

## Single verified exact-action decision

1. The MCP issuer re-reads the production-eligible exact candidate, rollback
   SHA, manual scope review, immutable manifest and original active freeze.
2. It signs one affirmative decision with an Ed25519 service key provisioned
   separately, never a key supplied by a chat message or model-controlled
   argument. The proof includes the exact two identifiers, item identity,
   SHA-256 scope/manifest/freeze, release identifier and 15-minute expiry.
3. The native Release Manager independently verifies the decision against
   the separately root-pinned public key and current exact scope before
   recording the Owner decision.
4. A native serialized transaction may temporarily lift the original freeze
   once, while root independently verifies the signed proof, active Entra
   binding, source/manifest/rollback and immutable freeze backup.
5. Production CCC, unit health, root policy, protected LKG, drift and
   post-deployment readback remain required. Freeze is restored byte-for-byte
   even on failure. The same signed release decision cannot become standing
   release authority, be replayed across another source/scope or become a
   silent extra approval.

A legacy signed Teams decision remains backward compatible for historical
releases, but is **not** required for the new policy. The new source-only
policy schema `3.1` replaces the Teams-signed high-impact requirement with
`authenticated_entra_owner_decision_required: true`. The legacy Teams card
consumer does not fabricate a signed OAuth decision from a typed chat,
local JSON, shell command, email address or an expired receipt.

## Required operational work before enabling in production

The signing key/private mount and root-owned trust policy do not exist until
a separately authorized and audited provision. Both must be verified on the
host before issuing any Owner decision. Never print or place private key bytes
in Git, ChatGPT, a ticket or the release manifest.

The recovered V2 runtime/MCP/host and original production freeze are to
remain untouched until the exact main candidate SHA, scope SHA256, rollback
SHA, complete CI/CCC health, independently authenticated Owner approval,
root capability support and one-transaction recovery evidence are proven.
**This document is not permission to override the current open breaker or
failed CCC service.** The historical MCP base-image dependency and
protected-LKG mismatch must be resolved by separately governed repair.

No standing production promotion authority and no user/endpoint disruption
are granted by this source change.
