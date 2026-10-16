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
