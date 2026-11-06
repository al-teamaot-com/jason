# AOT Jason Datto Observer — source-only local prototype

**Status:** Experimental; no production deployment, staff rollout, backend service, or endpoint execution.

## All-staff intent
The UX is intended for any authenticated **authorized AOT technician**, not one specific person or browser profile. Identity, native Datto permissions, tenant isolation and session-bound Jason authorization are prerequisites for connecting actual Jason processing. This local experiment does **not** verify staff identity beyond the technician's signed-in Chrome/Datto session, and must never be described as a governed AOT rollout.

## Test setup
1. In Chrome, open `chrome://extensions`, enable Developer mode, click **Load unpacked**, select this folder.
2. Open an approved test device in a Datto RMM tab matching `https://<region>.rmm.datto.com/...`.
3. Click the extension action on that tab; **Start observing** in the side panel.
4. Verify the local image preview changes after a visible, read-only PowerShell diagnostic. The preview is the **whole tab**, not DOM-extracted text. No terminal access is asserted.
5. Switch tabs: observation must pause; click **Stop**: preview is removed; close or navigate the Datto tab: session must cease.

## Controls and limitations
- No commands, no Datto API calls, no credentials, no network upload, no persistence and no Jason model connection.
- 2-second JPEG screenshots are ephemeral UI previews. Screen contents may include sensitive data; don't test on live client secrets or PII.
- Chrome extension permission is user-initiated `activeTab`; the whole visible tab is captured, not an independently authenticated PowerShell or WebRTC stream.
- Worker memory is not durable. If the service worker is suspended, observation may stop; do not treat this as a reliable session ledger.
- For a real staff rollout: verify supported Datto rendering/transport, implement explicit staff SSO + Datto/tenant/device authorization, per-session grants/revocation, server-side redaction and streaming, bounded data retention, multi-tenant evidence isolation, browser disconnect behavior, audit and tests.
- Loading this prototype locally is a development experiment, not production authorization.
