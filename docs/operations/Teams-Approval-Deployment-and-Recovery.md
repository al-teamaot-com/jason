# Teams Approval Deployment and Recovery Runbook

## Goal

Deploy and validate Microsoft Teams as a governed approval delivery/response channel without allowing Teams, Microsoft identity, Microsoft Graph, or OpenClaw to become an authority boundary.

## Architecture decision

ADR-005 establishes OpenClaw as the preferred Microsoft Teams transport/interface provider for Jason approvals.

Outbound:

`Central Orchestrator -> approval service -> Jason Teams adapter -> OpenClaw Gateway -> Teams -> Human`

Inbound:

`Human -> Teams -> authenticated OpenClaw activity -> Jason Teams ingress -> JKD-001 / approval policy -> Central Orchestrator`

OpenClaw is transport only. A successful Teams button click means only that an authenticated Microsoft identity submitted an interaction. Jason must still prove tenant/organization scope, bind the Microsoft object to a Jason identity, authorize that identity for the exact approval request, persist the formal approval decision, obtain fresh JKD-001 authority, and resume only through the Central Orchestrator.

## Preconditions

Before a live approval test, confirm:

1. repository approval tests and `Validate Jason` are green;
2. JKD-001 durable identity, grant, approval, and authority-context persistence is available;
3. approval audit storage is configured and durable;
4. the approval continuation replay guard and recovery ledger use durable local storage appropriate to the deployment model;
5. INF-013 artifact/evidence storage is available for referenced evidence;
6. OpenBao and the canonical Jason secret-provider wrapper are healthy for any Jason-owned secrets used by the deployment;
7. the OpenClaw Microsoft Teams provider is configured, healthy, and approved for the intended tenant/account;
8. OpenClaw has a valid stored Teams conversation reference for the intended proactive delivery target;
9. organization-to-OpenClaw Teams target and Microsoft-tenant/object-to-Jason bindings are known and reviewed;
10. the OpenClaw Gateway `send` boundary is available to the Jason transport adapter without expanding the Admin HTTP RPC allowlist;
11. the constitutional/architecture review recorded in ADR-005 remains applicable.

## Live Teams/OpenClaw configuration

Record non-secret configuration only:

- Microsoft tenant ID associated with the OpenClaw Teams provider;
- OpenClaw Teams account/provider identifier when multiple accounts exist;
- Jason organization ID;
- governed OpenClaw Teams proactive-delivery target/reference identifier;
- human-readable Team/channel description for operator review when applicable;
- permitted Jason approver identities and their Microsoft object bindings;
- expected Microsoft tenant binding;
- OpenClaw provider/version observed during validation;
- deployment timestamp and operator.

Never place access tokens, client secrets, private keys, Bot Framework credentials, raw conversation-reference payloads, raw approval evidence, or provider payloads in Git or normal operational evidence.

## Transport rules

- Jason must use the supported OpenClaw Gateway/channel boundary; do not import OpenClaw TypeScript implementation files directly into Jason.
- Do not broaden the OpenClaw Admin HTTP RPC allowlist merely to send approval messages.
- Every approval delivery must use a deterministic idempotency key derived from governed Jason identifiers so transport retries do not create duplicate approval authority.
- OpenClaw `messageId`, `conversationId`, `channelId`, and similar fields are delivery evidence only.
- The approval card may contain only approved non-secret metadata and evidence references.
- OpenClaw authentication/allowlist success does not replace Jason identity binding or approval authorization.
- Microsoft Graph certificate authentication remains available for Graph capabilities that actually require Graph; it is not the Teams approval transport authority.

## First controlled test

Use a harmless no-side-effect test capability or an explicitly non-executing approval fixture.

Expected sequence:

1. Central Orchestrator creates a request that policy marks as approval-required.
2. Provider-neutral approval request is persisted and `REQUEST_CREATED` audit evidence exists before delivery.
3. The organization-scoped OpenClaw Teams target resolves exactly once.
4. Jason renders approved non-secret approval metadata into the Teams Adaptive Card payload.
5. Jason submits the delivery through the supported OpenClaw Gateway `send` capability with channel `msteams` and a deterministic idempotency key.
6. OpenClaw resolves the stored Teams conversation reference and delivers the Adaptive Card.
7. OpenClaw returns an opaque delivery receipt/message identifier; Jason records it as evidence only.
8. The approver responds in Teams.
9. OpenClaw/Bot Framework authentication validates the inbound Teams activity before dispatch.
10. Jason receives the authenticated interaction and independently binds Microsoft tenant/object identity to the expected Jason organization/identity.
11. Provider-neutral approval authorization succeeds for the exact request/capability scope.
12. The formal JKD-001 approval record is persisted immutably.
13. JKD-001 performs fresh requester reauthorization and returns a new short-lived authority context.
14. The continuation is consumed once and handed only to Central Orchestrator.
15. The resulting terminal or controlled test outcome is recorded in the immutable approval audit chain.

A successful Teams click alone is not a successful approval test. All authority and evidence stages above must be observed.

## Mandatory negative tests

Before enabling a side-effecting capability, verify fail-closed behavior for at least:

- expired approval;
- unauthorized approver;
- Microsoft object ID not bound to a Jason identity;
- Microsoft tenant not bound to the Jason organization;
- organization mismatch in request or OpenClaw Teams target;
- modified/untrusted Adaptive Card identity fields;
- OpenClaw/Bot Framework authentication failure;
- authenticated OpenClaw interaction that fails Jason identity binding;
- OpenClaw delivery response with missing message identifier or unexpected channel;
- missing proactive conversation reference/target;
- duplicate delivery using the same Jason idempotency key;
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
- OpenClaw/Bot Framework authentication or Jason Microsoft identity binding fails;
- audit/evidence persistence fails;
- an OpenClaw Teams target is missing, disabled, ambiguous, lacks a stored conversation reference, or belongs to another organization;
- the OpenClaw Gateway cannot provide the governed Teams transport capability;
- an implementation would require direct imports of OpenClaw internals or an unnecessary expansion of its admin HTTP surface;
- required secrets cannot be resolved through their approved provider boundary;
- a replay claim or recovery authorization would need to be manually deleted to proceed;
- an operator cannot establish whether a potentially side-effecting operation already occurred.

## Production rule

Teams is the human interface. OpenClaw is transport and authenticated-ingress infrastructure. Microsoft authentication is identity evidence. Provider-neutral Jason approval policy determines whether the response is acceptable. JKD-001 creates execution authority. Central Orchestrator alone resumes or retries execution. Audit and INF-013 preserve the evidence required to prove that chain.
