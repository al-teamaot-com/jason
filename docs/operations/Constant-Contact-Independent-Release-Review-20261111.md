# Constant Contact — Independent Release Review

**Work item:** #2383. **Staged PR:** #2384. **Import/security PR:** #2439 (targets feature branch, not protected main).
**Disposition:** SOURCE-ONLY; NOT DEPLOYED; NOT AUTHORIZED FOR PROVIDER WRITES.

## Isolated scope

- Minimum OAuth scopes: account_read, contact_data and offline_access. One-time CSRF state, strict callback, encrypted rotating tokens.
- Read-only connected account, exact list, and per-contact subscription checks. Provider suppression is authoritative; absent list membership blocks re-adding existing contacts during this pilot.
- One XLSX sheet, no formulas, explicit consent evidence, max 25 pilot contacts.
- AES-GCM encrypted work records, one-hour write-authority work expiry, independent read-only reconciliation retention.
- Authenticated requester authorization **before** provider calls, original immutable plan/grant evidence, execution-plan preparation and re-preparation.
- Durable one-time POST claim; unknown outcome never redispatches. Async activity and itemized membership readback.
- Separately opt-in read and write activation profiles, disabled by default.
- GET-only reconciliation component not yet scheduled or deployed.

No changes to production ticket processing, Autotask, DRMM, PMv3, freezes, drift protection or rollback.

## Review findings

1. Owner approval is not intrinsically Teams-only; however, the existing *implemented* universal issuer still uses signed Teams ingress. Future authenticated ChatGPT Owner approval requires a separately proven issuer binding and original receipt, not a chat text.
2. Constant Contact is the preference authority. The pilot never silently re-subscribes globally unsubscribed or list-unsubscribed contacts, even with a stale spreadsheet.
3. The universal plan fingerprint is **not** the Constant Contact import-intent digest. Both are independently checked against canonical immutable approval evidence.
4. Only Central Orchestrator's prepared provider plan can submit a write. Ambiguous POST remains claimed, never automatically retried.
5. New contacts imported in bulk receive provider permission_to_send=implicit even when explicit consent was independently documented; do not misreport provider subscription evidence.
6. Never send an email campaign or SMS as part of an import. Client Secret goes only through the Jason console's protected OpenBao prompt.

## Tests and release scope

Tested source with private fake provider, real encrypted work SQLite and real canonical plan/grant SQLite stores. Cases include wrong account, target, requester, permission, revoked approval, mutated request material, replayed/unknown POST, activity mismatch, expiry, safe provider readback and root-owned account file checks.

Before a protected-main release, independently review this PR against current main, run required full CI and source security review, verify exact candidate SHA and scope hash, root-owned rollback SHA, freeze/breaker/health receipts and authentic Owner approval. Verify one controlled 1-to-3-contact import and actual activity/member readback after credentials are locally staged. Confirm unchanged ticket-worker processing; rollback and restore original freeze byte-for-byte if acceptance fails.

## Jason console entry — ONLY at authorized live connection stage

From the approved source checkout on the actual Jason console:

    sudo python3 tools/provider_secret.py create constant_contact

This canonical command requests the local OpenBao administrator password followed by constant_contact client_id, constant_contact client_secret, and constant_contact token_key_b64 through hidden prompts. Use a fresh 32-byte random encryption key encoded as base64. The OpenBao KV v2 CAS write is single-use; if a value already exists, the supported lifecycle action is update rather than create. A --check-only option is available and does not contact OpenBao or request a secret.

**Never** put the secret in ChatGPT, a shell argument, environment variable, ticket note, email, PR, stdout or GitHub. Do not run the live create command until the Owner is explicitly asked for that concrete console action.

## Outstanding external acceptance

- Owner registers exact HTTPS OAuth callback in Constant Contact developer application.
- Owner enters saved Client Secret on Jason console with protected prompts.
- Live OAuth permission and AOT account identity, destination list access, provider import and readback verified.
- Separate exact release authorization and restored freeze; no standing promotion permission.
