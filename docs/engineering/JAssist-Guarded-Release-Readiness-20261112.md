# J-Assist: Governed Release Readiness and Acceptance Packet

**Status:** PREPRODUCTION CANDIDATE ONLY — RELEASE NOT AUTHORIZED, LIVE ACCEPTANCE NOT SATISFIED
**Date:** 2026-11-12
**Workstream:** J-Assist Chrome Extension / isolated Jason evidence service
**Primary PR:** Current-main integration review (see GitHub PR metadata for exact head SHA)

## Reviewed objective and owner decisions

Provide a technician-initiated **Send to Jason** action from an authorized Datto RMM/Web Remote tab. Use membership in the existing **AOT-Jason-JAssist-Users** Entra group as J-Assist eligibility, not the Datto Administrator security level. Store the *group object ID* as a governed, versioned setting. Initial ID from Owner's 2026-11-06 Graph readback: `5273dd8a-1456-4985-b0a3-c00061267e26`. No individual person list is hard-coded. Preserve separate Datto device/account authorization, identity binding, explicit consent, and all normal independent endpoint-action controls.

**Protected application boundary:** No changes to autonomous Autotask ticket processing, existing Jason.Read MCP OAuth contract, Datto endpoint automation, or production release/freeze controls.

## Isolated component scope

- `experiments/chrome-datto-observer/`: MV3 J-Assist extension, Entra PKCE sign-in, pinned Jason HTTPS origin, exact Datto Web Remote/device URL parsing, explicit one-click image capture, hash/nonce/receipt binding, worker-only access token and UI fail-closed behavior
- `implementation/jassist/`: canonical access-policy schema, server-owned Graph token/member reader, independently verified Datto device scope, narrow signed `JAssist.Send` verifier, AES-256-GCM sealed durable session and image stores, independent DLP injection, ASGI intake, read-only ChatGPT MCP image reader, exact-release activation gate
- `experiments/j-assist-bridge/`: historical compatibility imports and synthetic integration/negative acceptance tests
- `.github/workflows/jassist-preproduction.yml`: path-scoped security/integration CI for the new component

All new application endpoints are inactive until the existing governed MCP application invokes the reviewed activation adapter with actual validated dependencies and exact-release approval. The development example policy is `enabled:false` and contains a **placeholder** Datto account ID. A synthetically signed JWT, test reviewer, test group membership, or a checked-in approval label is not live production authority.

## Preproduction evidence

The evidence must be captured against the immutable head SHA shown by GitHub at review. At source preparation, local tests cover:

- Browser worker actually imports all integration scripts, retains access token in volatile worker memory, never exposes token to panel/Datto DOM or extension storage
- Browser-shaped success/failure path: correct Datto account/device URL, current-tab checks, server readiness, short session, JPEG capture, SHA-256, fresh nonce, verified receipt, safe stop
- Signed RS256 JWT with AOT `tid`, `iss`, `aud`, exact `azp`, `scp=JAssist.Send`, time claims and canonical individual subject binding; wrong caller/scope rejected
- Current configured Entra group and enabled user read from server-owned Microsoft Graph; membership and device authorization rechecked on capture and retrieval; policy rotation/revocation denied
- Durable encrypted session key and encrypted image evidence, no plaintext secret or screenshot at rest; replay, concurrency, cross-principal/device and expiry rejection; restart/readback validation
- Bounded exact-origin HTTPS ASGI request handler, content-type/length limits, credential-header denial, no unreviewed image success
- MCP read-only evidence identity and content contract, no model analysis or endpoint execution claims

Synthetic test PASS does **not** prove real browser/Graph/Datto/DLP/TLS/ChatGPT acceptance.

## Live admission checklist — all MUST pass before release

| Gate | Current state | Required independent evidence |
|---|---|---|
| Current AOT Entra group/technician | NOT VERIFIED LIVE | Signed, tenant-bound Graph user-enabled and group membership read with approved server application permissions |
| Dedicated JAssist.Send SPA and Jason resource | NOT VERIFIED LIVE | Exact app ID, stable Chrome redirect, scope admin consent, token `aud/azp/scp`, actual interactive sign-in |
| Actual Datto authorization | NOT VERIFIED LIVE | Server-side trusted native device/account ownership lookup for specific test UID; correct mapped individual technician |
| Governed server configuration | NOT LIVE | Approved `enabled:true` policy from immutable-audit settings publisher; exact AOT account UID; rollback policy; no browser-provided values |
| Approved screen content review | NOT LIVE | Approved DLP/review provider with defensible rejection/redaction policy, test with synthetic sensitive markers; no accept-all |
| At-rest secrets and retention | TESTED SYNTHETIC ONLY | Server-owned separated vault keys, approved encrypted volumes/permissions, audit/purge and backup/rotation review |
| Production ingress | NOT LIVE | Pinned HTTPS route, TLS/trusted proxy validation, exact Chrome Origin/CORS, rate limits, upload bounds, observability |
| Jason MCP image read | NOT REGISTERED LIVE | Tool registered behind Jason's verified principal/authority boundary; same-user receipt retrieval; no API inference fallback |
| Real end-to-end technician acceptance | NOT RUN | Click actual Chrome J-Assist Send on controlled non-sensitive Datto test device; upload/readback exact hash, verify reviewer, receipt, same-user MCP image; negative cases and revocation |
| Protected integration | NOT YET COMPLETE | Merge/reconcile against current protected main; all required post-merge CI; active-PR overlap gate and scoped smoke |
| Release authority and rollback | NOT AUTHORIZED | Authenticated Owner exact SHA/scope/rollback consent; independently verified release revision, preflight, locked production lane and current healthy rollback SHA |

**Mandatory stop:** Do not claim the objective complete, enable live image delivery, turn off drift/freeze protection, or deploy production on branch-only CI or synthetic results. Never make the browser a source of identity/authority or transmit real client content through experimental loopback intake.

## Production rollback / release protocol

At preparation, the last root-protected production readback identified accepted production source SHA `690250b4d21f32cce79cab9f5b4c18cf93e7e94a`, aligned for host/MCP/runtime, with breaker closed. This is a **provisional rollback reference**, not an everlasting authorization. The Release Manager must independently refresh and verify it immediately before promotion, and prove runtime images and policy state. A candidate only qualifies after it is merged to protected `main` and verified by protected CI; a feature-branch SHA alone is not a deployable candidate under J-CHANGE-001.

**Release steps:** identify exact approved main SHA and reviewed scope SHA256; verify protected-main tests, dependency/security review, Datto/Graph readiness, DLP, origin, policy/keys and live acceptance in isolated production-equivalent pilot; obtain exact-action Owner release authorization through the authenticated governed path (Teams approval not inherently required); use the existing serialized locked Production Manager release; restore freeze byte-for-byte; independently verify live revision, trusted identity, receipt/RBAC, noninterference with ticket processing, runtime/MCP alignment, rollback readiness. Roll back to verified preceding accepted SHA on failed smoke/health and verify rollback before breaker clearance.

## Actual current block and next authorized work

Live Graph membership and scope consent, Datto device/account authority, certified DLP, trusted vault/HTTPS configuration, real browser session and MCP tool registration must be independently provided and verified. A live Chrome UI test requires browser control in ChatGPT Work or direct authorized technician hands-on acceptance; Chat-mode browser access is read-only. No test pass may substitute for those facts.

Do not mark production ready until all gates have verifiable, immutable evidence.


## 2026-11-12 Owner-approved nonproduction screenshot pilot

The Owner approved exactly one **controlled, technician-initiated
J-Assist screenshot pilot on an AOT-owned test device**, with content
screening, AES-encrypted storage, 120-second evidence retention, no
automatic endpoint commands and **no production deployment**. This
approval DOES NOT authorize a production source promotion, relaxing
Jason's release freeze, enabling the MCP tool on the production host,
using clients' data, or replacing the independent Entra/Datto checks.

**Selected candidate:** `Al`, Windows 11, account `AzureAD\AlDavis`,
Datto site `Atlantic Office Machines` (native site UID
`9bb56523-cade-4ffb-bc34-696e788f0f4c`), native Datto device UID
`69571572-83f7-1e33-9cdf-01717d4e74a4`. Live governed Jason
`endpoint.device.search` and `endpoint.device.read` confirmed a
currently online, nonsuspended, nondeleted device in that exact site.
No real screenshots were retrieved or transmitted by those reads.

**Native-UID correction:** The original experimental extension and
server policy accepted decimal Datto UIDs only. The pilot source
now accepts *either* strict legacy decimal UIDs *or* canonical UUIDs,
including Datto's actual API-reported UID above, and rechecks the
same resource/site in the server-owned governed Datto device read
adapter on each step. Wrong-site, stale, offline, suspended, deleted,
corrupt provider response, disabled Entra group member or invalid
device selector must deny. The v1 configuration key named
`aot_account_uid` must be configured as the **verified internal Datto
site UID** for this pilot; its legacy name is not authorization to use
the broader Datto account indiscriminately. Rename in a future
schema migration once live configuration publisher is established.

**Prepared Windows pilot package:** Tested J-Assist 0.2.1 extension
files staged under the Owner's Al workstation Downloads in the
`JAssist-Pilot-20261112` directory. Package SHA256 read back on
Windows after secure SSH file transfer; staged only, not loaded into
Chrome or published. Update the hash once the UUID correction build
has been re-transferred. Do not auto-install or run browser automation
via shell.

**Real acceptance STILL BLOCKED:** The Chrome Browser integration
in this Chat context is read-only (Work-mode browser UI control is not
available), and the currently deployed Jason MCP service still lacks
an active J-Assist receiver, approved content DLP, governed enabled
configuration, vault-backed keys, trusted TLS proxy and registered
MCP image reader. No real screenshot acceptance can be claimed.
A Work-mode authorized technician browser session and approved live
nonproduction ingress are required. Until then, the extension remains
fail-closed and no client/user screenshot data leaves the machine.
