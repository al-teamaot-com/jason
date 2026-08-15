# Runbook — Jason Microsoft Teams Integration

**Status:** Active operational runbook  
**Owner:** Jason Architecture Authority  
**Last validated:** 2026-08-15  
**Governing decisions:** `ADR-006`, `ADR-007`, `ADR-009`  
**Production proof:** `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`

## Purpose

Operate, verify, recover, and safely extend Jason's Microsoft Teams integration without depending on chat history or treating the interface layer as execution authority.

The current architecture intentionally separates:

- **ordinary inbound Teams conversation ingress** — owned by the direct `jason-teams-gateway`;
- **Jason reasoning/governance/execution** — owned by `jason-runtime` and the Central Orchestrator;
- **OpenClaw** — still deployed for other approved interface/transport functions and historical/proactive Teams functionality, but no longer the externally reachable owner of ordinary inbound Teams messages.

This runbook does not grant execution authority. Jason identity, policy, approval, capability resolution, provider authority, and Central Orchestrator controls remain governing.

## 1. Current production architecture

### Public ingress

The existing public Microsoft Teams endpoint remains:

`https://teams-jason.teamaot.com/api/messages`

Current edge topology:

- public DNS: `teams-jason.teamaot.com`;
- public Elastic IP historically established for the Teams relay: `18.235.19.103`;
- AWS relay instance: `i-0b0bb56884acb565c`;
- relay ZeroTier IP: `10.87.246.16/24`;
- Jason host ZeroTier IP: `10.87.246.157/24`;
- relay forwards the Teams path to the Jason host on TCP `3978`.

The public endpoint and Microsoft-side Teams registration were intentionally preserved during the 2026-08-15 cutover.

### Current host/service path

```text
Microsoft Teams
  -> teams-jason.teamaot.com/api/messages
  -> AWS relay / ZeroTier
  -> Jason host :3978
  -> jason-teams-gateway container :3979
  -> signed Jason conversation envelope
  -> jason-runtime:8080/v1/openclaw/teams/conversation
  -> governed conversation flow
  -> Central Orchestrator
  -> governed capability/provider
  -> deterministic response
  -> Microsoft Teams
```

Current production service names:

- direct Teams ingress: `jason-teams-gateway`;
- governed runtime: `jason-runtime`;
- OpenClaw: `openclaw-openclaw-gateway-1`.

Expected published ports after successful cutover:

- `jason-teams-gateway`: host `3978` -> container `3979`;
- OpenClaw: host `18789-18790` only;
- `jason-runtime`: internal Docker port `8080`, not published to the host.

OpenClaw may log that its internal `msteams` provider is starting on port `3978`; this does **not** mean it owns external Teams ingress. Verify Docker host-port ownership rather than inferring topology from an internal provider startup message.

## 2. Microsoft identity

Current non-secret identifiers:

- tenant ID: `f7054323-d52b-4863-8c2f-1898f0b6077c`;
- Teams/Entra application ID: `c94301b7-7194-46ab-aab7-94f9366f51a9`;
- Teams organization catalog app ID: `1b24025a-201f-439d-a4ef-e308c7f3d853`;
- published Teams app endpoint: `https://teams-jason.teamaot.com/api/messages`.

The direct gateway uses a dedicated application credential appended to the existing Entra application. The pre-existing OpenClaw credential was not read, replaced, or deleted during migration.

Current migration credential location:

`/opt/jason/services/jason-teams-gateway/msteams.env`

Required protection: mode `0600` or tighter, readable only by the intended host/runtime identity. Never print or commit the credential value.

Long-term hardening target: migrate the dedicated gateway credential into Jason's governed secret-delivery architecture or certificate/federated authentication.

## 3. Direct gateway implementation

Repository package:

`infrastructure/jason-teams-gateway/`

Important files:

| File | Purpose |
|---|---|
| `index.mjs` | Microsoft Agents SDK request authentication, tenant/AAD identity checks, bounded acknowledgement, signed Jason envelope, runtime call, deterministic response |
| `Dockerfile` | production container build |
| `bootstrap-azure-credential.sh` | one-time append-only creation of a dedicated gateway app credential |
| `deploy-pilot.sh` | isolated loopback pilot on host port 3979 |
| `cutover-production.sh` | controlled production transfer of host port 3978 from OpenClaw to the direct gateway |
| `rollback-production.sh` | restores OpenClaw Compose and returns host port 3978 to OpenClaw |

The gateway intentionally has no LLM/agent loop and no provider-selection or direct provider logic.

## 4. One-time credential bootstrap

Run only when the dedicated gateway credential does not already exist or when a governed rotation is required.

The bootstrap:

1. reads only the existing non-secret Teams app ID and tenant ID from OpenClaw configuration;
2. authenticates an Azure CLI session to the AOT tenant;
3. verifies the application registration is visible;
4. appends a new credential with `az ad app credential reset --append`;
5. writes the new value directly to a protected temporary file and then to `msteams.env`;
6. never prints the credential value;
7. leaves the existing OpenClaw credential intact.

Command:

```bash
clear
cd /home/al/projects/jason
bash infrastructure/jason-teams-gateway/bootstrap-azure-credential.sh
```

Expected terminal result:

```text
PASS: dedicated Jason Teams credential created and stored with mode 0600
PASS: existing OpenClaw Teams credential remains intact
CREDENTIAL_BOOTSTRAP_STATUS=PASS
```

Azure authority requirement: use an identity permitted to manage the application registration, such as an application owner or an appropriate Entra application-administration role. Global Administrator is not inherently required.

Do not re-run this bootstrap merely because the gateway is redeployed; doing so would create unnecessary additional credentials.

## 5. Isolated pilot

Before any production port cutover, prove the direct gateway independently:

```bash
clear
cd /home/al/projects/jason
bash infrastructure/jason-teams-gateway/deploy-pilot.sh
```

Expected result:

```text
{"status":"ok","service":"jason-teams-gateway","runtime":"http://jason-runtime:8080/v1/openclaw/teams/conversation"}
PILOT_STATUS=PASS
```

The pilot normally publishes only:

`127.0.0.1:3979 -> container 3979`

It must not modify the public Microsoft endpoint or take host port 3978 from OpenClaw.

Stop if the pilot is not healthy. Do not continue to production cutover to “see if it works.”

## 6. Production cutover

The governed production entry point is:

```bash
clear
cd /home/al/projects/jason
bash infrastructure/jason-teams-gateway/cutover-production.sh
```

The script is designed to:

1. require the direct gateway credential and governed ingress signing identity;
2. require a running isolated pilot;
3. derive the OpenClaw Compose project/service/workdir from Docker labels;
4. inspect actual Docker runtime port bindings;
5. reconstruct the OpenClaw `ports:` declaration while removing only host port `3978`;
6. preserve OpenClaw's other published ports;
7. validate the modified Compose configuration before mutation;
8. back up the original Compose file;
9. recreate OpenClaw without host port 3978;
10. verify OpenClaw remains running;
11. start `jason-teams-gateway` on host port 3978;
12. verify gateway health and port ownership;
13. persist rollback state; and
14. remove the isolated pilot only after production success.

Successful completion must end with:

```text
CUTOVER_STATUS=PASS
READY_FOR_TEAMS_LIVE_TEST=1
```

Do not interpret a successful Docker build alone as a successful cutover.

## 7. Post-cutover verification

### Service/port verification

```bash
clear

docker ps \
  --filter name=jason-teams-gateway \
  --filter name=jason-runtime \
  --filter name=openclaw-openclaw-gateway-1 \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Expected topology:

```text
jason-teams-gateway           Up ...             0.0.0.0:3978->3979/tcp
openclaw-openclaw-gateway-1   Up ... (healthy)   0.0.0.0:18789-18790->18789-18790/tcp, [::]:18789-18790->18789-18790/tcp
jason-runtime                 Up ... (healthy)   8080/tcp
```

### Direct gateway completion evidence

```bash
clear

docker logs --since 10m jason-teams-gateway 2>&1 \
  | grep -E 'jason_teams_gateway_started|jason_teams_turn_completed|jason_teams_turn_failed' \
  | tail -n 30
```

A successful real turn should include:

```text
{"event":"jason_teams_turn_completed","status":"completed","httpStatus":200,...}
```

### OpenClaw bypass evidence

```bash
clear

docker logs --since 10m openclaw-openclaw-gateway-1 2>&1 \
  | grep -E 'dispatching to agent|plugin-binding|msteams' \
  | tail -n 30 || true
```

For a direct-gateway Teams turn, do not expect a corresponding OpenClaw `dispatching to agent` event.

An internal `[msteams] starting provider (port 3978)` startup message alone is not evidence of external ownership.

## 8. Standard live proof request

For the existing production regression endpoint, the known read-only proof request is:

`Hey Jason, can you tell me who was last on AOT-50282 and if anything is wrong with it right now?`

The 2026-08-15 proof returned:

- last logged-in user `AzureAD\AlDavis`;
- one moderate `Unhealthy` alert;
- added users `CodexSandboxOffline` and `CodexSandboxOnline`;
- evidence source `datto_rmm`.

Use this as a regression reference only when the request remains authorized and the provider data is expected to be available. Do not assume those endpoint facts are perpetually current.

## 9. Rollback

Rollback command:

```bash
clear
cd /home/al/projects/jason
bash infrastructure/jason-teams-gateway/rollback-production.sh
```

The rollback state file is:

`/opt/jason/services/jason-teams-gateway/cutover-state.env`

Rollback must:

1. remove the direct production gateway;
2. restore the saved OpenClaw Compose file;
3. recreate the OpenClaw service;
4. verify OpenClaw is running; and
5. verify OpenClaw again publishes host port 3978.

A process restart without restored port ownership is not a successful rollback.

## 10. Stop conditions

Stop and do not continue mutation when any of the following occurs:

- dedicated gateway credential file is missing or improperly protected;
- the governed ingress signing key is missing;
- `jason-runtime` is not healthy;
- the isolated pilot does not pass;
- actual OpenClaw runtime port bindings cannot be resolved safely;
- modified Compose fails validation;
- OpenClaw does not remain running after releasing host port 3978;
- direct gateway health fails;
- direct gateway does not own host port 3978 after cutover;
- a live Teams request produces competing OpenClaw/model output;
- the direct gateway reports fail-closed errors that are not understood.

Do not compensate with a model prompt, private OpenClaw bundle patch, or provider bypass.

## 11. Failure classification

| Symptom | Likely class | Response |
|---|---|---|
| Gateway fails before health with missing Microsoft identity | credential/configuration | verify protected `msteams.env`; do not print it |
| Microsoft Agents SDK says client ID missing | gateway auth construction | use explicit SDK auth/adapter configuration; do not rely on ambient variable names |
| Azure bootstrap cannot modify app | identity/authority | use an authorized application owner/admin; do not extract the existing OpenClaw secret |
| Pilot healthy but live Teams still reaches OpenClaw | edge/port ownership | verify host port 3978 and relay destination; rollback if ownership is ambiguous |
| OpenClaw logs model dispatch for the same live turn | exclusive-ingress failure | rollback and investigate topology; do not add another hook |
| Gateway receives request but runtime call fails | Jason runtime/governed ingress | preserve fail-closed behavior and inspect runtime/audit evidence |
| Teams receives acknowledgement but no final result | runtime/provider/return path | inspect `jason_teams_turn_failed_closed` and Jason audit; do not allow OpenClaw to answer instead |
| Public unauthenticated probe receives 401 | protected application reached | expected for authenticated Bot Framework endpoint; not by itself an outage |

## 12. Outbound/proactive Teams messaging remains separate

ADR-009 supersedes OpenClaw only for **ordinary inbound Teams ingress**.

The existing proactive/outbound capability may still use OpenClaw and Microsoft Graph bootstrap behavior documented under ADR-005/ADR-007 and the approval messaging runbooks. Do not disable OpenClaw's Teams provider until the outbound/proactive dependency has been reviewed and either preserved through another supported path or deliberately retired.

The historical proactive bootstrap facts remain:

- organization catalog app ID: `1b24025a-201f-439d-a4ef-e308c7f3d853`;
- Graph installation permission behavior required `TeamsAppInstallation.ReadWriteForUser.All` during proof;
- proactive app installation is a governed auditable side effect;
- agents never call Graph or OpenClaw directly.

Inbound and outbound transport topology must not be conflated merely because they use the same Teams application identity.

## 13. Security and hardening follow-up

The routing workstream is production-proven. Remaining hardening includes:

- migrate the direct gateway credential from the mode-0600 host file to Jason's governed secret-provider/federated identity model;
- review whether the dormant OpenClaw inbound `msteams` listener can be disabled without affecting approved outbound/proactive functions;
- retain least-privilege Microsoft application permissions and periodically review whether broader installation permissions can be reduced;
- keep the direct gateway non-intelligent and free of provider/business-authority logic;
- maintain System Registry topology and verification records whenever host-port/service ownership changes;
- rotate/revoke obsolete credentials when the migration state is retired;
- preserve the rollback path after future OpenClaw Compose changes.

## 14. Documentation/evidence owners

- Architecture decision: `docs/decisions/ADR-009-Direct-Microsoft-Teams-Ingress.md`
- Provider-neutral conversational routing: `docs/decisions/ADR-006-Governed-Conversational-Interface-Routing.md`
- Proactive/outbound Teams decision: `docs/decisions/ADR-007-Teams-Proactive-Messaging.md`
- Production cutover proof: `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`
- Current operational topology: `implementation/kernel/system_registry/`
- Generated operational view: `docs/operations/System-Registry-Current-Operational-State.md`
- Current resume point: `docs/control/CURRENT.md`

If these sources conflict, the Constitution/governing ADRs and System Registry/current host evidence take precedence over this operational runbook.
