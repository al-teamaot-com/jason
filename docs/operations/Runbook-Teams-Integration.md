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

### Company-wide proactive staff bootstrap

For any governed proactive send to an AOT staff member, the direct Teams gateway must validate the target Entra object in the AOT tenant before Teams-side effects. The user must exist, be enabled, and have `userType=Member`; missing, disabled, or guest identities fail closed.

If the Jason organization-catalog app is not installed for the target user, the gateway uses its approved Microsoft Graph application identity to install exactly catalog app `1b24025a-201f-439d-a4ef-e308c7f3d853` in that user's personal scope, polls with bounded retries until the installation is visible, then creates/reuses the personal Jason Approval Bot conversation and sends the message. Repeated sends must reuse the existing installation/conversation rather than duplicate bootstrap work. Jason must never substitute `48:notes`, a different recipient, or send-as-owner when bot bootstrap fails.

### Owner notification routing and presentation

For proactive messages to the AOT owner, use only Jason's governed `communication.teams.message.send` capability through the direct Teams gateway / Jason Approval Bot conversation. Do not route owner notifications through generic Teams connector self-chat / Notes (`48:notes`) or substitute another chat when the governed target is available.

Presentation rules for operational summaries:

- use Adaptive Cards for multi-row/tabular content when supported;
- otherwise use one item per line with bullets or compact labels;
- avoid plain-text Markdown pipe tables because Teams can collapse them into a dense paragraph;
- separate exceptions/unresolved items into their own section; and
- verify post-send readback against the intended Jason bot conversation.

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


## Single-card delivery identity (October 24, 2026)

The existing proactive sender must send a card as one attachment-only message.
Do not combine top-level Activity.text with its Adaptive Card attachment: Teams
can split that payload into two visible messages and return an empty HTTP 202,
leaving no provider card ID. Microsoft documents that behavior in
https://github.com/microsoft/botframework-sdk/issues/6155.

The shared buildProactiveActivity helper now puts the notification text into
Activity.summary and leaves the actual card, actions, challenge and payload
unchanged. The card's own body contains the visible review details. Summary
rendering varies by Teams client; it is not evidence of a displayed notification.
Text-only messages remain unchanged. Both saved-conversation and first-contact
proactive paths use this one helper.

An actual provider message ID remains distinct from a synthetic accepted receipt.
The patch does not fabricate delivery confirmation, grant approval, change
identity verification, or clear an unresolved delivery block. Verify the deployed
gateway source, then read the actual newly sent card and signed response before
marking end-to-end acceptance. Existing uncertain requests must not be blindly
resent.

The shared deploy_live_container.py supports --health-runtime node for this
existing Node gateway. Python stays the default for runtime/MCP. Both modes
require HTTP 200 with a bounded timeout and use the same failure rollback.
For an exact-source gateway image replacement, preserve the current container
settings, signing-key/token mounts, network, public port and durable decision
store. Use the shared preflight and rollback mechanism; do not rerun the
historical initial OpenClaw port cutover to update an already direct gateway.


### Non-root image source permissions (2026-10-24)

The release builder can check out source with mode 0600. Docker COPY preserves
that mode while assigning root ownership; the existing USER node cannot read
the application. Normalize only packaged non-secret /app JavaScript modules
and package.json to mode 0644 and /app to 0755 at image build time. Keep
USER node and all mounted credential permissions unchanged. Before rollout,
run an import/syntax smoke test as the image's default user with no network
and a read-only root filesystem. Never compensate by running the bot as root.

## Expiring internal-note functional pilot (October 24, 2026)

The first executing general-plan pilot is restricted to the existing AOT
`jason-autonomy-worker`, approved by `person-al`, and two exact internal-note
payloads on the previously verified XYZ Test Company ticket 8870. It neither
adds an identity/grant nor enables reboot, procurement, financial or client
communication capabilities. `config/universal-approval-pilot-v1.json` pins the
complete policy file hash. Its two request-payload hashes include ticket ID,
internal-only publish value, note type, title and description. The campaign and
policy expire on October 27 at 04:00 UTC. Live grants remain independently
required; configuration cannot manufacture authority.

An immutable deployed runtime carrying a valid source revision can select this
explicit bundled pilot when the operator has not selected another universal
approval mode. An explicit environment `off` always wins, including native
isolated preproduction. Local development without a source revision stays off.
A later rollback without this source manifest restores the previous off state.
Expiry stops new issuance and existing-plan continuation, without stopping other
runtime functions or granting broader approval authority.

The existing UniversalPlanIssuer now accepts a trusted in-process registered
workload requester with explicit, exact-intent policy. It is not an HTTP route.
The human requester route retains its real Teams identity checks. Both routes
use the same persisted requests, scoped policy, actual signed Teams decision,
nonce/challenge, immutable plan, current JKD grant evaluation, Central
Orchestrator and exactly-once execution ledger. A service remains a service in
its execution context; a human approving it is not impersonated as the requester.

After separately reviewed source deployment, run inside the existing runtime:
`python -m jason_runtime.universal_approval_pilot deny`. A genuine human DENY
must precede the `approve` case. The `approve` command then requests exactly one
internal test note. Commands never execute the provider or fabricate a vote;
normal signed Teams callbacks and the normal continuation worker own execution.
Deterministic case IDs preserve pending, failed and ambiguous requests without
blind resend. `status` reports the durable progress only. No periodic pilot
issuer, additional bot, signing key, authority database or external endpoint is
introduced.

Acceptance is separate from CI: independently read the target ticket notes,
confirm zero DENY-case notes and exactly one APPROVE-case note, verify the real
Teams card ID and signed decision, and verify a duplicate response does not
create another note. A queued callback is not execution success. Record the
actual request/execution/receipt IDs and provider readback before declaring the
pilot functional. Broader universal rollout remains separate.

### Known deployment timing dependency

The usage-attribution Prometheus job scrapes every two minutes. Host exporter
restart can therefore leave a real Grafana dependency absent beyond the former
three short retries. Host reconciliation now allows one bounded 150-second
observation window, running the actual checker and requiring its success. It
does not skip file/datasource/metric checks or clear a failed unit manually. The
existing 360-second host budget remains unchanged; persistent failure rolls back.

The source-pinned pilot default is runtime-only. The MCP application embeds the
same composition but has its own registered MCP resource URL; its unset approval
mode remains OFF. It does not instantiate the pilot just because it shares a
source revision. Explicit operator-selected modes retain their existing semantics.
