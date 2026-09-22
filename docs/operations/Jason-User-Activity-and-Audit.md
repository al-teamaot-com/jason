# Jason User Activity & Audit

## Section Goal

Provide AOT ownership and authorized administrators with a clear, secret-safe, append-only view of who is using Jason, from which channel, for what governed purpose, which capabilities are invoked, what provider/resource activity occurs, and how each event can be correlated for review.

## Scope

The activity/audit view is observational only. It must not grant provider access, mutation authority, approval authority, autonomous execution authority, or broader client visibility.

The initial production view is built from Jason's existing usage-attribution and orchestration telemetry. It records and exposes operational metadata only.

## Required audit dimensions

For each observable Jason interaction or provider/API attempt, retain or derive the following when available:

- authenticated Jason principal / actor identity;
- trusted display email for human actors;
- actor type (human or workload);
- source/channel;
- timestamp;
- structured purpose;
- governed capability;
- provider, product, or service involved;
- outcome;
- correlation ID;
- request/execution identifier;
- client, organization, ticket, device, or other governed scope when present in authoritative telemetry;
- approval and mutation metadata when those signals are present in orchestration telemetry.

## Privacy and secret boundary

Raw prompts, raw provider responses, credentials, bearer tokens, OAuth tokens, API keys, client secrets, and provider payload evidence are excluded from this dashboard telemetry.

Conversation text is not required for the administrative activity view. If AOT later chooses to retain conversational content, that must be governed by a separate explicit retention, access, and client-isolation policy.

## Integrity

Audit and usage-attribution records are append-only. Historical events are not rewritten to create a cleaner narrative. Reconciliation or correction must create a new adjustment/evidence record rather than silently mutating history.

Unknown or unavailable values must remain unknown; Jason must not fabricate attribution, cost, approval, client scope, or outcome data.

## Grafana operator view

Dashboard UID: jason-user-activity-audit

The dashboard provides observable Jason activity events, attribution coverage, unattributed event count, observed human identities, activity grouped by user/workload and source/channel, capability and provider activity, and recent trace rows containing identity, source, purpose, capability, provider, service, outcome, correlation ID, and timestamp.

Where approval, mutation, autonomous-execution, or client-access dimensions are not yet emitted as dedicated metrics, the dashboard must not imply that those dimensions are complete. They remain required audit fields for future telemetry expansion.

## Authority

Grafana and Prometheus remain observational. A visible event, actor, capability, approval, or provider result does not itself grant execution rights.

## Acceptance criteria

1. The documentation requirement is present in source control.
2. Grafana provisions dashboard UID jason-user-activity-audit.
3. The page uses only read-only Prometheus telemetry.
4. The page exposes no secrets or raw prompt/provider payload text.
5. Existing Jason runtime, MCP, OpenClaw, and provider-facing execution services are not restarted or modified by dashboard deployment.
6. Existing usage-attribution telemetry remains intact.
