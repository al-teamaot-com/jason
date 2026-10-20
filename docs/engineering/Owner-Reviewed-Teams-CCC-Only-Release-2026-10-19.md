# Owner-reviewed Teams CCC-only release recovery

## Live failure and owner travel constraint

On 2026-10-19 Jason had an exact production_control_core release
c62da59ef015057e1b42282a8d6fb0e3e42d2e47 with durable owner approval,
isolated preproduction acceptance and rollback proof. The independent CCC
checker correctly reported its material owner review was missing.

Yet the official Teams offer publisher suppressed every card as soon as
the persisted owner approval became true. The old V1 channel also permits
only normal-risk releases and currently runs in owner_only_pilot mode.
Repeated requests for the traveling AOT Owner to log into Ubuntu and run
a Python script violate the accepted mobile Teams approval UX requirements.

## Repair: one signed owner card for one missing review

Under a separately reviewed V2 owner_reviewed policy and a matching
RUNNING container mode, the official Release Manager may publish a
review_only offer for a protected, production-eligible release already
approved for the exact SHA, but only when its exact durable CCC owner
material review is missing. Offer metadata retains protected main,
original rollback SHA, and immutable release manifest fingerprints.

The existing release mobile issuer (not a second bot or approval engine)
independently revalidates the exact release and creates one relapproval-
card with a private 192-bit, signed card-instance challenge. The card
says CCC Material Review and makes clear that Approve attests material
changes ONLY, not another release approval, deployment, standing risk
authority or CCC PASS. The owner must be the existing bound person-al.
The trusted Teams signed callback, durable decision and original evidence
are independently verified before any material review is created. Deny
is terminal; it does not revoke an earlier exact owner release grant.

The host consumer requires matching V2 policy, trusted signed gateway
machine, active owner Entra/Jason binding, nonce, request and previous
exact owner grant. It rejects changed SHA, policy, manifest, card challenge,
reviewer, old approval, denied/replayed response and conflicting recorded
CCC review. A successful review-only click writes ONLY exact source-bound
CCC material review and a single-use processed receipt; it NEVER calls
approve_release again, promotes a release, or manufactures CCC PASS.
Historical V1, V2 combined grant and crash recovery semantics remain.

## Explicit activation safety and pending bootstrap

Source merger is not activation. Live production still runs
owner_only_pilot with private V1 normal-only policy. V2 and the matching
runtime mode require separately reviewed governed activation; never modify
a live approval policy, simulate an owner click or bypass CCC.

The first production-control upgrade to V2 has a genuine bootstrap
dependency: exact source owner consent, separately authorized CCC
material review, independent CCC, root-verified breaker, preproduction,
rollback and postdeployment checks. Merging a new source SHA also
supersedes the already-approved candidate; keep this PR independent
until that release has closed safely. The signed mobile-review path
does not itself fix a failed service or a root breaker.

The SQLite owner-read contention and CCC scheduled deferral repairs
remain in separate, protected-checks-passing PR #1613. Rebase this PR
once those prerequisites have been safely integrated.

## Verified and required acceptance

Adversarial tests cover V2 signed CCC-only click, exact prior owner grant,
unchanged source/release authority, no duplicate release approval,
idempotence, Deny, changed source, changed manifest, missing grant,
wrong challenge, replay, conflicting review, V1 non-escalation, V2 mode
mismatch, altered risk and absence of duplicate reviewed cards.

Read-only verification against the ACTUAL production c62da59e record
with a private TEMPORARY V2 test policy proved the candidate code
would issue a CCC-only challenge-bound request tied to the exact
approved SHA and immutable manifest. No live authority, Teams card,
production service or CCC record changed.

Live acceptance still requires an actual owner-visible Teams card,
signed real click, verified identity and single-use receipt, CCC
material review, independent CCC PASS, root-closed breaker, governed
release closeout and subsequent SUPPORT-OPS-054 engineering progress.
No source test may be reported as live activation.

Related: #1440 #1545 #1553 #1517 #1526 #1609 #1611 #1612 #1613.
