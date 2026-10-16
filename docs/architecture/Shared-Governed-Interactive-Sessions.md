# Shared Governed Interactive Sessions — initial foundation

**State:** isolated source-only prototype; not production-enabled; no command transport, browser extension, or runtime registration is supplied. Related: #1455.

## Purpose and boundaries

The shared-session experience is provider-neutral: technicians should be able to observe, question, pause, and learn from Jason's authorized investigation on Datto RMM Web Remote, SSH to a managed HP switch, WinRM, or other future transports. Adapters describe capabilities; they do not issue authorization or execute without the Central Orchestrator.

Session interfaces (browser extension, companion panel, Teams, CLI) -> normalized intent -> identity / company / tenant / device / ticket binding -> existing governance and deterministic execution policy -> reviewed transport adapter -> event transcript / verification. The technician can request interruption, but cancellation must be enforced by the server and transport.

## Runtime-reloadable policy

`config/shared-sessions/policy.example.json` is a deny-all example. The admission prototype loads configuration afresh on *every* decision: a file change is effective on the next request without rebuilding code. Operators must distribute configuration through an access-controlled, audited configuration store in a later phase; only an authorized Technology Steward may edit it. Runtime reload is **not** an authorization override: every action still requires validated external identity, tenant/client/device/ticket binding, an explicitly approved transport, a live governed grant, and for sensitive/mutating commands their separate rights and approvals. Approval may never be supplied by an untrusted browser client. Config enablement cannot activate an unreviewed transport or expand core constitutional rules.

## Adapter contract (future work)

Adapter must expose `transport_id`, `target_kind`, `supported_session_modes`, `supports_live_input`, `supports_output_stream`, `supports_cancel`, `execution_identity`, `max_output_bytes`, `session_expiry`, `connection_health` and evidence/verification methods. Never infer that a Datto browser URL transfers WebRTC authority; never scrape authentication tokens. SSH adapters require separately approved device-bound credentials, host-key verification, command authorization against target OS/device type, and per-command verification. A PowerShell classifier is **not** suitable to classify HP Comware/ProCurve CLI.

## Future session events

Define append-only `session_opened`, `command_proposed`, `decision_recorded`, `command_started`, `output_observed`, `command_finished`, `session_paused`, `session_revoked`, `session_closed`. Preserve event ordering, redaction, attribution, tenant scope, immutable correlation, and technician-readable explanations. Browser disconnect must revoke live-session work, not silently switch to unattended execution.

## Phases

0. Validate supported Datto Web Remote transport or design the companion alternative; determine supported SSH device types and privilege boundaries.
1. Produce governed session API, adapter registry, server-side grants/expiration/revocation, signed event stream and test fixtures; read-only controlled pilot.
2. Add technician UI and synchronized command/output/reasoning; interrupt/resume/replay; test negative permission boundaries.
3. Add approved mutating path with per-action approvals/readback, reviewed ticket notes and learning candidates.

## Production safety

This prototype deliberately makes **no** service changes, host connections, endpoint commands, vendor API calls, credential changes, or deployments. The existing `endpoint.powershell.read` capability remains dormant. Do not enable the example config in production. A successful session admission result is not authorization to execute a command.

## Non-executing event ledger prototype (engineering checkpoint)

`implementation/shared_sessions/events.py` introduces an isolated, in-memory,
append-only session event model. It rejects unknown event kinds, requires a
session-open event, segregates histories by tenant and session identifier,
orders events with a per-session sequence number, links each event to the
preceding SHA-256 digest, and prohibits events after revocation or closure.
Its unit tests demonstrate these admission and event-lifecycle boundaries.
**This is not production audit evidence:** the ledger is not durable,
cryptographically authenticated, signed, redacted, or wired to any transport.
The next implementation stage must use a transactional durable event store,
server-controlled grants, explicit revocation/cancellation, output redaction,
retention, tenant-authorized reads and independently tested transport adapters.
No command execution or Teams approval integration is introduced by this stage.

## Non-executing adapter catalog prototype

`implementation/shared_sessions/adapters.py` defines explicit transport capability
metadata (target type, supported modes, cancel/stream flags, execution identity,
output bounds and expiry). No transport is registered by default and the registry
has no execute/connect method. Registry entries do not prove support, approve a
transport, or grant any execution authority. Live adapter implementations,
server-side capability grants, transport-specific command classifiers, target
identity verification and integration tests remain outside this prototype.

## Non-executing lifecycle controller

`implementation/shared_sessions/lifecycle.py` is an isolated lifecycle test
fixture for session open, pause, revoke and close. It rejects cross-tenant and
wrong-technician access and disallows reopening terminal sessions. There is
no resume operation until actual reauthentication, identity verification and
new server-side grants exist. This in-memory controller is not a production
session service, and does not enforce cancellation at any external transport.

## Vendor-supported transport feasibility (2026-10-16)

Official Datto Web Remote documentation says technician browser PowerShell
uses WebRTC and a Windows Console session running as SYSTEM. PowerShell support
requires Windows 10 1809+ or Windows Server 2019+; Web Remote's private terminal
runs Windows PowerShell at `C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe`,
not PowerShell 7 (`pwsh`). Its browser connection ends on tab closure, and a
reconnect window applies to brief interruptions. No documented third-party
API for injecting commands into that live WebRTC browser PowerShell channel
was established during this investigation. Therefore **Datto Web Remote is
NOT a demonstrated programmable adapter**. Never scrape browser auth,
intercept WebRTC private messages or silently impersonate a technician.

Official Datto RMM APIv2 documentation does describe OAuth-secured component
Quick Jobs with component-level permissions, plus job status retrieval. This
is a **separate, non-interactive job execution model**, not a live Web Remote
PowerShell session. Datto's integration whitepaper likewise recommends
noninteractive components for scripts. An approved governed job adapter may be
a pragmatic read-only pilot, but must not be mislabeled Web Remote live input,
and must preserve existing owner/technician approval, target verification,
execution, recheck and audit boundaries.

Sources (vendor):
- https://rmm.datto.com/help/en/Content/3NEWUI/WebRemote/WebRemote.htm
- https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm
- https://rmm.datto.com/help/Integrations/DattoRMMIntegrationsWhitepaper.pdf

Decision gate: Validate a supported vendor-authorized Web Remote terminal API
or design an explicitly approved endpoint companion/proxy for interactive
PowerShell; keep interactive transport disabled until one option has passed
technical, vendor-terms, authorization and security review. Keep the approved
component/job path separate from live streaming. No production approval is
implied by this feasibility note.

## Non-executing signed-grant test fixture

`implementation/shared_sessions/grants.py` demonstrates SHA-256 command digest
binding, exact tenant/client/device/technician/ticket/transport matching,
HMAC signature validation, expiration, explicit revocation and atomic single-use
consumption **in one test process**. The issuer function is explicitly named
`issue_for_test` and is NEVER production authority. It lacks durable replay
persistence, authenticated identity from Microsoft Teams, deployment key
management, production event attribution, revocation distribution and server
execution integration. All those must be implemented independently before any
execution action. Passing its tests proves only local cryptographic and
state-machine behavior; it does not satisfy the Owner's Teams approval gate.

## Offline end-to-end acceptance simulation

`implementation/shared_sessions/simulation.py` composes the local lifecycle,
policy, grant verifier and event ledger to demonstrate a proposed command,
policy decision and exact-command single-use grant validation **without ever
executing**. It never stores raw command text in events; it records the digest
only. Its regression tests check simulated allowance, deny under disabled policy,
wrong technician, paused sessions, changed command, and grant replay. The
`SimulationResult.executed` field is permanently false. It is NOT a user-facing
terminal, a real executor, a trusted classification service, a Teams approval
system, nor an endpoint transport. The separate human authorization and release
gates remain unchanged.

## SQLite durable event prototype

`implementation/shared_sessions/durable_events.py` adds an isolated SQLite
append-only prototype with transactional per-session sequence allocation,
restart-persistent event history, tenant-scoped retrieval and SHA-256 chain
verification. Its acceptance tests demonstrate restart, tenant separation,
terminal revocation and tamper detection. This is **not** production audit:
there is no centralized authenticated append service, immutable external/WORM
anchor, cryptographic signature, encryption policy, tenant-aware access-control
boundary, retention, or backup/restore certification. It is not connected to
a live command executor or Teams approvals. Production integration must select
an audited shared store and demonstrate concurrency, crash recovery, redaction,
access isolation, secret handling and replay protection under hostile inputs.

## Owner-approved companion path for Claw2-pc (2026-10-16)

Owner authorized a governed Jason Companion on **Claw2-pc**, explicitly as a
nonproduction interactive PowerShell evaluation platform instead of relying
on an undocumented Datto Web Remote WebRTC injection API. Keep the shared
session contracts transport-neutral. Before any agent installation or device
command, identify the actual Datto device UID, Windows version, companion
installation identity, network path and supported PowerShell edition. Bind
the device, tenant, client and technician to separate audited authority records.

`companion_contract.py` is an **inert** session handshake contract with strict
identity matching, per-device fingerprint, authenticated binding attestations,
nonce, expiration <= 5 minutes and explicit engineering-only scope. Its
booleans are inputs to local boundary tests, **not cryptographic proofs**.
No agent or executable process is supplied by this change.

Engineering acceptance requires a reviewed authenticated mutual channel,
device enrollment and revocation, per-command digest/approval, isolated
execution identity, streamed output with redaction and hard limits, transport
cancellation, crash/reconnect handling, reliable durable audit and independent
Teams approve/deny expiry/replay enforcement. Start with read-only commands on
Claw2-pc in a disposable test state after authority verification. No
production rollout or automatic promotion; retain explicit Owner gate.

## Companion wire contract (2026-10-16)

`implementation/shared_sessions/companion_protocol.py` introduces a strict,
versioned **nonexecuting** frame schema for hello/proposal/output/completion/
cancel/revoke/heartbeat events. The envelope validates exact identifiers,
size bounds, sequence numbers and command SHA-256 digest; it explicitly rejects
raw commands and secrets in protocol payloads. A local test-only replay guard
checks authenticated tenant/device binding and duplicate or out-of-order frames.
This is not a network listener, cryptographic channel, credential service or
execution implementation. Production must implement mutual channel identity,
structured command authorization on a separate protected channel, persistent
shared nonce/sequence store, backpressure, cancellation, telemetry and external
security testing. The approved Claw2-PC Datto identity was observed through
governed read as `13eda165-08e0-ec79-026a-985b37e2eb9e` (site Atlantic Office
Machines; online at inspection); enrollment must reverify it before use.

## Claw2 read-only PowerShell local probe engine (unactivated)

`command_catalog.py` contains a finite, parameterless list of reviewed
PowerShell diagnostic commands, digest-bound to proposed action IDs.
`companion_local_probe.py` provides an **opt-in, local-only engineering test
engine** with a source-level Claw2-PC hostname and Datto UID constraint,
explicit in-process grant verifier, fixed `/usr/bin/pwsh` executable, no shell
interpolation, timeout and bounded captured output. No default execution,
command-line entrypoint, network listener, installer or production connection
exists. Tests use a mocked subprocess and must **not** be cited as proof that
PowerShell runs on Claw2-PC. This initial probe is not a general interactive
terminal and must never run on a production device. Before even a controlled
live diagnostic: independently confirm the bound device UID/OS, verify `pwsh`
is installed, enroll a reviewed transport, use server-authenticated grants
backed by durable replay state, prove audit/output protections and apply the
normal exact per-run Datto component approval. Do not promote this local test
fixture as a production companion.
