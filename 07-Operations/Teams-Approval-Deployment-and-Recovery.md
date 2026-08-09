# Teams Approval Deployment and Recovery Runbook

## Goal

Deploy and validate Microsoft Teams as a governed approval delivery/response channel without allowing Teams, Microsoft identity, or Microsoft Graph to become an authority boundary.

## Preconditions

Before a live approval test, confirm:

1. repository approval tests and `Validate Jason` are green;
2. JKD-001 durable identity, grant, approval, and authority-context persistence is available;
3. approval audit storage is configured and durable;
4. the approval continuation replay guard and recovery ledger use durable local storage appropriate to the deployment model;
5. INF-013 artifact/evidence storage is available for referenced evidence;
6. OpenBao and the canonical Jason secret-provider wrapper are healthy;
7. the Microsoft application and tenant configuration are explicitly approved;
8. organization-to-Team/channel and Microsoft-tenant/object-to-Jason bindings are known and reviewed.

## Live Microsoft/Teams configuration

Record non-secret configuration only:

- Microsoft tenant ID;
- application/client ID;
- approved Graph permission profile;
- secret reference identifier, never the secret value;
- Jason organization ID;
- Team ID and channel ID for that organization;
- permitted Jason approver identities and their Microsoft object bindings;
- token audience and expected tenant binding;
- deployment timestamp and operator.

Never place access tokens, client secrets, private keys, raw approval evidence, or provider payloads in Git or normal operational evidence.

## First controlled test

Use a harmless no-side-effect test capability or an explicitly non-executing approval fixture.

Expected sequence:

1. Central Orchestrator creates a request that policy marks as approval-required.
2. Provider-neutral approval request is persisted and `REQUEST_CREATED` audit evidence exists before delivery.
3. The organization-scoped Teams target resolves exactly once.
4. Microsoft Graph delivers the approval message.
5. The delivery receipt is recorded as evidence only.
6. The approver responds in Teams.
7. Microsoft authentication is cryptographically verified.
8. Microsoft tenant/object identity binds to the expected Jason organization/identity.
9. Provider-neutral approval authorization succeeds for the exact request/capability scope.
10. The formal JKD-001 approval record is persisted immutably.
11. JKD-001 performs fresh requester reauthorization and returns a new short-lived authority context.
12. The continuation is consumed once and handed only to Central Orchestrator.
13. The resulting terminal or controlled test outcome is recorded in the immutable approval audit chain.

A successful Teams click alone is not a successful approval test. All authority and evidence stages above must be observed.

## Mandatory negative tests

Before enabling a side-effecting capability, verify fail-closed behavior for at least:

- expired approval;
- unauthorized approver;
- Microsoft object ID not bound to a Jason identity;
- Microsoft tenant not bound to the Jason organization;
- organization mismatch in request or channel target;
- modified/untrusted Adaptive Card identity fields;
- missing or invalid Microsoft signature/audience/issuer;
- missing fresh JKD-001 authority context;
- replay of an already-consumed approval continuation;
- cross-tenant reuse of an approval ID;
- conflicting immutable approval record reuse;
- unavailable audit persistence.

## Interrupted execution

If an approval continuation has been consumed but the execution outcome is unknown, do **not** delete the replay claim, modify the approval record, or simply rerun the request.

Treat the operation as indeterminate until evidence establishes what occurred.

### Recovery dispositions

An authorized recovery operator records exactly one new recovery decision with supporting evidence references:

- `confirmed_completed` — evidence proves the operation completed; no retry occurs.
- `confirmed_not_executed` — evidence proves the operation did not execute; this fact alone still does not create retry authority.
- `abandoned` — the operation is intentionally left unresolved/terminated and will not be retried through this recovery decision.
- `retry_authorized` — a retry is explicitly approved and carries a new JKD-001 authority context.

### Governed retry

For `retry_authorized`:

1. obtain fresh JKD-001 authority for the exact organization/request/capability scope;
2. record the recovery decision immutably with reason and evidence references;
3. verify the retry request carries the exact authority context stored in the recovery record;
4. atomically consume the recovery authorization;
5. invoke only Central Orchestrator;
6. record the resulting orchestration outcome in approval audit evidence.

A recovery authorization is one-time use. If the retry outcome becomes indeterminate, create a new recovery decision and obtain fresh authority again.

## Stop conditions

Stop and fail closed when any of the following occurs:

- organization, client, request, correlation, capability, approver, or authority scope cannot be proven;
- the approval is expired, denied, already consumed, or conflicting;
- Microsoft authentication or Jason identity binding fails;
- audit/evidence persistence fails;
- a Team/channel target is missing, disabled, ambiguous, or belongs to another organization;
- required secrets cannot be resolved through the approved provider;
- a replay claim or recovery authorization would need to be manually deleted to proceed;
- an operator cannot establish whether a potentially side-effecting operation already occurred.

## Production rule

Teams is transport. Microsoft authentication is identity evidence. Provider-neutral approval policy determines whether the response is acceptable. JKD-001 creates execution authority. Central Orchestrator alone resumes or retries execution. Audit and INF-013 preserve the evidence required to prove that chain.