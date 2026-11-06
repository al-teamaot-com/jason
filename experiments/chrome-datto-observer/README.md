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
