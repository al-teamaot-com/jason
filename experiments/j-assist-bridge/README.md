# J-Assist governed session bridge — preproduction only

This module establishes a **server-side authority contract** for a future
technician-initiated bridge. It deliberately does **not** connect the Chrome
extension or enable a network listener. It is not production-enabled.

## Existing constraints verified

The Jason runtime HTTP endpoint currently accepts signed Teams conversations
and does not attest Chrome technicians or Datto Web Remote sessions. Reusing
that endpoint for extension screenshots would not meet AOT's governance.

## Required adapter contract

1. Server-side trusted identity adapter returns the authenticated AOT technician
   and organization tenant ID. **Never accept these from browser JSON.**
2. Server-side provider-backed authorization verifies the technician's native
   Datto RMM access to the exact device immediately before each request.
3. Start requires explicit user consent, returns a short-lived session-bound
   credential, and binds one technician, tenant, and Datto device.
4. Stop, expiration, permission loss and changed session immediately revoke access.
5. Only lifecycle metadata is accepted in this initial module. **No screenshot,
   raw PowerShell output, browser token or page content may be transmitted yet.**
6. Before content enablement, implement and independently accept private network
   TLS ingress, authentication, authenticated origin binding, screenshot/text
   redaction, data minimization, audit retention, rate limits and proof that
   another technician cannot read the session.
7. No command execution or endpoint mutation is part of J-Assist v1.

## Validation

Run: `python3 -m unittest discover -s experiments/j-assist-bridge/tests -v`

Unit tests use synthetic trusted identities and synthetic provider authorizers.
They are not live provider-backed acceptance or proof of real identity binding.
The browser extension remains entirely local-preview only.

## JKD-001 integration (preproduction)

`jkd_authority.make_jkd_datto_authorizer` calls Jason's existing
`IdentityAuthorityService.evaluate` on every session request and requires an
explicit `j_assist.session.observe` OBSERVE grant, plus a separately injected
provider-backed **native Datto device-access** check. Neither an AOT standing
read grant nor a browser-declared identity is sufficient. Denials and revocations
fail closed. No new grant, new role or token is provisioned by this code.

The native Datto role/permission query and Microsoft identity attestation are
still missing production adapters. Tests use real JKD service objects but
synthetic identities and provider permissions. These tests do not prove an
actual Datto technician's access.

## Shared-session architecture reconciliation (2026-11-06)

The existing draft shared-session foundation is tracked at PR #1465,
branch `feature/shared-session-foundation-20261015` and documented in
`docs/architecture/Shared-Governed-Interactive-Sessions.md` on that
branch. J-Assist must integrate with the shared, provider-neutral
session lifecycle, events and audit model; the `SessionGate` here is
an **isolated security boundary prototype**, not a second competing
production session registry. Production implementation should adapt
the already-reviewed foundation rather than promoting both ledgers
or issuing independent grants.

Datto Web Remote is browser/WebRTC driven. No supported third-party API
for joining or controlling its live terminal was established in the
existing foundation. Graphical **visible-tab snapshots** are different
from programmable WebRTC control and do not imply the latter is available.

### Next acceptance milestones

1. Bring the session authority into the provider-neutral shared-session
   architecture, preserving its durable evidence, revocation and policy
   boundaries; reject unreviewed overlapping contracts.
2. Implement trusted Microsoft/AOT human identity binding and verify each
   technician's native Datto role, tenant and exact device access.
3. Implement a reviewed TLS-protected, authenticated, server-side session
   ingress with explicit consent and stop; deny traffic before those checks.
4. Introduce bounded *opt-in* single-frame sharing and redact/suppress
   sensitive material. Full-screen continuous streaming must remain off
   until explicit handling, review, retention and audit are accepted.
5. Pass two-technician and cross-client isolation tests, race/replay
   testing, production health requirements and explicit release authority.

The current deliverables prove only local browser capture and offline
contract tests, not technician-to-Jason data delivery or vision inference.

## Synthetic request/response proof — development only, 2026-11-06

`synthetic_probe.py` exercises an in-process **request -> SessionGate
authorization -> response** loop with an explicitly synthetic marker. It uses
the existing exact-identity/tenant/device/credential gate, verifies native
provider access on every request, and rejects content, malformed envelopes,
replayed IDs, wrong device, cross-technician access, revocation and expiry.
Responses deliberately state that no screen was analyzed. This is not
a browser-connected transport, screenshot intake, model output or production
integration.

**Next engineering task:** Independently attest AOT human identities and
Datto native per-device authorization; connect a reviewed TLS/protected
ingress to the provider-neutral shared-session service (PR #1465), with
consent, explicit frame review, content DLP/redaction, durable audit and
replay/rate limits before allowing actual screenshots. Keep ChatGPT
subscription integration separate from transport and do not silently
enable paid OpenAI API calls.

## ChatGPT subscription-first read-only app adapter (2026-11-06)

`chatgpt_session_tool.py` implements a **preproduction in-process read
contract** intended for a future **custom ChatGPT Business MCP app**. Only
safe synthetic receipt metadata is returned; a model never receives a
session credential, screenshot, login token, API key or raw terminal output.
The trusted authenticated AOT technician identity is supplied by the MCP
server adapter (never model JSON), and a server-owned credential lookup
revalidates the exact device, tenant and current native Datto access
through `SessionGate.authorize_read` every time. Bad identities, missing
credentials, wrong device, expired sessions, permissions revoked and
non-synthetic content all fail closed. The result explicitly flags
`screenshot_analyzed=false`, `live_transport_connected=false`, and
`inference_billing=none`.

**Cost policy:** ChatGPT handles reasoning when the future tool is
invoked **within a technician's eligible AOT ChatGPT workspace**.
Jason's MCP/tool backend only returns verified governed data. No OpenAI
API key, Responses endpoint, model call, subscription token, proxy billing
or hidden API fallback is created in this implementation. A separate
Chrome-sidebar inference experience is NOT yet subscription-eligible:
OpenAI Sign in with ChatGPT external app plan usage is currently
restricted by participation, plan and workspace eligibility. Do not
claim ChatGPT Business subscriptions cover our custom sidebar by
default.

Official capability references (verified November 6, 2026):
- https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt
- https://developers.openai.com/siwc/quickstart
- https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform

**Limitations / next work:** This module is *not registered* in the live
Jason MCP tool registry, and there is no real browser/backend data
delivery, SSO, native Datto permission production adapter, durable
shared-session record, accepted screenshot DLP, production promotion or
tested AOT ChatGPT workspace deployment. Integrate with shared-session
PR #1465 and verified server identity before exposing the tool.


## Development-only loopback HTTP contract — 2026-11-06

`loopback_transport.py` exercises a **real HTTP request and response over
127.0.0.1** using a **synthetic marker** and an injected trusted-authentication
callback. It uses the established SessionGate to check explicit consent,
session credentials, exact device binding, tenant, native-permission callback,
revocation and expiry. The loopback listener allocates an ephemeral port;
it has no external network exposure or default start-up entry point.

This is a **transport prototype, not a deployed authenticated browser
integration**. Unit tests inject a mock identity credential and mock native
Datto permission. The real Chrome extension does **not** connect to this
loopback endpoint. No screenshots, credentials from live Datto tabs, raw
terminal content, OpenAI API calls, ChatGPT plan-sharing, or ticket writes
are accepted. The HTTP response explicitly says the screen was not analyzed.

Before any external-facing service: integrate independently verified AOT
technician SSO, native Datto authorization, TLS-protected front door and
origin protections, audited durable provider-neutral sessions (shared-session
PR #1465), content security/redaction and governed retention. The intended
subscription-backed ChatGPT interface remains a custom AOT ChatGPT Business
MCP app; no separate billable model API fallback is permitted.

## Datto native technician authorization contract (development)

`datto_technician_authority.py` requires *fresh Datto-provider-attested
evidence* tied to the individual AOT technician and the selected device,
including the current active Datto security level, site/device visibility,
and Web Remote permission. It does not infer permission from Jason's
shared service credential, a user's Entra identity alone, or a Chrome
tab URL. It rejects permission removal, stale evidence, wrong tenant/
device/technician, missing security-level information, and adapter failure.

Only a test-injected evidence adapter exists. No Datto per-technician
production evidence source has yet been verified, so this module is
**not sufficient to enable a real screenshot upload or production rollout**.
The existing v0.1.6 Chrome preview remains unchanged. The extension
will need a separate versioned update for an opt-in authenticated
`Send to Jason` interaction after the server security gate is accepted.

## Existing Jason MCP Entra technician identity adapter (2026-11-06)

`mcp_identity_adapter.py` accepts only the server-verified four-tuple
returned by the existing `jason_mcp.server._authenticated_identity()`:
`(jason_principal_id, organization_id, "entra-oauth-bearer", client_id)`.
That upstream function performs Microsoft access-token validation, Entra
tenant/object verification, active identity binding and Jason identity
validation. A browser, a ChatGPT tool invocation or arbitrary JSON must
never supply this tuple. Missing authentication and non-Microsoft assurance
fail closed; a changed technician/tenant cannot read the previously opened
session even if the session reference is known. The model receives only
bounded synthetic test metadata, not the token or screenshot.

This is a preproduction adapter contract and **not an active tool
registration** in Jason's production MCP service. The live Datto
per-technician evidence source, durable shared session state, reviewed TLS
ingress and actual ChatGPT Business workspace integration remain required
before any screen content is accepted or an extension Send-to-Jason control
is enabled. No paid API inference is used.
