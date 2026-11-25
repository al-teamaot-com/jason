# PMv3.2 — One Teams approval for one ordinary frozen release

**Engineering only.** This implementation is inert until installed by an independently authorized, exact-SHA Production Manager release. It does not unfreeze a running system, close an open circuit breaker, reactivate autonomous engineering, publish a Teams card, or consume any approval.

## Contract

The existing reviewed V2/V3 mobile release flow has one signed Owner Teams card per exact eligible release. When the ordinary production circuit is CLOSED, the installed controller verifies the native whole-main scope review and current 0600 production-freeze marker, then publishes a nonexecuting offer including the exact release SHA, manifest digest, verified rollback SHA, reviewed scope SHA256, and current freeze-marker SHA256.

The Teams card visibly names the one-transaction temporary unfreeze, required rollback, and automatic refreeze. The existing signed card-instance challenge binds the Owner click to that immutable request and presentation. No second unfreeze click, chat "proceed", shell instruction, or standing permission is obtained or invented.

The independent signed Teams evidence consumer checks the original gateway signature, Entra/Jason Owner binding, exact reviewed request and challenge, protected main and established controls. The existing release approver writes the owner/CCC authority, then a distinct host gate records a separate signed one-transaction unfreeze receipt. That gate independently rechecks current source, exact scope, live LKG alignment, CLOSED breaker, protected offer, freeze bytes, SHA, signed decision ID and TTL. Crash recovery can complete the second receipt from the same signed decision; it cannot mint a new decision.

Only the existing serialized Production Manager transaction may consume that receipt. It validates the 0600 file and hash-bound record pointer again under its exclusive lock, temporarily removes the exact freeze and restores original bytes/mode/hash on success, error, rollback and interrupted transaction recovery. It consumes the one-time source receipt and refuses replay.

## Boundaries

- No automatic or permanent unfreeze. Engineering Owner pause, promotion incident hold, host/root drift, immutable candidate, protected-main, CCC, rollback and provider checks remain mandatory.
- An OPEN production circuit breaker blocks ordinary one-click card publication and promotion. The reviewed provider-recovery exception is unchanged; it is not a shortcut for an ordinary release.
- An older signed approval without the exact freeze intent does not inherit unfreeze authority. Different freeze fingerprints or scope require a new exact card. Expired, forged, replayed, misbound and owner-revoked approvals fail before freeze mutation.
- Existing V1, CCC-only, replacement-unfreeze and stand-alone explicit-unfreeze workflows are preserved.
- Governed retry releases with an exact -retry-N suffix use the same signed freeze permission; malformed retry IDs fail closed.
- This source cannot make an older installed Production Manager generate these offers. Its own first installation requires a currently supported, separately authorized bootstrap path. Never run uninstalled source against protected production or forge approvals.

## Acceptance evidence

Tests cover signed callback and independent host verification, one owner click producing two distinct receipts, changed marker/scope/rollback/owner, duplicate invocation, missing second receipt, expired consent, tampered on-disk evidence, single-use semantics, normal byte-identical restore and crash recovery. Full release-manager/mobile/card/serialization regressions, protected CI and isolated preproduction must pass. No production completion claim is valid before exact approved deployment and independent live readback.

Tracking: #2316, #2359, #2300.
