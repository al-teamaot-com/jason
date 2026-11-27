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
Version 1 remains cryptographically unchanged and cannot satisfy version 2.
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

Local regression: 371 tests and five subtests passed, including the
existing frozen-proof path, isolated normal-mode issuer and native
verification, wrong-mode denial and legacy recovery conflict.

## Unresolved before production eligibility

1. Independent high-risk security review of the entire exact change.
2. Integrate the existing mobile/Teams release-approval channel with the
   normal release policy without adding a second Owner decision. The
   current normal-mode candidate admits only the signed MCP route.
3. Reconcile active independent-component, catalog and scoped-backport
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
