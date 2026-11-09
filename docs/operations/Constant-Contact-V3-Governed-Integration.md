# Constant Contact V3 — Governed Integration Runbook

**Status: SOURCE-ONLY; NOT DEPLOYED; NOT PROVIDER-VERIFIED.** Engineering issue #2383; draft PR #2384. Do not treat a successful unit test or an HTTP callback route in source as production readiness.

## Objective

AOT operator supplies an XLSX workbook → Jason reads, maps and validates contact records and consent evidence → checks actual provider suppression/list state → presents an exact action bound to a Teams approval → performs an idempotent bounded import → polls the asynchronous activity and verifies provider results. No email campaign is sent.

## Existing HTTPS host

Reuse `https://mcp-jason.teamaot.com` with the exact redirect URI:

`https://mcp-jason.teamaot.com/oauth/constant-contact/callback`

The URL is **not** reachable as a Constant Contact callback until a separately approved deployment activates the MCP route. Do not authorize an account before the protected release.

## Constant Contact app

- Application: AOT - Project Jason
- Client ID: `ad24a820-822f-4c66-8446-3407167bc78a` (not confidential)
- Flow: OAuth 2.0 authorization code, server-side client secret.
- Required scopes: `contact_data offline_access`. No campaign permissions.
- Authorization host: `authz.constantcontact.com`; API host: `api.cc.email`.
- Authorization state must be unpredictable, expiring and one-time; tokens rotated and encrypted.

## Isolated OpenBao secret

Provider registration: `constant_contact`. Logical secret: `constant_contact.oauth_client`.

Production KV path:
`secret/data/connectors/constant-contact/production/oauth-client`

Required fields: `client_id`, `client_secret`, `token_key_b64` (random 32-byte AES-256 key, base64).

Provision using the existing protected `tools/provider_secret.py create constant_contact` operator workflow **only after reviewing production environment compatibility**. The saved client secret is entered into local hidden prompts, NEVER chat, GitHub, ticket notes, logs, URLs or shell history. Do not write the token key to stdout.

The canonical host projection is:
`/var/lib/jason/runtime-secrets/openbao/constant-contact-oauth-client-approle/`

Any container AppRole mount must bind `role_id` and `secret_id` to the MCP service's configured `JASON_CONSTANT_CONTACT_OPENBAO_ROLE_ID_PATH` and `JASON_CONSTANT_CONTACT_OPENBAO_SECRET_ID_PATH`. These paths are **not yet verified in production**.

The encrypted OAuth SQLite state defaults to:
`/var/lib/jason/openclaw/constant-contact/oauth.sqlite3`

## Owner-local OAuth start (after route rollout)

From an isolated, verified source/runtime with the approved AppRole projection:
```bash
PYTHONPATH=implementation python3 tools/constant_contact_oauth.py status
PYTHONPATH=implementation python3 tools/constant_contact_oauth.py begin
```
The `begin` command prints an OAuth consent URL containing a short-lived, non-secret state. The authorized AOT account owner opens it in their browser. The callback consumes state once, exchanges the code via Basic client authentication, validates the returned scopes, encrypts access and refresh tokens, then returns a sanitized status.

**Important:** An OAuth success response is not proof of the intended AOT account identity or of contact access. Before enabling imports, establish and verify the authorized provider account binding using live account/list evidence; reject an unknown account.

## Engineering acceptance before release

1. Complete governed runtime capability catalog registration and requester identity/information-release restrictions. No direct shell/API bypass.
2. Complete protected OAuth ingress and account binding, prevent callback replays, validate refresh recovery and secret-safe errors.
3. Complete production credential lifecycle and read-only connection acceptance.
4. XLSX import preview must reject unsupported fields, formulas, missing explicit consent proof, duplicates and known suppressions. Any caller-supplied suppression-complete flag is advisory, never execution authorization.
5. Implement governed write capability with exact-target Teams approval, idempotency, and polling `GET /v3/activities/{id}` until completion; read back actual changes and classify errors. Never opt an unsubscribed contact back in without that contact's documented consent.
6. Validate retry/rate-limits, provider 401/403/429, network failures, disconnect/revoke, concurrency, token refresh and redacted audit.
7. Full regression, security review, exact candidate SHA, rollback SHA, frozen-prod compatibility, Teams exact-SHA release approval, deployment verification, and zero unrelated regression.

## Known release boundary

The PMV3 engineering Owner pause is active. Do not remove the pause receipt, restart the engineering worker, bypass the protected-main gate, merge this draft PR, or deploy to production without the required governed release sequence and Teams approval.

## Provider references

- https://developer.constantcontact.com/api_guide/server_flow.html
- https://developer.constantcontact.com/api_guide/import_contacts.html
- https://developer.constantcontact.com/api_guide/contacts_sync.html
