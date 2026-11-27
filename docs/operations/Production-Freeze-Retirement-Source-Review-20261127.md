# Permanent production freeze retirement — source review

Status: isolated source preparation; not installed, authorized for production,
or operationally accepted.

Owner-directed objective: retire the temporary October 27 blanket production
deployment freeze. Keep the separate automatic-promotion incident hold,
exact authenticated release decisions, protected source, current scope,
preproduction, rollback identity, transaction locking, breaker, drift,
provider authorization and post-deployment verification. Do not reuse
historic approvals. No change to provider rights or ticket processing.

## Verified dependency

The normal native promoter has an unfrozen branch, but the current MCP
issuer, unprivileged proof consumer, and privileged host verifier bind their
signed decisions to the active freeze (or its legacy transaction backup).
Deleting the marker alone would leave current signed approvals unusable.
Existing independently scoped native release routes also depend on the old
binding. The freeze is not an independent Owner approval requirement in
the November 10 normal-release governance contract.

## Prepared shared source change

Extend the existing exact Owner proof with a distinct version-2 normal
release binding to the root-attested policy recording permanent retirement.
The original implementation and historical SHA-256 pins are byte-identical.
A separate, independently pinned successor is used by the updated ordinary
issuer and verifier. Legacy bootstrap and recovery still use the original.
The root installer stages only the exact successor and a dedicated empty
public policy directory; the MCP deployment projects only that directory
read-only, never the private Owner trust/control directory. These are
preparatory changes and cannot themselves retire the freeze.
The normal issuer and both verification paths require the independently
installed policy, an absent active marker, current exact candidate, rollback,
scope, manifest, authenticated identity, signature and expiry. Legacy
approval flags and old freeze-bound signatures cannot authorize a new
normal-mode transaction. An inconsistent old recovery transaction is
denied, not allowed to reconstruct a retired marker.

The retirement record is evidence of a one-time policy migration, not a
standing approval, new deployment hold, or per-release human decision. No
source code in this change creates it or removes the freeze. Missing
policy evidence cannot authorize the new normal deployment path.

Local regression: 541 tests and five subtests passed, including historical
bootstrap pin integrity, original and successor proof vectors, native rollback
admission, isolated normal-mode issuer and root verification, wrong-mode
denial, legacy recovery conflict, and source/install/mount consistency.

## Unresolved before production eligibility

1. Independent high-risk security review of the entire exact change.
2. Integrate the existing mobile/Teams release-approval channel with the
   normal release policy without adding a second Owner decision. The
   current normal-mode candidate admits only the signed MCP route.
3. The actual live root reconciler is wrapped by the independently adopted
   audit-journal controller. Its legacy worker is immutably pinned, and its
   compatible_host_releases list is empty. Do not overwrite the pinned
   worker, change the journal policy, or bypass the wrapper. The exact
   installed successor needs a separately reviewed native migration that
   preserves the audit-journal guarantees and the original rollback path.
   Reconcile active independent-component, catalog and scoped-backport
   release/recovery routes against the shared policy; retire only obsolete
   one-use routes and preserve all historical signed evidence. Reconcile
   draft PR #2766 against this target rather than deploying a new
   freeze-dependent controller.
4. Prepare one exact migration using the existing trusted root policy
   installer: atomic updates of the native proof verifier, controller,
   root reconciliation/health readers and MCP's required read-only policy
   projection. Bind reviewed source, rollback artifacts, actual live
   baseline and protected peer health. The source patch cannot itself
   supply root installation or Owner authority.
5. Perform isolated end-to-end installation, normal approval and rollback
   rehearsal, including stale approval, replay, missing policy, concurrent
   transaction and recovery tests. Verify current root policy trust pins.
6. Obtain the authenticated exact retirement migration decision through a
   supported Owner channel. A global authority-administration check rejected
   the current session; release-specific Owner verification is distinct and
   must not be inferred from that result. Do not use administrative shell
   privileges to bypass the authenticated decision.
7. Under existing locks, preserve and archive the historical marker and
   backup, retire the global freeze only, retain the separate incident hold,
   and prove release approval/rollback and scheduled recovery/health without
   re-creating the retired marker. Verify actual Ticket Core continuity.

No production deployment, freeze retirement, or exact migration approval
has been completed. Existing freeze and incident hold remain intact.

## Concurrent source integration

Integration coordination: #2766. Preserve both independent security-regression workflow steps. The isolated MCP image built from the exact live LKG plus the two issuer/proof source files passed unprivileged normal-proof issuance and cross-mode denial with a synthetic root-owned public policy in a disposable network-disabled container. No live signer, provider credentials, or production state were mounted. This evidence does not authorize a native install.

## Existing native-manager successor preparation

The installed manager is the accepted 81ad19542cc8a720debb09d2ea7c511db6b9fc20
successor. Its original receipt and saved worker bytes are independently
attested. Use the existing authenticated engineering-manager transaction's
new normal-manager successor mode to stage the fixed normal Owner verifier,
component readback, and versioned host guard in their exact native paths.
The existing manager receipt then binds the new runner, watchdog and
development worker to immutable saved copies. Retain the original
independent-component guard and all historical receipts. The complete
protected-main candidate remains subject to the existing native CI check;
the manager installation source inventory records unrelated source changes
without installing their application artifacts. The concurrent composition
source is reviewed but not deployed.

This bounded prerequisite uses the existing before/after image journal,
production locks, Entra Owner authentication, rollback and two scheduled
acceptance cycles. It requires the freeze and incident hold to be
unchanged. It neither restarts application containers nor grants
production/provider authority. Its own preflight, exact native installation
and scheduled acceptance remain necessary; it is not a retirement receipt.

## Configurable production restriction

The retired-mode policy projection includes a distinct root-managed operating
configuration, deployment.json, with exactly schema_version "1.0" and the
boolean production_freeze. Normal admission, signed decision issuance and
native promotion reread this setting. Missing or malformed settings deny
promotion. A true setting blocks new promotions without replacing any
container or rebuilding code. Recovery and independent readback remain
available while frozen. The mutable flag is deliberately not part of the
immutable retirement receipt digest or effective component identity.
The existing protected transaction lock must serialize configuration writes
with deployment. A native Owner-authenticated migration receipt uses its
own owner-native reference namespace, not a fabricated MCP approval ID.

## Combined migration draft and validation checkpoint

The draft combines the authenticated manager-preparation scope and final
retirement scope into one exact decision. The isolated transaction tests
cover denial of missing or mismatched approval, incomplete preparation,
preservation of non-target peers, successful simulated activation, four
injected failure/rollback cases, and recovery of an interruption before
cutover. Full affected local regression: 810 tests and five subtests passed.
The migration-specific tests are included in security-regressions CI.

These are source and simulated-host results, not production acceptance.
The final phase still requires independent validation of effective native
recovery, exact installed path/custody and systemd behavior, live component
readback, and the approved rollback path. Do not merge or deploy the draft
on the strength of fixture results. No production control or service was
changed, and no new release authorization has been recorded.

## Serialized interruption recovery and native file rehearsal

Activation and explicit interruption recovery now take a nonblocking lease
on the existing root-owned immutable intent record while holding the shared
production locks. The lease remains held across quiescence and native health
revalidation, including their lock-release windows. No new lock file, root
service, authorization channel, or standing privilege is introduced.
Normal activation must pass the existing current protected-main source/CI
review; historical source review is reserved for explicit recovery and
historical acceptance. Previously committed and recovered commit receipts
are labeled historical and require independent live verification.

The one-time native migration uses the established native manager installer
recovery pattern: failed acceptance rolls back automatically; a killed or
interrupted installer can recover the exact approved journal via its bounded
recovery entrypoint, without another business authorization. This is not a
claim that the initial installer is an independently scheduled recovery
daemon. Ordinary coordinated component transactions use their existing
native scheduled recovery path after installation.

Validation: 812 affected regression tests plus five subtests passed;
five isolated-root cases skipped in the ordinary run passed in the
disposable image. All 30 migration tests passed inside the network-disabled,
read-only container using real root-owned before/after files, atomic rename,
fsync and journal custody. Docker and systemd ports were simulated in those
transaction tests; the actual MCP image, current live component identities,
read-only mount contract, rollback capacity, and 33-target live diagnostic
scope were independently checked. Production has not changed. Native
protected-main preflight, authenticated exact-scope authorization and real
production acceptance remain mandatory.

## Historical transition source custody correction

The first protected-main audit migration check identified a real source
compatibility issue: the legacy fixture and legacy host installation path
consume tools/release_control_transition_worker.py, whose original
02ce315d9e96e1e655c3465f5fc2761661f78e5ced5b13f849680a85f2a1ff7e
digest is independently pinned by the installed audit controller. Keep that
historical source byte-identical. Store the normal component-aware successor
as tools/scoped_backport_release_control_transition_worker.py and materialize
it only at the reviewed separate scoped-backport path. No historical audit
pin, native fixture assertion, or legacy installer is relaxed. Run the
original transition regression against both variants and the new
component-reader denial checks. Trigger the audit workflow on either
transition source change, before merge.

## Native preparation failure: exact guard mode and denial reporting

The authenticated attempt on candidate 34f9fc7cd57adf9889ec0461e74e06ede1f36a64
recorded the exact parent approval at 15:40:49 UTC on November 27 and
terminated with a verified predecessor rollback at 15:41:49 UTC. The
original engineering pause is retained. The former manager remains active;
the production freeze, incident hold and protected application peers remain
unchanged.

The reviewed preparation after-image specifies mode 0644 for the new
native health guard, whereas the existing independently pinned worker
requires a root-owned, single-link regular file with exact mode 0444 and
matching digest. This is a deterministic custody contract defect. An
isolated, network-disabled, read-only container with synthetic ledger state
reproduced rejection of the original 0644 image and acceptance of the
corrected 0444 image with identical guard bytes. It did not exercise
production acceptance or any provider. The earlier suspected readback
freshness race alone cannot explain the later attempt. The original
installer discarded the independent reader's precise denial reason, so
the historical child result cannot be recovered.

The source correction stages the guard with its existing required 0444
mode and preserves all independent health and ownership assertions.
Bounded diagnostic reporting retains known health denial reasons without
echoing arbitrary child output. Local affected regression: 257 passed,
5 isolated-root cases skipped in the ordinary run. The actual strict
reader custody rehearsal passed separately.

The failed attempt is terminal, not reusable authorization. A corrected
release requires normal protected-main review and a fresh exact approval.
The preserved pause is a rollback protection: the ordinary successor
preflight requires an unpaused predecessor, and the existing resume route
requires a verified non-rolled-back cutover. Do not remove that pause
manually, overwrite the immutable failure record, or claim this source
correction alone provides a supported recovery transition. Establish the
applicable governed recovery scope and verify the restored predecessor
before another production attempt.

### Exact successor of the verified terminal rollback

The corrected candidate may be considered while the predecessor is paused
only for the combined retirement scope, with the existing authenticated
Owner decision still required for the new candidate. The read-only
predecessor proof binds the exact failed candidate, root-owned immutable
approval, receipt-image and terminal rollback hashes; checks the
historical exact scope and predecessor receipt; requires the exact
three-record terminal history; and independently compares all original
target bytes, ownership, modes and absent paths. The retained pause must
match its approved bytes. The failed release directory must be absent.
Other paused predecessor cases retain their ordinary denial.

The new plan binds that evidence into its authenticated exact action.
After authentication, the installer repeats the original protected-source
and health checks, the rollback proof, and the before-image checks under
the existing native locks. The old approval is not reused or overwritten.
The pause remains in place until the existing successor cutover checks
succeed; failed acceptance continues to restore the pause.

Before the existing locked health checks, the combined retirement path now
waits outside the locks for the scheduled protected readback publisher to
provide clean evidence no more than 40 seconds old. This is a read-only
starting prerequisite, not a new source of health or a waiver: all
independent drift, breaker, core, image, audit, authority and ticket-scan
checks, including their original 120-second freshness requirement, are
unchanged. Unhealthy, future-dated or unavailable evidence fails closed.
No production timer, health record, authority, or lock is changed by
this wait.

Validation of this source candidate: 949 affected regression tests and
five subtests passed (five disposable-root tests excluded from the
ordinary run). Synthetic tests reject an unrelated request, a foreign
pause, changed records, extra history, changed restored files, and reuse
of the failed candidate; the scope is still sent to the existing
authenticator before locking or mutation. A protected-main native
preflight and a new exact authenticated approval are required.
