# Direct Teams Gateway Production Proof — 2026-08-15

**Classification:** Historical proof / production cutover evidence  
**Status:** Completed / successful  
**Operator principal:** `person-al`  
**Environment:** `production-pilot`  
**Branch:** `feature/jason-runtime-service`  
**Architecture decision:** `docs/decisions/ADR-009-Direct-Microsoft-Teams-Ingress.md`

## Purpose

Preserve the production evidence that ordinary Microsoft Teams conversation ingress was successfully moved from OpenClaw to the dedicated Jason Teams Gateway while keeping Jason Runtime and OpenClaw healthy and preserving a tested rollback path.

This record is point-in-time evidence. Current production topology remains governed by the System Registry and fresh host observation when required.

## Why the architecture changed

The previous Teams path depended on OpenClaw owning inbound transport and handing Jason-bound turns to the `jason-bridge` before OpenClaw's own model path could respond.

Live investigation disproved the assumption that a Jason plugin binding guaranteed exclusive turn ownership. Several interception approaches were attempted and then abandoned:

- `before_agent_run` did not execute for the live Teams path;
- `before_agent_reply` did not execute for the live Teams path;
- plugin-owned inbound claim did not execute reliably for the live Teams path;
- a plugin-bound Teams session was observed still entering the OpenClaw GPT-backed agent trajectory;
- direct patching of the packaged OpenClaw Teams bundle was abandoned after repeated deployment failures and packaging-layout brittleness.

The architectural response was to remove OpenClaw from ordinary inbound Teams ingress rather than continue adding routing patches.

## Direct gateway implementation

The direct gateway implementation is under:

`infrastructure/jason-teams-gateway/`

Key files:

- `index.mjs` — authenticated Microsoft Teams ingress, identity/context checks, bounded acknowledgement, signed Jason envelope, governed runtime call, deterministic response;
- `Dockerfile` — Node 24 production container;
- `bootstrap-azure-credential.sh` — one-time append-only creation of a dedicated Jason Teams application credential without reading/replacing the existing OpenClaw credential;
- `deploy-pilot.sh` — isolated health pilot on host loopback port 3979;
- `cutover-production.sh` — controlled production host-port transfer from OpenClaw to the direct gateway;
- `rollback-production.sh` — restores the original OpenClaw Compose state and port ownership.

The gateway reuses the existing signed Jason conversation-envelope contract and the already-trusted Ed25519 ingress identity. It does not contain a model, agent loop, provider-selection logic, business authority, or direct provider call.

## Credential bootstrap proof

The existing Teams/Entra application was resolved as:

- application/client ID: `c94301b7-7194-46ab-aab7-94f9366f51a9`;
- tenant ID: `f7054323-d52b-4863-8c2f-1898f0b6077c`;
- application display name observed during bootstrap: `Jason Approval Bot`.

The operator authenticated to Azure with an authorized AOT administrative identity. The bootstrap then appended a second credential named for the Project Jason Teams Gateway.

Observed result:

```text
PASS: dedicated Jason Teams credential created and stored with mode 0600
PASS: existing OpenClaw Teams credential remains intact
CREDENTIAL_BOOTSTRAP_STATUS=PASS
```

No credential value was printed or stored in Git/documentation.

The credential remains in the host-protected migration file:

`/opt/jason/services/jason-teams-gateway/msteams.env`

Mode at creation: `0600`.

## Isolated pilot proof

After explicit Microsoft Agents SDK authentication configuration was corrected, the isolated pilot started successfully:

```text
========== PILOT HEALTH ==========
{"status":"ok","service":"jason-teams-gateway","runtime":"http://jason-runtime:8080/v1/openclaw/teams/conversation"}

DIRECT_GATEWAY_LOCAL=http://127.0.0.1:3979/api/messages
OPENCLAW_3978_BINDING=0.0.0.0:3978 [::]:3978

PILOT_STATUS=PASS
```

This proved the direct gateway could initialize with the dedicated Microsoft identity, access the governed ingress signing key, join the runtime network, and reach the Jason Runtime without changing the live Teams path.

## Production cutover

The production cutover retained the existing public Teams endpoint and transferred only host port `3978`.

The final cutover implementation inspected the live Docker port bindings rather than assuming the literal Compose syntax. The observed pre-cutover bindings were:

```text
CURRENT_OPENCLAW_3978=0.0.0.0:3978 [::]:3978
REMOVED_RUNTIME_BINDING=*:3978->3978/tcp
PRESERVED_RUNTIME_BINDING=*:18789->18789/tcp
PRESERVED_RUNTIME_BINDING=*:18790->18790/tcp
```

The generated OpenClaw Compose configuration validated before the live file was replaced.

A backup was created at:

`/opt/jason/services/openclaw/docker-compose.yml.pre-jason-teams-20260815T173328Z`

The cutover then produced:

```text
PASS: OpenClaw remains running without host port 3978
{"status":"ok","service":"jason-teams-gateway","runtime":"http://jason-runtime:8080/v1/openclaw/teams/conversation"}
PASS: direct Jason Teams gateway owns host port 3978

CUTOVER_STATUS=PASS
READY_FOR_TEAMS_LIVE_TEST=1
```

## Final observed service topology

After cutover:

```text
NAMES                         STATUS                   PORTS
jason-teams-gateway           Up                       0.0.0.0:3978->3979/tcp
openclaw-openclaw-gateway-1   Up (healthy)             0.0.0.0:18789-18790->18789-18790/tcp, [::]:18789-18790->18789-18790/tcp
jason-runtime                 Up (healthy)             8080/tcp
```

Interpretation:

- the direct gateway owns externally reachable Teams ingress on the Jason host;
- OpenClaw remains healthy for other approved functions;
- OpenClaw no longer publishes host port 3978;
- Jason Runtime remains internal and healthy.

## Live Teams end-to-end proof

The operator sent the production Teams request:

`Hey Jason, can you tell me who was last on AOT-50282 and if anything is wrong with it right now?`

The Teams response was:

```text
AOT-50282 — last logged in user: AzureAD\AlDavis. Source: datto_rmm. AOT-50282 — 1 alert found. Moderate — Unhealthy - Local user changes detected vs previous compare file.;AddedUsers=CodexSandboxOffline,CodexSandboxOnline;RemovedUsers=. Source: datto_rmm.
```

This exactly matched the previously proven governed Datto-backed facts for the test endpoint:

- last logged-in user: `AzureAD\AlDavis`;
- one moderate `Unhealthy` alert;
- added local users: `CodexSandboxOffline`, `CodexSandboxOnline`;
- provider evidence source: `datto_rmm`.

## Direct gateway completion evidence

The direct gateway emitted a startup event and three completed Teams turns during the evidence window:

```text
{"event":"jason_teams_gateway_started","port":3979,"tenantId":"f7054323-d52b-4863-8c2f-1898f0b6077c","clientId":"c94301b7-7194-46ab-aab7-94f9366f51a9"}
{"event":"jason_teams_turn_completed","status":"completed","httpStatus":200,...}
{"event":"jason_teams_turn_completed","status":"completed","httpStatus":200,...}
{"event":"jason_teams_turn_completed","status":"completed","httpStatus":200,...}
```

Conversation/message identifiers are intentionally omitted from this durable narrative because they are not required to establish the architectural result.

## OpenClaw bypass proof

During the same evidence window, the filtered OpenClaw log contained only startup/provider initialization information:

```text
[gateway] http server listening (... jason-bridge ... msteams ...)
[msteams] starting provider (port 3978)
```

There was no matching:

- `dispatching to agent`;
- `plugin-binding` execution line;
- ordinary Teams model trajectory.

The internal OpenClaw `msteams` provider still reports its configured listener port during startup, but Docker no longer publishes that container port to the host. The externally reachable port is owned by `jason-teams-gateway`.

## Governance result

The live path was proven as:

`Teams -> Direct Jason Teams Gateway -> signed trusted ingress -> Jason Runtime -> Central Orchestrator -> governed Datto RMM capability/provider -> evidence-backed response -> Teams`

The proof does not grant authority to the gateway. Microsoft identity remains transport/authentication evidence. Jason's existing identity binding, exact-message idempotency, policy, Central Orchestrator, capability/provider resolution, and evidence controls remain authoritative.

## Rollback evidence and command

The cutover created:

`/opt/jason/services/jason-teams-gateway/cutover-state.env`

The governed rollback entry point is:

```bash
bash infrastructure/jason-teams-gateway/rollback-production.sh
```

Rollback removes the direct production gateway, restores the saved OpenClaw Compose configuration, recreates the OpenClaw service, and verifies that OpenClaw again owns host port 3978.

Rollback was not required because production proof passed.

## Durable implementation checkpoints

Important checkpoints from the direct-gateway migration include:

- `065f8f9fb1a3b645a6a4bc3711865581ca6dcdd7` — add direct Teams gateway package;
- `30c6209cdf6eced3e534dd2787941e9bcb60a88d` — implement direct governed Teams ingress;
- `4502c396211ed70f46130e118cb3ab450fe4f122` — add gateway container;
- `0cb2d6083e18889651d9e10e19e16df8621a1690` — add dedicated Azure credential bootstrap;
- `1cc0d61f7c3d20ba55617e9c6c93613181af90b8` — expose Azure device-login prompt correctly;
- `8be9593964d0b5242b1d4c709c9fd0e006a0c7ac` — initialize Microsoft Agents SDK with explicit gateway authentication;
- `1e3003f74845f4af6786a6ab36d8e99b20fbcdce` — release Teams port from resolved OpenClaw runtime bindings and complete production cutover.

## Durable lessons

1. Plugin/session binding is not proof of exclusive conversational ownership.
2. A transport adapter must not depend on a model lifecycle hook to enforce Jason's authority boundary.
3. After three concrete failures of an integration technique, changing the architecture is preferable to accumulating brittle patches.
4. Stable public endpoints can often be preserved by changing local service ownership behind the edge.
5. Deployment tooling should derive live topology from Docker/Compose state rather than assuming literal source syntax.
6. Rollback must be created before production mutation and must verify restored state, not merely restart a process.
7. Dedicated application credentials should be added without extracting or replacing an existing provider's protected secret.
8. Transport components should remain small and non-intelligent; reasoning, authority, provider selection, and response assembly belong to Jason.

## Remaining hardening, not a routing blocker

The routing workstream is complete. Remaining follow-up is operational hardening:

- review and disable the dormant OpenClaw inbound `msteams` listener/provider path where that can be done without breaking approved outbound/proactive behavior;
- migrate the direct gateway's dedicated Microsoft credential from the temporary mode-0600 host file into Jason's preferred governed secret-delivery architecture or certificate/federated identity;
- add the direct gateway and current port topology to the System Registry and verification plan;
- keep the production rollback procedure current as Compose topology evolves.

These follow-ups do not invalidate this proof.
