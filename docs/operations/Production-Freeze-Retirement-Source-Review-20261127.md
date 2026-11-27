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
