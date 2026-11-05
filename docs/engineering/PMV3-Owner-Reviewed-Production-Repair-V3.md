# PMv3 owner-reviewed production repair (V3) — source-only design

**Development authorization:** Owner approval of issue #2324 for engineering
only. This does **not** approve a specific production release, allow a provider
action, change any live policy, or lift the production freeze.

## Why

The existing production V2 Teams channel intentionally permits only
`normal` and `production_control_core`. Native PM correctly classified the
heartbeat migration as `production_repair` and refused to issue a Teams card.
Misclassifying that change would bypass the recorded release risk.

## Minimal solution

- V1 and V2 retain their **exact** risk contracts, and the installed/source
  `config/mobile-release-approval-policy.json` remains V2 unchanged.
- New V3 is a *separately opt-in* reviewed contract using schema_version
  `3.0`, policy_mode `owner_reviewed`, and the **exact** risk set
  `normal`, `production_control_core`, `production_repair`.
  `schema_or_contract` and other undeclared risks remain prohibited.
- Identity is still `person-al`, approval capability
  `release.production.approve`, request TTL 300–900 seconds, and the same
  mandatory `high_impact_review` booleans remain true:
  `owner_exact_sha_required`, `signed_teams_identity_required`,
  `independent_ccc_required`, `protected_release_gates_unchanged`.
- The Teams card and the independent host consumer validate the exact SHA,
  rollback SHA, manifest hash, private policy digest, signed Entra-bound
  owner identity, issued card-instance challenge, expiry, and replay ledger.
  The click records an approval only; it never deploys or unfreezes.
- Protected production gates, manual scope review, preproduction, immutable
  images, rollback-readiness, the separate one-time freeze exception, and
  final post-production verification remain unchanged.

## Activation / rollback boundary

This patch implements and tests V3 support **without activating it**. A
separately reviewed, signed **exact-SHA production-control release** must
first deploy code that understands V3. Activation of V3 then requires its
own Owner-approved source-policy revision and governed atomic staging of
the private 0600 policy; it is not authorized merely by merging this PR.
If activation fails, the native policy stage restores the original exact V2
bytes before runtime rollback. Do not edit the live policy directly.

Only after a V3 policy is active and the current protected production SHA
is reconciled may a separately built `production_repair` candidate receive
a fresh Teams card. The prior b163 candidate/approval is not transferable
across a changed production baseline.

## Evidence / follow-up

Contract tests cover V1/V2 non-expansion, V3 opt-in and rollback,
signed Teams callback and independent consumer, denied/forged challenges,
modified manifest/policy, revoked identity, and idempotent replay.

Tracked by #2324 and #2316. This does not change the separate one-click
freeze-exception UX requested in #2316.
