# Teams Approval Transport Decision — 2026-08-10

## Purpose

Preserve the 2026-08-10 host findings and architecture decision that moved Jason Teams approval delivery away from ordinary Microsoft Graph app-only channel posting and toward the already-deployed OpenClaw Teams transport.

## Starting state

The Jason repository already contained:

- provider-neutral approval requests and responses;
- approval audit and replay/continuation controls;
- Microsoft tenant and identity binding;
- Teams card rendering;
- authenticated Teams ingress contracts;
- Teams delivery tests;
- Microsoft certificate-token foundations for governed Graph capabilities;
- OpenClaw as an existing Jason host service and interface/transport provider.

The repository-wide connector regression baseline was repaired in PR #138 before this workstream resumed.

## Live host inspection

The Jason host showed no deployed Jason-specific Microsoft/Teams credential boundary or target binding under the inspected `/opt/jason` and `/etc/jason` locations. No Microsoft secret, certificate, AppRole, or live Teams message was provisioned during the inspection.

The review then identified an architectural mismatch: the existing `TeamsApprovalDeliveryRuntime` used Microsoft Graph application credentials for ordinary Teams channel message posting, while Jason's newer Microsoft foundation preferred certificate-based app authentication. More importantly, ordinary Graph channel posting is not an appropriate normal app-only approval-message path; the app-only permission available for that endpoint is intended for migration scenarios.

Provisioning was intentionally stopped before introducing credentials or permissions.

## OpenClaw Teams capabilities observed

Host inspection of `/opt/jason/services/openclaw` established that the installed OpenClaw Microsoft Teams provider already supplies the required transport capabilities:

- proactive Teams messaging using stored conversation references;
- Adaptive Card delivery;
- sender/team/channel allowlists based on stable Microsoft identity information;
- authenticated inbound Bot Framework activities;
- explicit authorization checks for Adaptive Card action invokes;
- dispatch of non-poll `adaptiveCard/action` interactions;
- a supported Gateway `send` boundary with channel selection, target resolution, idempotency/deduplication, durable delivery, and delivery identifiers;
- an Admin HTTP RPC surface that intentionally does not expose arbitrary send/session methods.

The repository must not import OpenClaw TypeScript internals by filesystem path and must not broaden the Admin HTTP RPC allowlist merely to transport approvals.

## Constitution / Canon checkpoint

The design was explicitly reviewed against the Jason Constitution/Canon and found consistent with:

- Human Governance;
- Evidence Before Assertion;
- Separation of Responsibilities;
- Vendor Independence;
- Institutional Memory;
- the standing rule that OpenClaw is an interface/provider and not an authority.

Accepted authority flow:

`Human -> Teams -> OpenClaw transport -> Jason ingress -> JKD-001 / approval policy -> Central Orchestrator`

Accepted outbound flow:

`Central Orchestrator -> approval service -> Jason Teams adapter -> OpenClaw Gateway -> Teams -> Human`

OpenClaw authentication proves transport identity evidence; it does not itself make a Jason approval valid.

## Implementation direction

ADR-005 records the decision formally.

A thin Jason adapter is being introduced that:

- resolves an organization-scoped OpenClaw Teams proactive target;
- renders only approved non-secret approval metadata;
- calls the OpenClaw Gateway `send` capability with `msteams` as the transport channel;
- uses a deterministic Jason approval idempotency key;
- accepts only opaque delivery identifiers as transport evidence;
- fails closed on missing targets, organization mismatch, missing message identifiers, or unexpected returned channels;
- leaves inbound Microsoft tenant/object binding and approval authority entirely in Jason.

The previous Graph delivery runtime remains historical code during convergence; it is not the intended production Teams approval transport after ADR-005.

## Secret-safety statement

No access token, client secret, private key, certificate private material, Bot Framework credential, OpenBao secret, conversation-reference payload, or provider credential was copied into this record, chat evidence, or repository changes.

## Next validation

Before live Teams deployment:

1. pull the feature branch to the physical Jason host;
2. validate the new OpenClaw Teams adapter tests and full connector regression suite;
3. reconcile the exact OpenClaw Gateway `send` request shape against the installed OpenClaw version and fail closed if the installed contract differs;
4. move through release validation, PR, governance review, and merge;
5. configure the OpenClaw Teams provider and organization-scoped target without exposing secrets;
6. perform one harmless approval delivery/ingress round-trip;
7. prove Jason identity/authority, replay protection, audit, and orchestrator continuation end to end.
