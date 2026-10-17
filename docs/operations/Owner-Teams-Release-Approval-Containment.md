# P0 #1554 — Owner Teams Release Approval Containment

**Status: isolated source candidate only. Not installed or activated in production.**

Related: #1553 disputed Teams approval provenance; #1554 containment.

## Scope and constitutional separation

This hold applies only to existing release.production.approve approval requests with relapproval- IDs. It does not disable ordinary Teams messaging, notifications, procurement, ticket processing, the test-only universal owner acceptance flow, or separately approved manual release and CCC governance.

Three independent boundaries consume the same 0600 state: (1) Teams card issuer and release-manager offer generation; (2) signed Approve/Deny callback before receipt consumption; (3) host Release Manager consumer before transfer of signed approval into exact-SHA CCC/owner release authorization.

Both Approve and Deny fail closed while held. Signed approvals recorded before the hold cannot be converted to release authority. Historic evidence is preserved, never deleted, re-signed, or relabeled.

## Durable security state

Shared path (visible to runtime and host): /var/lib/jason/openclaw/release-manager/owner-release-approval-containment.json

The exact schema of a held state is:

```json
{
  "schema_version": "1.0",
  "capability": "release.production.approve",
  "state": "held",
  "hold_id": "P0-1553",
  "hold_started_at": "2026-10-17T20:00:00Z"
}
```

Sample time is illustrative only, not an actual activation record. A separately authorized activation must record the true UTC timestamp.

A separately approved release of the containment changes state to released, preserves the original hold ID and hold_started_at, and adds a UTC released_at strictly after hold_started_at. The file MUST remain present. All requests created before or at released_at are permanently ineligible at callback and host consumption, including previously approved records. A fresh owner approval is required after the hold is lifted. This prevents stale callback resurrection.

Containment file validation requires a 0600 regular file owned by root or the executing service UID, no symlink, bounded JSON, exact fields and scope, UTC timestamps, and a valid P0 case ID. Invalid policy fails closed. No containment file before initial activation preserves the already-authorized normal-risk mobile release pilot behavior.

Never create, edit, or delete the file outside a separately owner-approved, audited governed release/change. This PR does not itself add a new remote command, authority role, privileged shell execution, or mutable policy API. Any safe activation path must verify state readback from both runtime and host and coordinate against release-manager execution to avoid a cross-process race. Source code alone is not proof of active containment.

## Auditing and operational validation

- Issuer: distinct OWNER_RELEASE_APPROVAL_HOLD_ACTIVE warning; no card request created.
- Signed callback: existing authenticated-ingress denial event includes owner_release_approval_hold_active reason.
- Host: OWNER_RELEASE_APPROVAL_HOLD_ACTIVE return without creating owner approval or CCC material review.
- Released state refuses old signed requests by creation timestamp, not by whether a previously signed decision looked valid.
- A malformed/insecure containment state never grants authority.
- Existing manual break-glass owner review, exact source checks, CCC and rollback remain intact. Teams interaction is not shell/root authority.

## Go-live restrictions

Full containment requires a separately authorized production change. The earlier disputed approval in #1553 remains unresolved. The harmless owner UAT acceptance in PR #1555 is a distinct workflow and must be verified by the Owner actually clicking Approve and Deny in Teams. A Bot Framework signature or provider-accepted card receipt is not proof of a physical human click.
