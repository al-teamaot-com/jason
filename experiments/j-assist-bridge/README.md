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

## Active Datto Web Remote vs. PowerShell rights (2026-11-06)

Datto's current security-level documentation states the **active** security
level controls device visibility and remote tools, and a technician can
switch levels. The Web Remote documentation explicitly requires an
independent PowerShell toggle for Web Remote PowerShell. The experimental
`DattoWebRemoteAuthorizer.can_access(..., surface="powershell")` now
requires `powershell_enabled=True` in addition to Web Remote permission;
`surface="webremote"` checks general Web Remote access. Unsupported
surfaces fail closed. Actual evidence must originate with Datto for the
**individual** technician; a shared API token's API security level is not
equivalent to the technician's active UI security level. No provider API
was confirmed for obtaining that active signed-in level across technicians;
this is an external live-integration acceptance gap, not grounds for
trusting Chrome-supplied assertions.

References:
- https://rmm.datto.com/help/en/Content/3NEWUI/Setup/SecurityLevels.htm
- https://rmm.datto.com/help/en/Content/3NEWUI/WebRemote/WebRemote.htm
- https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm

For ChatGPT subscription use, eligible AOT Business workspace
admins/owners can install a custom MCP server in **Plugins**, with
public HTTPS endpoint or Secure MCP Tunnel and verified OAuth. The
Chrome extension itself is not a substitute for a subscription-backed
ChatGPT client. Reference:
https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

## J-Assist / shared-session combined integration branch — 2026-11-06

The dedicated isolated integration branch merges draft J-Assist PR #2349
with draft shared-session PR #1465 **without a production merge**.
`shared_session_adapter.py` links an explicitly authorized J-Assist
`SessionGate` to Jason's existing `SessionLifecycle`, using its
`SqliteSessionEventLedger` for ordered metadata-only opened/closed
events. The adapter requires a trusted technician, exact Datto device,
ticket reference, and affirmative consent; inspect revalidates the
session credential and current provider authorization; close terminates
both models. Tests prove cross-technician denial, permission revocation,
expiration and a verifiable shared hash chain.

**Preproduction only:** `SessionLifecycle` itself is still
process-memory-backed and the SQLite event chain is not signed,
multi-host durable governance evidence. Restart recovery and transactional
cross-service revocation must be engineered and accepted before
production. No real screenshot upload, live SSO issuance, Datto signed-in
security-level provider API, ChatGPT workspace connection or model
analysis was enabled.

## One-click screenshot intake: fail-closed preproduction component (2026-11-06)

`screen_evidence_intake.py` implements an independent **in-memory**
preproduction screenshot evidence receipt contract. The intended future
Send-to-Jason HTTP endpoint must supply a verified server-side principal
and SessionGate credential. This contract enforces exact device/session
binding, fresh native authorization on receipt and retrieval, bounded image
bytes (1 MiB), SHA-256 integrity, one-use request nonce, image magic checks,
a mandatory external content-review callback, a second authorization check
*after* review, a server-issued receipt and 120-second image expiration.
The returned receipt explicitly says `analyzed_by_model: false`.
Missing/rejected DLP/review denies receipt; no default allow-all exists.
Eight new Python tests cover synthetic accepted evidence, cross-tenant/
technician/device isolation, replay, permission loss, review failures,
size/hash errors and expiry.

**Do not expose this class through a production or remote endpoint.**
Tests use synthetic data and deliberately lightweight image-header
recognition, NOT full image parsing or malware scanning. In-memory images
and nonces are NOT durable, encrypted-at-rest, crash recoverable or safe
for multi-worker production. The class is not wired into the Chrome
extension, remote HTTPS ingress, or ChatGPT MCP image retrieval.
Provider-backed technician access, a real data-loss-prevention/redaction
engine, strict CORS/origin, OAuth, audit/retention and malicious-image
handling remain acceptance gates. This step does not send or analyze any
client image.

## Loopback-only HTTP screenshot receipt acceptance (2026-11-06)

The `/v1/test-image` route is present ONLY in the test loopback
server and only when an isolated test image-intake instance is injected.
It defaults to **404** without that instance. Four new real HTTP tests
exercise binary payload transfer, SHA-256 readback, session-device
authorization and opaque server receipt, missing bearer, wrong checksum,
wrong device, replay, revoked Datto callback, media-type rejection and
default route closure. The HTTP response labels itself
`production_ingress:false` and `analyzed_by_model:false`.

The tests use a synthetic image-header fixture and a deliberately injected
test reviewer. No live screenshot was transmitted. The server listens only
on `127.0.0.1`, with no remote port, public TLS termination, OAuth flow,
origin verification or persistent evidence store. It MUST NOT be used for
client content. The original one-click J-Assist button remains disabled
and has no fake success path. Required production work: verified browser
identity and Datto user permission, encrypted evidence persistence and
retention, independent content scanning/redaction, audited remote HTTPS
ingress, ChatGPT MCP image fetch under matching technician authority,
and actual technician acceptance.

## One-click send orchestration + MCP read-side contract (2026-11-06)

`experiments/chrome-datto-observer/send_once.js` is a new pure
background-action coordinator. It rejects an incomplete trusted
authentication/session/Datto-permission contract BEFORE capturing any
screen, then checks exact tab continuity, size and type, image hash,
receipt binding and a post-delivery tab recheck. The send reports success
only with a matching server-issued receipt. Nine tests cover fail-closed
capture, bad image, revoked tab and forged acknowledgements. This
coordinator is **not yet connected to a real Chrome OAuth/HTTPS sender**;
the v0.1.8 Send button stays disabled.

`chatgpt_image_tool.py` is an in-process, read-only connector contract
for a future registered Jason MCP image tool. It obtains the confidential
session credential server-side and revalidates the current technician,
Datto device, receipt and expiration before yielding base64 image
evidence with MIME type. It does not run or charge a model, does not
extract PowerShell text, and does not grant an unverified principal any
access. Four tests cover exact image bytes, authorization isolation,
revocation and missing credentials. This adapter is **not registered**
in the production Jason MCP service or in an AOT ChatGPT workspace.

**Release blockers remain:** verified browser-initiated Entra OAuth and
Datto active-user Web Remote permission, reviewed encrypted audit and
image storage, real image content scan/redaction, authorized HTTPS
ingress, cross-process lifecycle persistence, custom MCP registration
and genuine AOT ChatGPT Business acceptance. Do not enable live upload
or declare end-to-end success based on the synthetic tests.

## Browser-shaped JPEG receipt: server-held session authorization

The *loopback-only* `/v1/jassist/image` preproduction route exists
only when BOTH a test image intake service and a server-held session
credential resolver are explicitly injected. It defaults to HTTP 404
otherwise and rejects `X-JAssist-Session-Token` from the browser.
It handles JPEG (Chrome capture format) as well as PNG, obtains the
session credential privately from its injected resolver, rechecks
the underlying SessionGate and emits a receipt with `status:accepted`
and `production_ingress:false`. It is still HTTP on **127.0.0.1 only**
and does not authenticate real Entra tokens or attest active signed-in
Datto permissions. These are **test credentials and synthetic marker
envelopes**, not real screenshot parsing or DLP. Do NOT expose the route
outside the local test host or deploy the test reviewer.

## Dedicated JAssist.Send Entra acceptance boundary (2026-11-06)

New preproduction `entra_send_authority.py` accepts a signed Entra
access token ONLY after trusted RS256 signing-key verification against
AOT's existing Jason API audience, exact tenant and issuer, expected
new SPA application's `azp`, strict `scp=JAssist.Send`, temporal
claims and a server-side ACTIVE AOT Jason identity binding. It rejects
tokens with `Jason.Read`, cross-tenant/SPA use, revoked identity, JWKS
failure, invalid signatures and expired tokens. Seven Python tests
construct actual RS256 JWTs using synthetic ephemeral keys; none use
tenant credentials or live user tokens.

Existing `jason_mcp.server.EntraTokenVerifier` for ChatGPT
`Jason.Read` remains unmodified. No user impersonation, Datto scope
claim from the browser, or privileged API access is introduced. To
enable live pilot, the required AOT Entra `JAssist.Send` scope and
dedicated Chrome SPA app CLIENT ID must be admin-granted and the
approved SPA ID supplied to server configuration; this adapter is
currently unregistered and no new public HTTPS route exists.

## Signed-Entra-JWT loopback HTTP regression (2026-11-06)

The optional loopback browser-shaped image intake now accepts a
verified, realistic RS256 Entra JWT exceeding 512 characters and maps
its signed AOT claims through the active technician binding. A denied
authentication callback returns HTTP 401 rather than an unhandled 500.
The test then checks receipt hash, no bearer/session credential returned,
wrong client/scope rejection and revoked Datto callback. The server
holds Jason's internal session credential; browser never sends it.
`test_signed_entra_image_http.py` contains two additional tests.
All keys, tokens and JPEG markers in these tests are synthetic.
This does not establish live AOT Entra sign-in, real DLP or HTTPS ingress.

## Concurrent nonce and evidence-capacity hardening (2026-11-06)

The preproduction image intake is shared by a threaded HTTP loopback
test server. Its formerly unlocked nonce-set check admitted a race
between simultaneous requests: two uploads using the same session and
nonce could both pass while content review was in progress. The intake
now uses a lock, reserves a session/nonce BEFORE slow content review,
commits only once, and releases a pending nonce on DLP rejection,
expired/revoked authorization or any error. Nonces remain replay
protected through the maximum 300-second governed session lifetime.
Only 32 unexpired images (up to 1 MiB each) may remain in the in-memory
test service; at capacity it fails closed until cleanup. Retrieval and
pruning are lock protected. Three synthetic multithreaded/capacity
regressions are included in `test_screen_evidence_concurrency.py`.
This is preproduction memory protection, not durable encrypted storage
or an approved real DLP implementation.

## Owner-selected AOT J-Assist Administrator-only access policy (2026-11-06)

The Owner confirmed assignment to Datto RMM's built-in **Administrator**
security level as the pilot eligibility rule, rather than verifying each
user's CURRENT active security level.
Datto's native built-in designation is **Administrator security level**,
which grants access to every device in that Datto RMM account. It is a
level assigned to the user; the user's active UI security level can
differ if the user switches levels. This is therefore an explicitly
separate AOT J-Assist **screen-assistance eligibility** policy, not a
claim about the Datto UI session's active permissions.

The isolated `DattoAdministratorScreenAuthorizer` accepts ONLY fresh,
provider-verified proof that the **same** Entra-mapped Datto technician:
1. Is active/enabled, is positively assigned the built-in
   `Administrator` security level, and belongs to the pinned AOT Datto
   account. Membership proof expires after 30 seconds.
2. Requested an actual device UID that a second trusted Datto-native
   callback confirms belongs to the same pinned account.
3. Is requesting `screen_assistance` only. Commands, PowerShell,
   components, reboots and every other endpoint operation are denied by
   this policy and require independent governed authority.

Browser flags, email-domain matching, personal assertions, shared API
key security level and Entra membership alone never prove Datto
Administrator membership. Only server-owned trusted resolvers may
provide the evidence and device ownership check. The existing regular
DattoWebRemoteAuthorizer is unchanged; this is an opt-in alternative.

**Provider gap:** Official Datto RMM documents a read-only
`GET /v2/account/users` listing, but its documented `AuthUser`
response fields include username, email, status, disabled and dates,
not the assigned security levels. Thus the documented account-users
API alone does **not** prove Administrator membership. An independently
verified provider source (such as an approved Datto-supported
membership interface, or authenticated mapped KaseyaOne access-group
source if that is what the Owner means) is required before activating
the policy. No live adapter is configured. Fail closed until then.

References:
- https://rmm.datto.com/help/en/Content/3NEWUI/Setup/SecurityLevels.htm
- https://rmm.datto.com/help/en/Content/3NEWUI/Setup/Users.htm
- https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm

No browser Send button is enabled, no production source changed, no
provider identity is inferred, and no production release is authorized.
