# OpenClaw Delegated Human Host Proof — 2026-08-08

## Result

PASS.

The live Jason host successfully proved the governed delegated-human execution chain using only synthetic capability `jason.synthetic.health`.

## Proven path

1. Jason synchronized to main at `32825e2`.
2. JKD-001 authority database upgraded non-destructively and reported owner-only mode `0600`.
3. OpenClaw replay, ingress audit, and orchestration audit SQLite files were verified at `0600`.
4. Synthetic human identity `synthetic-human-al` was created in organization `aot`.
5. Observe-only authority grant `grant-synthetic-human-health-observe` was issued for `jason.synthetic.health`.
6. Short-lived delegation `delegation-synthetic-human-openclaw-health` delegated that human's observe authority to `svc-openclaw-gateway`.
7. OpenClaw signed the delegated request with its existing Ed25519 private key; the private key remained inside the OpenClaw secret boundary.
8. Jason authenticated the OpenClaw machine identity, validated the delegation, evaluated the human's own JKD-001 authority, evaluated governance gates, issued a short-lived execution context, and executed through the Central Orchestrator.
9. The first request completed with orchestration status `succeeded`.
10. Replay of the same signed request was rejected with `replay_detected`.
11. The delegation was explicitly revoked.
12. A fresh request using the revoked delegation was rejected before authority/orchestration execution with `delegation_inactive`.

## Evidence summary

Successful delegated request:

- machine identity: `svc-openclaw-gateway`
- principal: `synthetic-human-al`
- delegated: `true`
- first request status: `completed`
- orchestration status: `succeeded`
- authority audit events: `1`
- ingress audit events: `6`
- orchestration audit events: `4`
- replay status: `rejected`
- replay reason: `replay_detected`
- provider contacted: `false`
- provider credentials used: `false`

Post-revocation request:

- status: rejected
- authority audit events: `0`
- orchestration audit events: `0`
- fail-closed reason: `delegation_inactive`
- provider contacted: `false`
- provider credentials used: `false`

Final JKD-001 health showed 2 identities, 2 grants, 1 delegation, and 2 execution contexts. The synthetic delegation remained stored as an audit/governance record but inactive after revocation.

## Constitutional conclusion

The deployed proof preserves the required separation of identity and authority:

- the Ed25519 key proves OpenClaw transport/service identity only;
- OpenClaw does not become or impersonate the human principal;
- the human principal requires independently governed JKD-001 authority;
- on-behalf-of use requires an explicit, bounded delegation record;
- delegation revocation fails closed before capability execution;
- governance gates and the Central Orchestrator remain mandatory;
- no provider credential or provider API was involved.

## Next operational hardening

- automated expiry/inactive delegation cleanup without destroying audit history;
- trusted OpenClaw machine-key rotation/revocation procedure;
- production ingress/state health checks;
- authority/OpenClaw SQLite backup and restore validation;
- update canonical CatchMeUp/session checkpoint after those controls are merged.
