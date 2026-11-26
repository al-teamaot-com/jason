# Jason Ticket/Owner Teams Recipient Correction (2026-11-13)

## Observed production defect

The existing `AutonomousCompletionTeamsInvoker` resolves the historical
`person-al` Jason binding before its `al@teamaot.com` fallback.
The current AOT Teams binding database has two separate, active records:

- `person-al` -> `al_admin@teamaot.com` (unlicensed Teams admin).
- `person-entra-bee80bdcffb04c50b453c09d4d411f5f` ->
  `al@teamaot.com` (regular Owner Teams identity).

The Teams proactive gateway recorded actual provider message IDs for
outbound ticket-status cards to the admin Entra object, and the Microsoft
Teams connector reports a 403 licensing error for that admin account.
A stored authenticated proactive conversation for the regular account
was observed; no recipient installation or Teams license purchase is
needed as a prerequisite to the source correction.

## Bounded correction

For the existing owner-only `communication.teams.autonomy.completion.send`
notification capability, resolve the exact licensed Owner's AOT tenant,
Entra object, Jason identity, email, active binding and non-client scope.
Do not use the `person-al` alias or any caller-supplied destination,
and fail closed if the exact record is missing or mismatched.

This changes only the owner notification **destination**, including
ticket pickup, status, blocker, resolution and the existing owner release
lifecycle notices using the same capability. It does **not** modify
Microsoft identities, binding records, approvals, existing permission
grants, ticket-worker scanning/claims/remediation, or Teams transport.
The separate `autonomous_completion_teams_compatibility` contract remains
unchanged.

## Acceptance evidence required

1. Focused invoker tests: two bindings present chooses only the regular
   Owner; legacy-only, revoked, mismatched, wrong tenant, cross-client,
   duplicate and spoofed argument fail closed.
2. Notification/outbox, auxiliary maintenance, runtime composition and
   ticket-worker regression tests pass.
3. Independently compare a prepared execution plan (without sending)
   against the real production identity binding read-only snapshot.
4. Approve the **exact final release source SHA and rollback SHA** under
   existing authenticated Owner/release and freeze controls.
5. After separately authorized deployment, verify a fresh actual ticket
   event yields a genuine Teams provider message ID for the regular Owner
   object, followed by regular-account receipt/readback, and that the
   ticket scanner remains healthy with unchanged PSA state and freeze.
6. If any mandatory production check fails, use the governed rollback.
   Do not replay historical delivered notifications or blast the
   prior backlog into the new destination.

No production activation is permitted by this documentation alone.
