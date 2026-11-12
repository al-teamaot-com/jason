# J-Assist — AOT-only isolated pilot activation candidate and live service checks

**Assessment date:** November 12, 2026 (read-only live evidence, US Eastern)
**Decision:** **NO-GO for pilot activation**; source preparation and review can continue.
**Owner authority already granted:** One controlled, manually initiated screenshot pilot
on an AOT-owned test device, with content screening, encrypted evidence, two-minute
retention and no device commands. **Production deployment / changing the existing
shared AWS relay was expressly not approved.**

## Exact pilot target (not activated)

| Subject | Immutable, scoped intent |
| --- | --- |
| Site and environment | AOT internal site only: `9bb56523-cade-4ffb-bc34-696e788f0f4c` |
| Test device | Datto browser ID `1717088`, native UUID `710e63d6-caca-d830-697a-81250b0a8321`, hostname `Al-Samsung` |
| Interactive eligibility | AOT tenant `f7054323-d52b-4863-8c2f-1898f0b6077c`, configured Entra security group `5273dd8a-1456-4985-b0a3-c00061267e26`, **individual** user enabled+member read |
| Chrome application | Pinned pilot client ID `d1cc801b-13ba-4d44-bea6-e7f08186e4d5`, extension `pihjpgplfhmpenlghbcdbgdkadleflfi`; **registration/consent not independently confirmed** |
| Browser authority | Delegated `JAssist.Send` to Jason API `9b9996e9-5c34-48b7-948c-f44f89352f89`, no browser Graph-wide permission |
| Host / ingress | Existing Jason host, isolated port `3981`, existing AWS EC2 relay `i-0b0bb56884acb565c`, exact proposed `mcp-jason.teamaot.com/v1/jassist/*` |
| Transport | Host firewall restricted to ZeroTier relay; TLS only, exact origin, no raw public listener |
| Evidence | AES-256-GCM with two independent 32-byte keys, maximum 1 MiB JPEG, 120-second expiry, reviewed purge, same-technician MCP read |
| Image-content policy | **Only independently attested exact-frame test fixtures** in current implementation. Unreviewed live screen images remain prohibited; not general DLP |
| New AWS resources / permissions | **Zero planned. None added or changed.** |
| Current activation state | Disabled source-only container; **not installed or started**, no registered MCP tool, no real screenshot transmitted |

## Read-only live service checks: fact vs missing evidence

| Gate | Verified or reported fact | Remaining evidence / exact action |
| --- | --- | --- |
| AOT identity | Jason governed `identity.user.search` completed through Microsoft Graph. Entra public JWKS returned **HTTP 200** with 6 RSA signing keys | No signed J-Assist SPA token, verified SPA registration/redirect/`JAssist.Send` consent, current individual user/group membership or Graph application-role consent proof. Group-member capability is **not deployed**. No authenticated local Graph PowerShell context available |
| Datto RMM | Governed UUID reads for `Al-Samsung` and `Al` succeeded, online/nondeleted/nonsuspended, exact AOT site | Governed numeric `endpoint.device.read(resource_id=1717088)` still **HTTP 404**. Draft PR #2456 adds exact provider by-ID lookup and must be integrated, deployed under separate authorization, then live-read/verified (numeric ID and UUID, same site/user) |
| OpenBao | `openbao` container running, initialized and unsealed, v2.6.1, raft storage | Dedicated least-privilege J-Assist OpenBao AppRole, exactly two independent scoped 32-byte secret keys, access-policy readback, key rotation and mounting **not verified or provisioned by this work** |
| Server configuration | Source example has `enabled:false`, placeholder site, AOT group ID. `/var/lib/jason/pilots/jassist` and proposed policy/review files **do not exist** | Audit-backed, owner-approved enabled policy on protected storage, 0700/0600 path, exact single-device binding, signed reviewer manifest and real encrypted retention/purge mount |
| Screenshot review | Strict SHA-256 positive-only preapproved test-frame reviewer passes synthetic negative tests | No general DLP; cannot permit arbitrary live Web Remote screenshots. Need independently signed fixture-review approval for the exact safe pilot frame or separately approved content-screening service; no accept-all fallback |
| Relay Caddy | **Owner-supplied Work report:** 10:29 AM ET, Caddy **v2.11.4**, live running config matched adapted baseline, candidate validated, MCP/Teams semantically unchanged, nine negative checks passed, no change applied | Underlying Caddyfile/adapted digests and 9 individual test outputs not attached to the reviewed GitHub packet. Record provenance honestly; do not manufacture. Separate exact-action approval still required before any relay route change |
| HTTPS / MCP | Existing production MCP `/healthz` HTTP **200**; J-Assist `/v1/jassist/readiness` HTTP **404**, no port 3981 listener, 0 registered J-Assist capabilities | Deploy isolated read-only authorized pilot receiver only after preflight and route authority. Register image MCP read behind canonical principal and verify same-user readback |
| Release control | Root-protected release breaker **OPEN**, reason `continuous_production_drift_detected`, with `failed_system_unit` problem. Failed `jason-openclaw-authority-health.service` reported exit status 2; drift-watchdog state was changing during the read | **Hard stop.** Fresh health, rollback and runtime/source alignment must pass independently. Protected last-known-good readback `690250b4...` is not a verified immediate rollback for newly observed `d1b8c196...` runtime images. No unfreeze/restart/drift exception was approved |
| Real acceptance | 176 Python integration tests, 52 Chrome tests, and 9 infrastructure tests passed on earlier PR head; network/negative cases were synthetic | Obtain exact new-head CI, live approved browser-to-Jason request and hash-bound receipt, checked image read, revocation/expiry/replay and noninterference after a separately authorized activation |

## Separately governed activation candidate

The source-only immutable-scope **`infrastructure/jassist-pilot/activation-candidate.json`**
pins the AOT tenant, group, test device IDs, site, existing relay, exact
private path, retention and zero-new-AWS scope. It deliberately contains **null**
protected-main SHA, rollback SHA, reviewed scope SHA256 and independent
authorization/evidence references. These values cannot be fabricated, copied
from an unrelated feature branch, or attested by a browser.

The **`pilot_activation_admission.py`** check:

- Demands a genuine independently governed evidence verifier for **all 13 gates**.
- Checks actual protected-main SHA, reviewed scope SHA256, different freshly
  verified rollback SHA and immutable Owner exact-action evidence.
- Fails closed on missing Graph consent/member read, Datto by-ID proof, vault
  keys, content reviewer, TLS/firewall, MCP readback, Caddy validation or
  production-breaker health evidence.
- Rejects unknown policy scopes, changed device/tenant/host/route, duplicate
  fields and untrusted local booleans. Its CLI performs **no writes** and
  never claims activation.
- Separates pre-activation checks from post-activation real technician
  screenshot/MCP acceptance; the latter cannot legitimately pass before
  an authorized pilot is available.

This is a **release preparation artifact**, not a signed deployment ticket or
an activated service. Any later production-shared relay edit needs explicit
independent exact-revision Owner authorization, regardless of whether AWS
new-resource count remains zero.

## Safe activation sequence (NOT executed)

1. Confirm protected production healthy, breaker closed, no regression in ticket,
   MCP or Teams processing; independent locked rollback SHA and freeze readback.
2. Integrate draft PR #2456 into protected main; verify fresh by-ID Datto result
   `1717088 -> 710e63d6-caca-d830-697a-81250b0a8321` in the AOT site.
3. Read the AOT Entra single-tenant SPA redirect/scope/admin consent and actual
   enabled-member Graph read under a separate least-privilege server identity.
4. Create a least-privilege J-Assist-only OpenBao AppRole/key-policy mapping using
   separately approved secret-management controls; verify key separation and
   rotation without exposing raw keys in logs, tickets or model messages.
5. Approve an exact non-sensitive fixture reviewer manifest (or certified DLP),
   protected configuration, bounded image storage and 120-second expiry/purge.
6. Attach the Work validation Caddy baseline/candidate artifacts/hashes to the
   immutable evidence package; revalidate current route/order immediately before
   separately authorizing a narrow, reversible route change.
7. Build a digest-pinned isolated pilot image, test local readiness and
   negative paths, then activate only under a locked exact-action release
   transaction authorized for the shared relay/host.
8. Perform the one-device signed-in Chrome-to-Jason send, verify sha256
   receipt + same-user MCP retrieval, deny replay/revocation/foreign users,
   and observe no Teams/MCP/ticket-processing degradation.
9. Restore production freeze byte-for-byte. On any failed check, disable only
   the pilot, revert the exact relay delta, verify original routing and
   protected production health, and retain audit/rollback evidence.

## Actual stopping boundary

**Development and preparation:** Authorized; work may continue.
**Pilot activation:** **NO-GO; not performed.**
**Production release / relay mutation:** **Not authorized in this chat.**

Necessary future external authorization is precise: verified AOT Entra
administrator consent (only if absent), approved scoped vault/DLP deployment,
access to immutable relay validation artifacts, independently confirmed
protected-main/runtime health, and exact-action Owner authorization **only
after** an immutable candidate SHA, scope, rollback and tests are shown.
No Teams approval is automatically required; identity and exact-action
evidence remain mandatory.

## Implementation-ready provider configuration drafts (nothing applied)

All five files below are **inactive, version-controlled templates**:

- `infrastructure/jassist-pilot/openbao-scope.PROPOSED.hcl`:
  J-Assist-only KV-v2 read on
  `secret/data/pilots/jassist/nonproduction/session-encryption`
  and `.../evidence-encryption`. No list/write/delete/sudo and no
  access to production connector credentials.
- `openbao-mapping.PROPOSED.json`: two distinct `key_b64`
  32-byte key contracts, dedicated
  `jason-jassist-pilot-read` AppRole, not provisioned.
- `entra-consent.PROPOSED.json`: source-known AOT SPA ID,
  exact Chrome redirect, `JAssist.Send` delegated API scope and
  separate server-side Graph permissions. Actual Entra registration,
  consent and membership remain unverified; do not add tenant
  permissions automatically.
- `access-policy.DISABLED.example.json` and
  `review-policy.DISABLED.example.json`: AOT-only exact
  disabled-by-default configurations; cannot enable upload.

The isolated image source is now **digest pinned** to the linux/amd64
Python 3.12.16 `slim-bookworm` manifest
`sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4`.
Seven resolved Python wheel versions and **individual SHA-256 hashes**
are recorded in `requirements.lock.txt`; an independent
`pip download --require-hashes` verification succeeded. No image was
built or deployed, and package pinning alone does not constitute a
vulnerability/supply-chain audit.

## Updated supply-chain check and separate MCP security exception

A read-only Docker registry inspection pinned the pilot base to
`python:3.12-slim-bookworm@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4`
(linux/amd64). The **seven Python dependencies**, including all resolved
transitives, are now individually version- and SHA-256-pinned in
`infrastructure/jassist-pilot/requirements.lock.txt`. A second
`pip download --require-hashes --only-binary=:all:` succeeded for all
seven matching wheel artifacts.

A source-only `pip-audit 2.10.1` run initially found **15 advisory
records** for PyJWT 2.13.0 in the proposed pilot lock. After upgrading
only the **nonproduction pilot** to PyJWT **2.15.1**, the audit returned
**zero known vulnerabilities** for the seven locked packages, and
all **176 J-Assist Python tests** passed with the patched 2.15.1 wheel
actively imported. A current advisory scan has no warranty of
future findings, and an image still requires an independently verified
build provenance/SBOM. **No image was built or deployed.**

Separately, a read-only command showed the currently running
`jason-mcp-pilot` container uses PyJWT **2.13.0** while
`jason-runtime` uses **2.15.1**. This does **not** prove the MCP JWT
verification path is exploitable; J-Assist's own JWT verifier requires
RS256, and reachability must be assessed per advisory. To avoid
silently expanding the approved pilot into a production upgrade,
separate governed security issue **#2464** tracks review, scoped
patch candidate, rollback and exact Owner authorization.
No production or MCP container was changed.
