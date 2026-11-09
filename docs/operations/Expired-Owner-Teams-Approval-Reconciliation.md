# Expired Owner Teams Approval Reconciliation

**Classification:** HIGH RISK — release authentication/approval lifecycle and shared
approval persistence. **Issue:** #2365. **Scope:** an expired pending
release.production.approve request that was sent through the governed Teams
gateway but was not acknowledged by the Owner.

## Observed failure (November 8, 2026)

- Exact production-eligible release release-c33593334e0caa20, candidate
  c33593334e0caa2090b94f27f498e71f48ffa719, rollback
  75a4c5e3e6a27a563a59653e514db38ba69a11fa.
- Teams request relapproval-54f75af250466153901f1a6cb309cb2d had an
  expiration of 2026-11-07T23:53:26.197084Z, yet remained persisted as
  pending after expiration, with zero signed decision receipts.
- A non-synthetic provider Teams message ID was recorded, but this did not prove
  the Owner actually saw the card. The gateway routed to the authoritative
  al@teamaot.com Teams binding, which is distinct from the ChatGPT
  al_admin@teamaot.com Entra caller.
- Existing renew-expired-owner-card rightly rejected the stale pending
  state. No direct SQLite update, forged callback, clock change, provider write,
  production unfreeze or deployment was authorized by this diagnosis.

## Reusable correction

1. The generic ApprovalRequestService.expire_if_due uses the repository's
   existing atomic PENDING -> EXPIRED compare-and-set. Expiration must be
   at or after the trusted expiry. It records no signed decision or new
   approval; missing/stale/changed requests and inconsistent signed evidence
   fail closed. Already-approved, denied, or otherwise terminal requests cannot
   be changed by expiration.
2. The existing mobile release maintenance worker reconciles up to 20
   overdue release-approval records per tick after validating containment
   and the exact reviewed Owner policy. It only selects the established
   release.production.approve capability, AOT organization, service issuer,
   pending status and actual elapsed TTL. Malformed release IDs are ignored.
3. A pre-existing renewal marker alongside a still-pending predecessor is an
   inconsistent state; the worker does not transition it and must require
   review. This prevents silently turning improperly pre-staged markers into
   actionable renewal cards.
4. Reconciliation never automatically resends a Teams card, creates a
   renewal intent, grants Owner authority, or changes release eligibility. The
   existing local human Owner renewal path, signed Teams callback, exact SHA,
   CCC, production freeze and Release Manager controls remain authoritative.

## Safe acceptance and release sequence

- Run targeted approval atomicity, mobile-release maintenance, denial and
  duplicate-send tests plus representative downstream Teams/PMv3 regressions.
- Exercise the actual stuck request against a temporary SQLite backup made
  through read-only production access; prove only the temporary copy expires,
  no receipt is fabricated, and the live source stays pending before any
  authorized deployment.
- Perform independent security review and PMv3 protected-branch CI, respecting
  the existing release lock and engineering Owner pause.
- Form a new immutable candidate SHA only through an authorized, governed
  integration path; an existing expired signed card for the prior SHA cannot
  authorize this or a later release.
- After a separately authenticated new Owner Teams decision and exact-SHA
  production release, verify startup health, release controls, the expired
  request's terminal readback, and zero new signed decisions for that request.
  Restore the original production freeze and retain automatic-promotion hold.
- A fresh card must be issued and its intended recipient visibly verified
  before claiming Owner approval or completion. If Teams does not display the
  new card, investigate actual recipient account/client and gateway receipts;
  provider transport acceptance alone is insufficient.

This change is a lifecycle repair, not approval to deploy, reroute to a different
Microsoft identity, alter production records, or send an XYZ client notification.
