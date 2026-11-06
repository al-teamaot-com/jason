# J-Assist — Datto local prototype

**Naming update (v0.1.3):** Staff-facing name **J-Assist**. Action: **Start assisting**. The extension remains technician-controlled and local-preview only; it does not yet send data to Jason.

# Jason Assistant — Datto local prototype

**Previous naming iteration (v0.1.2):** The staff-facing product was briefly called **Jason Assistant**, with a Datto mode and a **Start assisting** consent action. This version is still only a local preview: Jason does not receive or analyze the screen. The historical branch/PR and filesystem directory retain the earlier development codename for traceability.

# Historical implementation notes (formerly Datto Observer)

**Status:** Experimental; no production deployment, staff rollout, backend service, or endpoint execution.

## All-staff intent
The UX is intended for any authenticated **authorized AOT technician**, not one specific person or browser profile. Identity, native Datto permissions, tenant isolation and session-bound Jason authorization are prerequisites for connecting actual Jason processing. This local experiment does **not** verify staff identity beyond the technician's signed-in Chrome/Datto session, and must never be described as a governed AOT rollout.

## Test setup
1. In Chrome, open `chrome://extensions`, enable Developer mode, click **Load unpacked**, select this folder.
2. Open an approved test device in a Datto RMM tab matching `https://<region>.rmm.datto.com/...`.
3. Click the extension action on that tab; **Start observing** in the side panel.
4. Verify the local image preview changes after a visible, read-only PowerShell diagnostic. The preview is the **whole tab**, not DOM-extracted text. No terminal access is asserted.
5. Switch tabs: observation must pause and clear the preview, then resume upon returning; click **Stop**: preview is removed.
6. Navigate the observed tab away from Datto, return, and verify the old session stays revoked. The panel should show a stopped state and permit an explicit new Start.
7. Close the panel and reopen it: observation must remain stopped and show no retained screenshot.

## Controls and limitations
- No commands, no Datto API calls, no credentials, no network upload, no persistence and no Jason model connection.
- 2-second JPEG screenshots are ephemeral UI previews. Screen contents may include sensitive data; don't test on live client secrets or PII.
- Chrome extension permission is user-initiated `activeTab`; the whole visible tab is captured, not an independently authenticated PowerShell or WebRTC stream.
- Worker memory is not durable. If the service worker is suspended, observation may stop; do not treat this as a reliable session ledger.
- For a real staff rollout: verify supported Datto rendering/transport, implement explicit staff SSO + Datto/tenant/device authorization, per-session grants/revocation, server-side redaction and streaming, bounded data retention, multi-tenant evidence isolation, browser disconnect behavior, audit and tests.
- Loading this prototype locally is a development experiment, not production authorization.

## Version 0.1.1 navigation fix
- Navigation (including a change between Datto devices) revokes the bound session rather than leaving the panel in a half-running error state.
- Background messages distinguish paused (inactive tab) from ended (revoked) observation. Pausing clears the stale preview; ending restores the Start control.
- Each Start receives a fresh session ID, and in-flight frames are rejected if the tab changes or the session is stopped/restarted before capture completes.
- This patch addresses a code-level defect identified after a technician reported unexpected Test 5 behavior. The cause of the exact observed error has not yet been independently established; interactive retest is required.

### Test 5 incident clarification (2026-11-06)
Technician observed that leaving the Datto tab revoked capture but the older v0.1.0 UI left Start disabled and Stop enabled. A subsequent Start after manual Stop returned "Not a supported Datto RMM tab". The first problem is corrected in v0.1.1; the follow-up failure is consistent with Chrome having a non-Datto tab active, but the exact tab state was not captured. The UI now tells technicians to select the actual Datto PowerShell tab before starting. Returning to a prior tab does not recover its revoked session.

## J-Assist graphical scope — version 0.1.4

The technician may open J-Assist on the Datto Web Remote PowerShell tab
or a graphical/non-shell Datto Web Remote tab. In both cases, the local
Chrome capture is the **whole active visible Datto browser tab**: no
remote endpoint agent, WebRTC interception, command transport or new
permission is added.

The side panel labels the selected surface as PowerShell, non-shell
Web Remote (potentially graphical), or an ordinary Datto RMM tab.
This URL-based classification is a descriptive UI hint, **not** proof
of the actual desktop/session type and **not** an authorization grant.
The existing background worker performs independent origin, exact-tab,
active-tab, navigation, and session checks on every capture.

Safety: full-tab screenshots can contain passwords, client data,
personal information, patient information, or other material not suitable
for further processing. Screenshot transmission and Jason vision analysis
remain **disabled** pending separate identity, Datto native role,
consent, retention, audit, data-minimization and redaction acceptance.
No staff-wide deployment has occurred.

## J-Assist approved brand assets — v0.1.5

Chrome extension metadata now uses branded 16/32/48/128 PNG icons. The 16px variant intentionally omits the sparkle detail for legibility. The Datto side panel uses the original dark compact header SVG supplied in **Jason/J-Assist Visual Identity v1.0 (2026-11-06)**. The PNG icons were regenerated from the matching approved SVG geometry at native dimensions; source SVG masters are retained in `brand/`. No new Chrome permissions, hosted assets, network communication, Jason inference or endpoint control. Preview authorization/capture behavior is unchanged.

To update an installed unpacked extension, replace its files with this version, visit `chrome://extensions`, and click **Reload** for J-Assist. Verify the teal toolbar icon and dark side-panel header.

## Version 0.1.6 — local reviewed screenshot

After **Start assisting**, select **Capture screenshot** to request a **fresh, active Datto tab** frame from the existing authorization-checked worker. Review it in the side panel, then explicitly click **Download reviewed screenshot**. File name carries UTC capture timestamp and no client details. Screenshots are never auto-attached to Autotask, sent to Jason, uploaded or stored in extension storage. The prepared evidence and download link are invalidated on Stop, inactive tab, failed capture, tab navigation/revocation, and panel close. The existing Chrome activeTab capture permission and worker authorization rules are unchanged.

**Visual acceptance required:** With a non-sensitive authorized Datto test tab active, take a screenshot and download it. Confirm the image depicts that test tab, the screenshot link disappears on Stop or tab switch, and no Autotask attachment is created. Manual redaction and ticket attachment remain technician responsibility.

## Version 0.1.7 — copy reviewed screenshot for ChatGPT (manual subscription workflow)

After an authorized Datto session is explicitly started, the technician
clicks **Capture screenshot**, visually reviews the result, then chooses
**Copy reviewed screenshot**. The extension converts that selected JPEG
to a PNG in memory and writes it to the system clipboard, using the added
`clipboardWrite` permission. The technician must then independently paste
the image into an approved AOT ChatGPT conversation; no ChatGPT/Datto
credentials, OpenAI API key or subscription token is requested. The
extension itself never uploads the image, opens a network connection to
Jason, or submits the image to ChatGPT. No API inference is used.

Copying is refused before capture, when the selected tab changes, and after
Stop/closure. The extension clears its download link and internal preview
on Stop but **cannot erase a screenshot already copied to the operating
system clipboard**. Technicians must avoid secrets, passwords, protected
health data or prohibited client information and clear/replace the
clipboard when finished. Clipboard writes are deliberate user gestures,
not background capture. Native Chrome permission `clipboardWrite` is
an additional permission in v0.1.7; do not silently upgrade existing
staff installations without the technician knowing.

**Not end-to-end automation:** An authorized technician's manual copy/paste
uses the technician's normal ChatGPT workspace interface and subscription.
It does not prove custom MCP registration, secure automatic screenshot
delivery, Datto native-permission evidence, or Jason model analysis via the
extension. Those remain gated separately.

## Version 0.1.8 — simplified single-action panel (UI shell only)

The panel now prominently displays **Send to Jason** and collapses the
existing local preview, capture, copy and download controls into **Advanced**.
Existing v0.1.7 local capabilities remain available. The new primary control
is **disabled with an explicit disconnected status**, not simulated.

Target approved one-click transaction (future release):
1. Verify selected active HTTPS Datto tab and exact device UID.
2. Authenticate technician with verified Entra identity, map to current
   individually authenticated Datto technician active security-level evidence.
3. Start or reuse exact device/tenant/technician-scoped authorized session.
4. Capture a fresh screenshot on explicit click. Prefer actual supported
   terminal text only when independently authorized and its origin provable;
   do not scrape arbitrary webpage DOM or infer text from an image.
5. Perform server-side DLP/content checks, then send over TLS with bounded
   size, image hash, session nonce and single-use receipt. No silent captures.
6. Show **Sent to Jason** only after verified server receipt; fail clearly on
   mismatch, session expiry, closed tab, unauthorized device, or redaction
   rejection. Make evidence retrievable by the same user's authenticated
   ChatGPT Business custom Jason MCP connection, with no billable API fallback.

Production blockers: real verified Datto technician permission adapter,
Entra browser OAuth, securely audited session persistence/recovery,
TLS image intake and content controls, MCP image retrieval and real
AOT ChatGPT workspace end-to-end acceptance. Do not enable the button
until those gates pass. This release is a layout/test prototype only.
