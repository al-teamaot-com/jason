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


## Stage B: governed held-only Teams approval timer declaration (#1993)

Stage A bootstrapped and independently verified the new root-owned migration
helper at the exact production/LKG SHA. Stage B now introduces ONLY the two
source-reviewed user unit declarations:
- required_user_units = jason-release-approval-only.timer
- allowed_user_units = jason-release-approval-only.service

Both native installers detect a nonempty four-category unit delta rather
than looking for the old #1974 system timer. They pass the exact candidate
and root-protected LKG revision into the already-installed, root-owned
reviewed migrator. It checks the **entire** unit delta against one of only
two fully specified plans, the owner exact-SHA grant, CCC review, root
policy bytes and rollback state. It stages the user timer as ALLOWED
*before* unit installation, then commits to REQUIRED after the candidate
install has completed. No new system units, provider mutations, generic
approval execution, self-issued authority or changes to the automatic
promotion incident-hold are authorized.

The new 5-minute user timer schedules only approval-offer publication and
independent consumption of signed owner decisions, never unattended
production promotion. A card sent is NOT proof of a human Teams click;
live recipient/card origin, signed callback, Approve, Deny, expiry and
replay remain separate measured acceptance criteria. **Stage B being
deployed does not mean the Universal Teams Approver is complete.**

## Root/host unit changes must never be normal risk

Stage B contains root-protected desired-state declarations and trusted
host migration steps. The original Release Manager risk classifier omitted
some of these files and initially classified the first preproduction
candidate as normal risk. That was detected before release approval or
promotion. The protected policy and runtime classifier now categorize
config/production-desired-state.json, root migrator, root host reconciler
installer and root release transition installer as production_control_core
for any change class. This prevents release-offer automation from treating
systemd and root-policy edits as routine normal releases. Protected CI and
fresh exact SHA Owner + CCC approval still apply independently.

## Protected migration ledger chaining - root-helper bootstrap (#1993)

The exact Stage B attempt e1f7016838ffec71e2667d9129012b0e0077d0bc
was legitimately approved and CCC-reviewed. Preproduction passed, but native
production host reconciliation refused to install new user units because
of a preexisting root migration receipt requiring independent review.
The independent root-approved policy can retain an earlier reviewed,
committed migration receipt (such as #1974). The installed helper was
hard-coded to reject all subsequent reviewed delta plans whenever that
root-only receipt existed. It is not permissible to delete an old
applied receipt, turn off the auto-promotion hold or install user units by
running privileged commands outside the release reconciler.

The new root helper, introduced in a distinct bootstrap release with no
new user-unit declarations, supports exactly one nested previously
committed reviewed migration. Only a root-owned receipt with phase=applied,
the exact current independent root-policy digest, valid original bytes,
reviewed fixed delta, immutable parent source ancestry and protected
last-known-good lineage can be nested. Any partial migration, malformed
receipt, wrong ancestry, already nested receipt, unexpected source delta
or root-policy mismatch remains a denial. The later separately reviewed
Stage B release preserves the complete root-only parent receipt, its digest,
source IDs and review metadata inside a new root-only child receipt before
the new root policy is staged. Only the exact independently approved new
unit plan can be staged and committed. On child rollback, the parent bytes
are independently verified before any protected-policy write and then
restored byte-for-byte, retaining the original parent audit chain. The
original systemd incident hold remains active throughout.

This design must first pass protected CI, new exact-source Owner/CCC approval,
native preproduction and postdeployment CCC at the no-units bootstrap.
Only then may a separate Stage B timer declaration be prepared, reviewed,
approved and deployed. A verified installed timer does not prove the
Universal Teams Approver is operational. The total rollout remains 0 of 3
representative live approval workflows certified until genuine Teams human
callback, origin card identity, Deny/expiry/replay, authorized bounded
execution and audit are all independently proven.

## Held-offer user-unit installation order (October 24 regression)

The Stage B host attempt reached its final desired-state guard before the
Release Manager's later controller installer copied the newly required user
timer. The guard correctly rejected the missing timer and rolled back. Passing
preproduction and source-level migration tests did not exercise this host order.

The existing Release Manager installer now exposes an approval-units-only mode.
The native host reconciliation invokes it as the existing user after the trusted
root migration helper has staged the exact pair, and before committing the timer
as required or running the final drift guard. This mode installs and activates
only that existing timer/service; it does not replace the running controller,
change its source link, or touch the normal promotion timer or incident hold.
The later full controller installation remains in its original transaction slot.

For rollback to an older immutable host script, the trusted root migration helper
stops and removes only the exact held-offer pair after validating and staging the
rollback receipt. The old script can then satisfy its unchanged desired state.
Unknown plans, wrong targets, unexpected file types, unsuccessful stop, and
policy/receipt mismatches remain failures. The original root policy and parent
receipt are restored only after the existing final absence checks succeed.

Regression tests exercise unit-only installation, half-pair refusal, no-unit
bootstrap, controller preservation, host stage ordering, exact-pair removal,
stop-failure retention, and wrong-target rejection. A passing source test is not
live Teams acceptance; the deployed timer and actual approval flow still require
independent verification.


## Expired owner-card renewal (P0 #2015)

A signed Teams Approve received after a card expires cannot grant release
authority. The old approval must remain terminal and immutable. Do not
change its SQLite status, extend its expiry, reuse its ID or replace the
original source-bound release offer. The five-minute worker does not
automatically issue a new approval for an expired card.

After this code is deployed through a separately reviewed high-impact
production release, the authenticated owner can request a NEW card only
from an interactive Jason shell running as operating-system user al:

    python3 /home/al/.local/lib/jason/release_manager_host_runner.py renew-expired-owner-card --release-id release-<16-hex-SHA-prefix> --candidate-sha <full-40-character-SHA>

Only card issuance is requested; this command does not grant owner/CCC
authority and never deploys. It requires actual terminal authentication,
the current protected-main SHA, unchanged release manifest and rollback
baseline, a closed breaker, clean drift, the existing manual promotion
hold, an active matching owner policy, and a prior expired undecided Teams
card. Pending, denied, approved, changed, or not-yet-expired cards block
renewal. At most three separate owner-initiated renewals are possible.

The host writes an exclusive, owner-bound private nonce record under
/var/lib/jason/openclaw/release-manager/mobile-release-renewals/.
On its regular scan, the existing Teams maintenance worker checks this
record and old expired request, then issues a distinct random approval
ID, a fresh expiry, and source-bound immutable renewal lineage.
An uncertain transport response cannot silently resend the same card.
Both the signed Teams callback and independent host CCC consumer verify
the original expired card and immutable renewal record. Deny never
authorizes action; a valid NEW signed Approve grants exactly one same-SHA
owner/CCC authorization under the original independent release gates.
Old cards remain permanently unusable.

Security/release restriction: mobile_release_approval.py, the independent
host consumer, and the Release Manager host runner are classified as
production_control_core. The active V1 owner-only Teams pilot cannot
authorize deploying changes to those files. Activation therefore needs
the separately reviewed owner high-impact release path. Neither a
generic chat instruction nor editing the risk/TTL policy is a substitute
for the exact-release authorization.

## Owner-only offer safety gate must not self-trigger production drift

An observed Oct 25 production failure loop made the held-only approval
service exit status 1 whenever the root release breaker or protected drift
readback was unsafe. Systemd then marked this *nonexecuting* issuer service
FAILED, which the independent drift watchdog treated as production drift
and reopened the breaker. That deadlocked automatic breaker recovery while
all legitimate runtime/MCP resources remained healthy. The native
approval-only function now fails CLOSED in the same case without marking
its own systemd unit failed: it logs `SAFETY_GATE_BLOCKED`, consumes NO
owner decision, publishes NO offer and exits successfully as a deliberate
nonaction. Truly malformed protected snapshots and baseline mismatches
remain errors. Never interpret service success as authorization or a
positive production release/CCC/Teams decision. Root incident hold and
revalidation remain independently enforced.

## Engineering intake duplicate prevention (October 25, 2026)

The five-minute engineering worker repeatedly failed the TODO release bridge
because the older canonical task issues were omitted by the intake's
200-open-issue GitHub discovery window. It recreated identical issue bodies
under new issue numbers, then the release bridge correctly refused the
conflicting TODO-to-issue binding. Production issue evidence: TODO-OPS-002
canonical #952 and generated #1491/#1899; TODO-KNOW-001 canonical #1131
and generated #1674/#1883/#2021. Closing generated duplicates alone does
not fix the underlying intake bug.

The intake now enumerates a bounded 5000-open-issue inventory, refuses
saturated discovery, retains the lowest-numbered canonical issue for
identical duplicated bodies, rejects conflicting scopes and checks the
provider issue inventory again before creation. Canonical task scope and
durable development/release authority remain unchanged. These controls
prevent low-risk duplicate bookkeeping from blocking higher-priority
Universal Teams Approver, staff purchasing and QBO work. Protected source
checks and exact release approval are still mandatory; this note is not
permission to bypass the root breaker or production incident hold.

## Oct 25 Owner correction: actively develop the Big Three concurrently

The prior single-feature engineering focus explicitly excluded PO/invoicing and
QuickBooks until Universal Teams Approver was fully accepted. That was superseded
by the Owner's October 22-25 direction to get the THREE priorities working
before optional hardening, with usable Teams approvals first, staff-wide
PO/invoice workflow second, and bank/credit-card QuickBooks reconciliation
third. The old developer focus suppressed valid owner-authored issues #759,
#1470 and #1545 even though source workers ran every five minutes.

The updated pinned engineering focus now admits only the existing,
individually owner-authorized bounded engineering scope for #1545 (Teams),
#759 (PO/invoicing) and #1470 (read-only reconciliation evidence), plus
necessary earlier Teams dependencies. The exact approved issue bodies carry
the worker's established owner-approved development marker, never an
approval to execute financial/provider writes. The existing development
worker subtracts active critical support tasks from the shared 3-slot cap
before claiming bounded new work; previously completed DEV-1440 does not
consume capacity and broad EPIC #1467 remains excluded. This is not a waiver
of human approvals for spending, disruptive operations, CCC, guarded releases,
tenant authorization, or independent production verification.

Do not report active work as completed functionality. New diagnosing or
implementing states show only productive admission; the three Big Three
workflows remain outstanding until real end-to-end acceptance passes.

## Owner-approved Big Three: hosted engineering credit-exhaustion recovery

The October 25 production engineering-admission release successfully claimed
Teams #1545, staff PO/invoicing #759 and QuickBooks bank reconciliation #1470.
All three native reasoning requests then received a provider HTTP 429
credit_balance_exhausted failure with required owner action to replenish the
hosted OpenAI API credit balance. The local Ollama models cannot be claimed to
be a verified replacement for the configured hosted engineering reasoner.
Ordinary ChatGPT subscription funding should not be presumed to replenish
separate API credits.

The existing native support worker already requires a provider-reported,
metered, operator-authorized OpenAI diagnostic before any retry on exhaustion,
but the owner-approved development worker had no equivalent retry lane. The
new one-time development recovery uses that exact existing diagnostic receipt
function, verified 0600 usage ledger, exact original owner-authored approved
scope, immutable request SHA, provider HTTP 429 and nonretryable failure
response. Only after a NEW provider-reported positive-token diagnostic receipt
is present may the worker queue ONE fresh same-kind request for the original
approved issue. It retains both request IDs and usage-receipt ID and never
changes the old failed response or grants provider writes, finance authority,
billing authorization or production promotion. Missing credits or invalid
proof keeps each item blocked, never falsely marked healthy.

Owner action is to restore credit in the existing hosted API provider billing
account and run its separately authorized credit-verify diagnostic. No paid
provider requests should be blindly retried while the provider reports
exhaustion. The developer lane will then independently readmit as capacity
allows. These development recovery checks are not end-to-end certification of
Teams, all-staff invoicing, or QuickBooks reconciliation.

### Legacy owner alias and Entra-authenticated binding compatibility — 2026-10-31

The reviewed release policy intentionally continues to name the canonical owner
as `person-al`, while authenticated Teams auto-enrollment persists Microsoft
bindings as `person-entra-<object-id>`. A literal binding lookup therefore cannot
be assumed to exist for the symbolic owner alias.

For the **release approval sender only**, direct `person-al` lookup remains first.
If absent, composition explicitly permits the exact fallback
`person-al -> al@teamaot.com`. The sender may use that fallback only when the
persisted active binding has the exact email, no client scope, and a Jason
identity equal to `person-entra-` plus the normalized Microsoft object-ID UUID.
Wrong email, inactive status, client scope, malformed object ID, or identity
mismatch fail closed before any Teams send. Other approval workflows receive no
fallback unless separately configured.

This compatibility rule does not grant approval, change policy membership, edit
the binding database, or substitute email possession for Microsoft identity.
The signed Teams callback and the existing exact-release consumer remain the
only path from a human decision to release/CCC evidence.


### Canonical proactive token mount alignment — PMV3 release preparation

Live PMV3 release preparation on 2026-10-31 exposed a second delivery-layer
configuration defect before any owner approval or production deployment. The
runtime container had two read-only proactive-token mounts:

- legacy runtime secret: `/run/jason-secrets/teams-proactive/token`;
- active Teams gateway credential:
  `/run/jason-secrets/teams-proactive-gateway/token`.

The active Teams gateway used the latter credential source while runtime sender
defaults still selected the legacy mount. Fingerprint comparison proved the
credentials differed; the canonical gateway therefore returned HTTP 401 before
provider delivery. No approval card was delivered and no owner authority was
created.

All runtime Teams senders now default to the already-mounted active gateway
credential at `/run/jason-secrets/teams-proactive-gateway/token`. The
`JASON_TEAMS_PROACTIVE_TOKEN_FILE` override remains supported. This is
credential-path alignment only: no secret value is committed, copied into
source, rotated, or granted additional scope.

Regression coverage requires the RuntimeSettings default, governed Teams send,
and autonomous completion sender to share the same active gateway token path and
reject reintroduction of the legacy default.


#### Concurrent composition workstreams

The token-path alignment touches only the `RuntimeSettings` Teams proactive
credential default. Current open branches #2177, #2178, #2125, #2128 and #2126
also modify `composition.py` for KFS reporting, VulScan V2, routine governed
read/write registration and Windows Time JSON shadow respectively. Those
settings, registrations, provider/authority gates and default-off controls are
independent and must be preserved when later integrated. The PMV3 token-path
correction does not absorb or supersede them.
