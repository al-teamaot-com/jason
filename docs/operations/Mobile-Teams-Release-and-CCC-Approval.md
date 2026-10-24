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



## Held production promotion - independent owner-card issuance (P0 #1993)

The automatic promotion incident hold is intentionally preserved. Its
20-release-stability-hold.conf systemd condition continues to skip
jason-release-manager.service, which may deploy production. A separate
user timer jason-release-approval-only.timer and service run **only while
that hold file exists**, calling the native Release Manager
approval-only-held command. The command cannot invoke deployment, root
transitions or customer/provider actions.

The bounded worker reads fresh root-protected breaker and drift snapshots,
verifies runtime/MCP/host and protected last-known-good alignment, checks
live owner_only_pilot or separately reviewed v2 mode, versioned 0600
policy, signed owner containment and exact protected main. The existing
independent signed owner decision consumer can record the exact owner
approval and CCC material review only after verifying durable decision
evidence. A current-main, preproduction-eligible, appropriately risk-scoped
release with unchanged production rollback gets one immutable offer for
the existing owner Teams sender. Existing offers are never refreshed or
rewritten after an unknown/partial send or expired card. The issuer's
existing durable request ledger prevents repeat card sends.

The offer-only timer is installed by the normal native immutable-release
installer, activated alongside the preexisting 5-minute production
timer, and registered as a required user timer in desired state. It never
removes or overrides the incident hold or the root-protected deployment
breaker. Approve is not a deploy instruction while the hold is active.
A separate supervised, audited recovery is required to reactivate
unattended production promotion; manual exact-SHA promotion remains
governed by existing owner/CCC root checks. This is not a broad Universal
Teams Approver activation. Existing #1553 original-card human-origin
provenance remains a separate acceptance gate.


## Root-policy migration proof for held-only timer (#1993 follow-up)

An exact Owner-approved/CCC-reviewed production-control release containing
the held-only owner approval timer may require updating the root-owned
production desired-state policy during the immutable host reconciliation.
The original protected migration previously only allowed the historical
#1974 full-integrity units and rejected this release despite full
preproduction PASS. The native root migrator now recognizes exactly two
**separate** named delta plans: the original historical #1974 set or
the #1993 pair:
- required_user_units: jason-release-approval-only.timer
- allowed_user_units: jason-release-approval-only.service
- no added system units and no other policy change

It selects exactly one plan from the difference between the prior
immutable LKG Git source policy and new immutable candidate source policy.
The plans cannot be combined or partially mixed. Before new user timer
activation, the root policy stages that timer as merely ALLOWED; after
the host has fully installed and checked the unit, the root migrator
promotes it to REQUIRED. The original root policy bytes and exact
reviewed plan are recorded in an owner/CCC/source-bound 0600 root ledger
for staged, applied and rollback phases. Rollback demotes the timer to
ALLOWED first, then rejects final restoration if newly installed
candidate-only user timer/service definitions remain, and finally
restores the exact original protected root-policy bytes. Candidate
source still cannot edit arbitrary root units, release approvals,
production breaker, auto-promotion incident hold or unrelated provider
permissions. An old approved SHA does not authorize a new changed SHA.


## Mandatory root-helper bootstrap phase (#1993)

The first guarded deploy of the held-only Teams timer correctly failed at the
*installed root worker's preflight*: that worker executes the **previous**
root-owned migration helper to evaluate a newly introduced timer before the
candidate's helper can be installed. Simply shipping an updated migrator
alongside newly required user units does not repair that ordering defect.
Never manually replace the root-only file or bypass its root policy gate.

The rollout must therefore be split into **two distinct immutable releases**:

- **Stage A — trusted-helper bootstrap.** Ship the already reviewed bounded
  root migration helper plus the ordinary approval-only application code,
  but keep config/production-desired-state.json identical to the protected
  known-good baseline. The Release Manager installer reads that immutable
  policy and neither copies nor activates the new user timer/service while
  they are undeclared. The existing root preflight has no new unit delta to
  authorize and can install the newer reviewed root migration helper through
  its normal native host reconciliation.
- **Stage B — approval-only timer declaration.** Only after Stage A is fully
  production-verified and its reviewed migrator is the trusted installed root
  helper may a second exact-SHA PR add the **two** held-only approval systemd
  declarations to desired state. The same installer will then activate the
  declared timer. The *installed* root helper recognizes that exact reviewed
  plan; its root-owned 0600 receipt and staging/rollback gates remain in force.

Each stage requires independent protected GitHub/CCC and exact SHA Owner
approval. The auto-promotion incident hold is never removed by either stage.
If Stage A cannot complete its host verification, do not attempt Stage B.
