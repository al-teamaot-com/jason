# Retire the V4 admin-account release approval dependency

**Source preparation. Not a production deployment or authorization.**

## Owner direction

The release approval mechanism must not depend on the unlicensed
`al_admin@teamaot.com` Teams recipient. The previous V4/V4.1
`admin_approver_separated` *release-approval mode* is withdrawn.

Restore the exact previously accepted V2 source policy from
`c43e88e072c0b35c5b342d5e712fe34565b3e0cd`. This is the
existing `owner_reviewed` Teams release flow, targeting the licensed
`al@teamaot.com` Owner through the already installed canonical
Teams approval gateway. It still requires signed Teams callback,
one-use immutable approval record, reviewed SHA/manifest, original
risk profile, production CCC and verified rollback. No other
approval channel, new login, new service or new application.

## Source-control scope

Only the source policy and assertions identifying the active
deployment policy are changed. The existing V4/V4.1 version-aware
code remains solely for previously issued evidence and governed
rollback compatibility. Historical V4 security tests now construct
their own isolated 0600 fixture instead of reading the retired source.

Because the existing release manager and deploy scripts already
calculate the mode from the exact immutable policy:
- runtime mode becomes `owner_reviewed` (not `admin_approver_separated`);
- the optional `admin-separated-v1` privilege grant mode is **not**
  silently activated from the retired release policy;
- no regular technician gets privilege-grant rights by virtue of
  receiving a Teams card; role enforcement in the legacy
  authority-grant path remains separately governed and must be
  checked in production before accepting restoration.

This source change does not mutate the currently active V4
private policy, a production freeze marker, failed breaker, masked
timer, admin identity database or ticket-processing state.

## Validation and release boundary

Require protected CI and tests of source policy, native runtime and
MCP deployment validators, high-impact signed Owner release approval,
wrong-identity and replay rejection, privileged-grant checks, and
non-disruptive ticket-worker continuity. One controlled Teams-signed
Owner authorization for the final immutable source SHA remains
necessary to deploy. Verify the private 0600 policy, runtime mode,
real Teams card delivery/callback on the licensed Owner account,
host consumer, and rollback readiness after deployment. Do not
treat a GitHub merge or a prior chat statement as deployment proof.
