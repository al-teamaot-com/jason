# Release Teams recipient != privileged administrator

**Scope:** source-only reviewed change, single existing approval workflow.
No live release, Microsoft tenant mutation, new Teams license, new OAuth application,
new approval ledger, or policy update is authorized by this document.

## Problem and decision

V4 ties the Owner's Teams delivery and signed release-approval actor to the
separate privileged al_admin@teamaot.com Entra identity, which is intentionally
unlicensed for Teams. The already-working licensed Teams account al@teamaot.com
cannot respond to those release cards, creating a circular bootstrap blocker.

In strict source-policy V4.1, reuse the existing relapproval- ApprovalRequest
ledger, Teams Adaptive Card, signed Bot Framework ingress, immutable card
challenge, host-side signed evidence verifier, CCC and exact release/unfreeze
checks. Select the **existing regular Owner Entra object** for both delivery
and the authenticated Owner's release.production.approve decision. The
privileged Entra administrator remains distinct and continues to be required
by the already-separated authorization mechanisms for **privileged management**
such as exact authority-grant operations. Do not let the Teams recipient
silently inherit the administrative grant role.

Version V4.1 differs from V4 at the exact approval actor selection, with a
different SHA-256 policy digest: any pending V4 card cannot silently become
a valid V4.1 decision. All signed evidence must match the request's original
policy hash, tenant, exact actor, release SHA, manifest, nonce, expiry, client
scope and one-use decision. Host consumer repeats the exact-actor check against
the durable Entra binding and independent current identity record; no
email/UPN fallback or identity-DB edits are permitted.

## Activation

This patch is NOT a production release. The release remains frozen and the
currently masked promotion timer is unchanged. Activation requires a separate
governed exact-SHA release with full protected-main scope review, independent
preproduction and root/CCC readback, and actual Teams-signed approval through
the existing approval ingress or a separately governed emergency recovery
channel. Never treat chat consent, an ordinary Teams message, old evidence,
or a locally crafted callback as such an approval.

The live V4 policy remains untouched until valid promotion. All tests use
isolated fixtures; the existing V2/V3/V4 behavior remains independently
supported for rollback without silently upgrading the existing 0600 policy.

## Acceptance

- One card is routed to the exact licensed normal Entra object, not admin
- A signed correct Owner click records the original immutable request once
- Wrong tenant, wrong OID, client scope, disabled actor, service actor, mismatched
  Entra identity and replay are denied by the runtime
- Host consumer independently verifies exact tenant/OID, challenge and identity
- Administrative authority profiles stay unchanged; regular Teams approval
  never supplies a privileged grant
- Release freeze, timer, drift, CCC, LKG and rollback gates remain intact

## Concurrent integration evidence

The following PRs were inspected for overlapping source paths and described
in PR #2398's Integration coordination field. The implementation is intentionally
not a synthesis or silent merge of their unapproved changes.

- #2395/#2378: separate admin-browser step-up for ordinary release review;
  not adopted under the Owner's simpler licensed Teams delivery directive.
  Their unrelated protected integrity work remains independent.
- #2393: separate service-originated approval-role proposal; not adopted.
- #2377: existing admin Teams reachability negative gate remains valid;
  an integration must keep no-message-on-unlicensed-admin behavior.
- #2279: superseded-release checks remain authoritative.
- #2336/#2384/#2382/#2373/#2355/#2282: shared file overlaps from financial,
  Constant Contact, Workboard, client notifications, internal notes and KFS;
  reconcile on the final protected-main SHA rather than guessing current head.

This is a coordination record, not a merge/release authorization.
