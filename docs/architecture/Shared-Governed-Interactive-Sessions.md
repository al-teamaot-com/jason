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
