# Mobile Teams release + CCC owner approval (P0 #1440)

## Objective and current scope

AOT's Owner must be able to approve a **production-eligible, normal-risk,
exact-SHA release from Teams on a phone**, without opening SSH or entering
`record_ccc_material_review.py` and `release_manager_host_runner.py approve`
separately.

This is a narrowly isolated adapter built on Jason's **existing provider-neutral
`ApprovalRequestService` and signed Teams gateway**. It does not replace
Universal Approver #1440, broaden the Datto/procurement owner roles, enable
Universal mode, bypass CCC or make the Teams message itself an execution grant.

**Default is OFF. No new standing provider/device authority is created.**

## Who can activate the first bounded pilot

Activation requires an additional *separately approved* production release
and a local 0600 policy installed by the verified owner:

`/var/lib/jason/authority/mobile-release-approval-policy.json`

Exact initial schema:

```json
{
  "schema_version": "1.0",
  "organization_id": "aot",
  "policy_mode": "owner_only_pilot",
  "owner_identity_ids": ["person-al"],
  "allowed_risk_profiles": ["normal"],
  "ttl_seconds": 900,
  "capability": "release.production.approve"
}
```

Neither changing this file nor setting the mode variable is a substitute for
reviewing the production deployment of the activation. The parser refuses
missing, malformed, public-readable, symlinked, wrong-owner or overbroad
policy files. In this initial pilot, financial, destructive, core-control
and schema-contract risk categories are **never** mobile-approvable.

Runtime mode, initially disabled:

`JASON_RELEASE_MOBILE_APPROVAL_MODE=off`

Only after separate exact-SHA activation approval may it become:

`JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_only_pilot`

The HTTP process retains the callback handler but the separate maintenance
process is the only card issuer, using
`JASON_RELEASE_MOBILE_APPROVAL_WORKER_ENABLED` and the existing 5-minute
development/production management cadence.

## One immutable review, one click

1. The Release Manager assembles its immutable manifest from the protected
   candidate, classifies risk, builds artifact hashes, validates isolated
   preproduction, rollback readiness and the protected release record.
   The host Release Manager must additionally confirm this **exact SHA is
   currently protected GitHub main** and the rollback equals the live production
   baseline. Only then does it publish a 15-minute freshness-bounded offer
   under `release-manager/mobile-release-offers/`. Historic superseded offers
   are removed, and the Teams issuer independently cross-checks offer SHA,
   rollback and manifest. A candidate is offered only in `production_eligible`
   with no previous owner approval, normal risk and safe preproduction evidence.
2. Jason creates a durable `relapproval-...` request with 15-minute TTL
   (configurable within 5–30 minutes) for **person-al only**. The card
   shows the bounded human-readable GitHub change purpose, release ID,
   full 40-character source revision, risk,
   affected systems, representative changed files, exact rollback SHA,
   preproduction proof and immutable manifest digest. To keep the two
   Approve/Deny actions practical on narrow mobile screens, administrative
   duplicates (capability/mode/approval ID) and the unsupported Request Changes
   button are not shown; the original signed request still retains and binds
   the policy hash, owner identity and full detailed evidence.
   Additional source changes force a new review; cards never silently carry
   forward from an old SHA. One request is issued per eligible release, with
   no repeated unsolicited cards after expiry.
   Delivery receipts (real provider IDs or a bounded `accepted:` transport
   receipt) are appended to the private ledger **after** card issuance. They
   are operational transport evidence, not owner authorization or changes to
   the immutable release/policy fingerprint. The signed callback validates
   exactly this one optional bounded field independently; any additional
   mutable approval data, unexpected request scope or a changed manifest
   fails closed. Regression tests exercise the real post-send metadata path
   through signed Teams intake and independent host CCC review, not only a
   pre-send synthetic request.
3. The existing Teams Bot Framework ingress verifies the signed Ed25519 gateway
   envelope, bound Microsoft tenant/object and unique callback. Jason checks
   the active AOT identity and separate owner role; **the requester is a service
   identity, not the owner**. The approval ledger atomically consumes exactly
   one Approve/Deny. An approved callback saves original signed gateway
   evidence in a 0600 durable store, but **does not deploy or manufacture CCC
   PASS**. Deny is terminal, creating no release or CCC authorization.
4. The normal host Release Manager alone independently re-verifies the saved
   gateway signature and registered machine identity, current owner binding,
   accepted one-use SQLite receipt, decision-time expiry, exact owner policy
   digest, untouched original manifest, rollback and artifact digests. Only
   after this independent replay-safe verification does it materialize:
   - the exact owner CCC *material review* (not a CCC check outcome), and
   - the exact release's owner approval via the existing
     `approve_release()` function, preserving main/immutable artifact checks.
   Crash recovery can only rebuild a lost process marker if the **same** signed
   decision already matches both persisted artifacts. Any mismatch fails closed.
5. The existing Release Manager still performs locked source/main verification,
   pre-mutation CCC (the only scoped exception is expected pending runtime
   alignment), drift and root circuit-breaker checks, immutable image and
   rollback checks, root host reconciliation, **post-deploy CCC PASS** and
   closeout evidence. Teams acceptance is not execution authorization.
6. The Owner gets the existing production-status and failure notifications.
   Status must never claim deployed before the Release Manager records closed.

The request and signed receipt database are under:
`/var/lib/jason/openclaw/mobile-release-approvals.sqlite3`

Host-safe replay-protected completion markers are under:
`/var/lib/jason/openclaw/release-manager/mobile-release-decisions-processed/`

CCC owner-review artifacts remain at the existing canonical review path and
a per-SHA named review. Existing manual `approve` and
`record_ccc_material_review.py` commands remain an authenticated **break-glass
fallback**, not a routine requirement.

## Initial limits and production dependencies

- The pilot applies to exact normal-risk release owner approval **only**.
  It does not cover Datto component actions, finance approval, tenant
  permission changes, reboot, Client approval or staff-wide roles.
- The independent CCC checker must already be acceptable for the reviewed
  candidate. If source changes make the checker itself stale, this pilot
  **does not automatically upgrade the root-owned CCC checker**. That requires
  a separately reviewed root-control workflow, otherwise the existing CCC
  gate stays closed. Do not advertise broad terminal-free coverage until that
  dependency is satisfied.
- A lost Teams connection, invalid/revoked key, wrong tenant/owner, stale
  code, changed manifest, expired request, replay or missing host proof
  **fails closed**. Jason must not mark approval completed based solely on a
  Bot Framework delivery receipt.
- Never enable a broad existing owner role to make a test pass; this policy is
  independent of Datto/procurement roles.
- The independent pilot must be activated through the usual PR, protected
  checks, owner-approved exact release, CCC material review, host reconciliation
  and rollback. The source implementation alone is not production activation.

## Required go-live acceptance

1. Sandbox complete signature + normal-risk release -> Teams approval -> exactly
   one accepted ledger receipt -> host-verification -> matching CCC material
   review and release owner approval; no manual CLI for this **test flow**.
2. Deny, expired request, wrong principal, wrong organization/tenant, duplicate
   decision, tampered/unsigned gateway evidence, changed policy digest, changed
   diff/manifest, superseded commit and failed preproduction all deny without
   authorization or provider writes.
3. Restart and crash-after-record handling cannot mint a second decision or
   authorize a different SHA. No transient network/authentication failure
   becomes a positive approval.
4. Independently confirm CCC pre- and post-mutation checks, circuit breaker,
   rollback and final closeout on a controlled **production** candidate.
5. Test with the Owner's actual mobile Teams client (Approve and Deny), not just
   a generated card or Graph delivery receipt.
6. Separately decide the CCC-checker-update scenario before promising all
   releases are terminal-free during the owner's travel.

Tracked parent: https://github.com/al-teamaot-com/jason/issues/1440
