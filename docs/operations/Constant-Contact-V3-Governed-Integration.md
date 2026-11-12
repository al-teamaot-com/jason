# Constant Contact V3 — Governed AOT Excel Contact Import

**Status:** SOURCE-ONLY / STAGED; NOT DEPLOYED; NO LIVE CONSTANT CONTACT ACCOUNT CONNECTED.
**Tracking:** issue #2383, feature PR #2384, requester authorization fix PR #2439.

## Objective and architecture

AOT technician provides a consent-backed XLSX workbook, reviews exact destination list mapping, obtains a verified exact-action approval, imports once, and receives authoritative per-record activity/readback evidence. No campaigns or SMS.

Reuse existing MCP HTTPS callback, OpenBao, Jason Central Orchestrator, universal verified plan ledger, and native governed execution-plan binding. The Constant Contact connector owns only its provider adapter, encrypted work records, subscription evidence and asynchronous job ledger. This is separate from PMv3 and must not interrupt the ticket worker.

The current *implemented* universal plan issuer relies on signed authenticated Teams ingress. The import contract itself is channel-neutral ("canonical_verified_owner"); a newly verified authenticated Owner channel can be adopted independently after full signature/identity/grant acceptance. Chat text, unsigned approvals and unlicensed-account notifications cannot grant provider writes. Production release approval follows the separately verified Owner-reviewed Teams-optional release policy.

## OAuth and account binding

- Application: AOT - Project Jason. The public Client ID is recorded in issue #2383. Never send the Client Secret in chat, source, logs, PR, shell history or ticket notes.
- Existing HTTPS host: https://mcp-jason.teamaot.com
- Exact callback: https://mcp-jason.teamaot.com/oauth/constant-contact/callback
- Minimum scopes: **account_read contact_data offline_access**. No campaign, SMS, account-update or event permissions. Account summary requires account_read, contacts/lists/import need contact_data, token rotation needs offline_access.
- OAuth server-side authorization code with fixed Constant Contact issuer/redirect, confidential Basic authentication, short-lived one-time CSRF state, strict granted scope and AES-GCM encrypted rotating tokens. The OAuth app registration and saved secret are Owner-local external dependencies; no live OAuth account is connected.
- The token's GET /v3/account/summary reveals encoded_account_id. Independently verify the actual AOT owner and organization before storing that identifier in a protected root-owned 0640 (or stricter) approved-account file. Never hardcode the account ID or trust a workbook/caller-provided ID.

## Protected production configuration — NOT staged

OpenBao logical secret "constant_contact.oauth_client" maps to "secret/data/connectors/constant-contact/production/oauth-client" with fields client_id, client_secret and token_key_b64 (base64 AES-256 key). Use the existing local protected provider_secret provisioning workflow only after exact release approval. AppRole mounts are JASON_CONSTANT_CONTACT_OPENBAO_ROLE_ID_PATH and JASON_CONSTANT_CONTACT_OPENBAO_SECRET_ID_PATH. Token DB: JASON_CONSTANT_CONTACT_OAUTH_DB. Import encrypted work DB: JASON_CONSTANT_CONTACT_IMPORT_WORK_DB; one-time claim/readback DB: JASON_CONSTANT_CONTACT_IMPORT_CLAIMS_DB. Protected account binding path: JASON_CONSTANT_CONTACT_ACCOUNT_BINDING_PATH (default /run/jason-secrets/constant-contact/approved-account.json).

The account file must include organization_id="aot", the independently confirmed encoded_account_id, and verification_basis="owner_approved_oauth_readback". Use root installation, never user-writable directories. Encrypted work uses a domain-separated HKDF key derived from protected OAuth encryption material. Encryption rotation/recovery and provider revocation need a separate reviewed operations procedure.

## Excel and consent rules

The initial pilot intentionally caps one import at **25 contacts**, even though Constant Contact supports up to 40,000 JSON contacts and a less-than-4-MB payload. Exactly one XLSX worksheet, up to 4 MB input. Allowed columns: email, first_name, last_name, company_name, job_title, marketing_consent, consent_evidence. Required columns are email, marketing_consent, consent_evidence. Duplicate headers, formulas, unsupported columns, invalid/duplicate emails, excess length, missing explicit consent or missing consent evidence are rejected.

Each stated consent proof must correspond to a real independent AOT record (e.g., dated opt-in form), not an invented value. Spreadsheet evidence is hash-bound for review, not automatically authenticated. Explicit review remains necessary. No implicit opt-in, campaigns or SMS are attempted.

**Constant Contact remains the subscription source of truth.** Read the OAuth account and exact destination lists; for every email perform GET /contacts with status=all and include=list_memberships. Global unsubscribe, deleted/temp hold, ambiguous/unknown or incomplete paginated evidence fails closed. Existing globally subscribed contacts might previously have unsubscribed from a specific list. The initial pilot therefore refuses existing contacts missing any destination list membership until separately verified list-specific re-consent is implemented. New contacts with documented opt-in may be imported; existing contacts already on all destination lists may have approved field changes. Bulk import assigns permission_to_send=implicit to new contacts regardless of the supplied independent explicit consent evidence: do not misrepresent that provider field.

Rate-limit: pace provider verification GETs by at least 0.3 seconds to stay under the usual 4 requests/second; remain below 10,000/day and respect HTTP 429 and Retry-After. Retry safe GETs only with bounded backoff. Never retry an ambiguous POST.

## Exact-action execution

1. A previously authenticated AOT requester requests preview. Verify the current Jason identity binding BEFORE fetching any Constant Contact data.
2. XLSX preflight plus current account, destination-list and per-contact subscription evidence yields an immutable preview + JSON specification digest; encrypt raw work data at rest.
3. Issuance: immutable canonical plan contains a server-generated work ID, account/preview/specification/suppression hashes, exact list IDs and count. Raw emails, OAuth tokens and secrets are NOT included in the approval request. The original canonical issuer must verify permission and transport the exact plan.
4. Approval: verify the original immutable plan's actual whole-plan fingerprint (not the import intent digest), authentic decision receipt, one-use state, policy, exact work/requester/scope and current expiration. Never accept a typed chat response as an import approval.
5. Dispatch: only the native governed "prepare -> bind -> re-prepare -> execute" connector path can write. Recheck current provider account, lists, contact preferences, signed plan receipt, approval state and one-time durable claim. A POST /v3/activities/contacts_json_import may occur ONCE for that intent.
6. The POST returns an activity ID and "pending_unverified", not completion. An unknown/failed HTTP response remains claimed; no automatic redispatch is permitted.
7. Reconcile read-only via GET /v3/activities/{id}, validate completion state and exact per-job counts, then verify each hashed email identity and required list membership through fresh provider reads. Only full per-record readback becomes a verified import receipt; missing/partial/error/unknown results are clearly reported.
8. One-hour executable work TTL and bounded longer encrypted readback retention are separate. Expired approval never authorizes another POST; a source-only readback component may continue checking already-submitted activities within the retention window.

## Activation and non-interference

**Read activation:** JASON_CONSTANT_CONTACT_READ_PROFILE=constant-contact-aot-read-v1 activates ONLY three scoped read capabilities. **Write activation:** JASON_CONSTANT_CONTACT_IMPORT_PROFILE=constant-contact-aot-import-pilot-v1 is an independent, disabled-by-default PILOT profile requiring active reads, canonical approval service, verified root account binding, OpenBao/OAuth session and exact feature deployment approval. No second approval service or gateway is created.

Do not set either environment profile, provision secrets, register a callback, merge protected main, restart services or change root freeze/drift control during source development. The PMv3 Owner pause remains in force until independently governed migration. Source-only tests and GitHub CI are NOT production authorization.

## Independent review and release evidence

- Review OAuth callback CSRF/replay, token rotation/secret safety; account/technician identity binding; suppression and list-specific consent; workbook validation and source data retention; canonical plan/grant checks; re-prepare exact-plan integrity; crash/replay and ambiguous POST; activity counter and every item readback; 401/403/429, timeouts and safe retries.
- Reconcile the staged feature against **current protected main** and overlapping runtime/MCP/approval/KFS/finance PRs, then run full required CI, risk reviews, isolated production-equivalent preproduction and zero-drift smoke, without merging unrelated work.
- Present exact final candidate SHA and reviewed scope digest, *live root-protected last-known-good rollback SHA*, complete manifest/freeze/breaker/health evidence, and test receipts for separate independently authenticated Owner release approval. Source branch SHA is not automatically a production candidate.
- After approved release: verify callback ingress, AOT account binding/privileges, protected secret lifecycle, one 1-to-3-contact documented-consent import, actual provider activity + per-contact readback, duplicate/replay refusal and ticket processing continuity; rollback if acceptance fails, restoring the original production freeze.
- Stage and verify independently scheduled **read-only** reconciliation before routine unattended imports. Pending/unknown work must not be marked complete.

## Exact external dependencies

After protected release preparation, the Owner must (1) register the exact callback in the Constant Contact app, (2) securely stage the saved Client Secret through local protected OpenBao prompts, (3) authorize and independently confirm the AOT account with the three scopes and provide a small consent-backed XLSX test, and (4) approve the exact release SHA/scope/rollback when presented. Do not request these before they are genuinely required.

## Primary Constant Contact references

- https://developer.constantcontact.com/api_guide/server_flow.html
- https://developer.constantcontact.com/api_guide/scopes.html
- https://developer.constantcontact.com/api_guide/account_details_get.html
- https://developer.constantcontact.com/api_guide/import_contacts.html
- https://developer.constantcontact.com/api_guide/contacts_sync.html
