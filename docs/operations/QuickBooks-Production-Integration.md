# QuickBooks Production Integration Runbook

## Goal

Connect Project Jason to AOT's live QuickBooks Online company using Intuit OAuth 2.0 while preserving the already-proven read-only governance model.

Production is a separate trust boundary from the sandbox. Development credentials, production credentials, sandbox OAuth state, and production OAuth state must never be substituted for one another.

## External prerequisites

Do not authorize the live AOT QuickBooks company until all of the following are true:

1. The Intuit Production Key / app assessment questionnaire is completed accurately and approved.
2. Intuit exposes the app's separate Production Client ID and Client Secret.
3. The Production redirect URI is registered exactly as:
   `https://mcp-jason.teamaot.com/oauth/quickbooks/production/callback`
4. The authorized Intuit scope remains only:
   `com.intuit.quickbooks.accounting`
5. Payments scope is disabled.
6. AOT explicitly approves the live-company connection.

Marketplace publication is not a prerequisite for this private/internal integration unless Intuit changes the applicable program requirements.

## Production security facts

Use these facts when answering the Intuit assessment. Do not claim controls Jason does not have.

- Use case: private/internal AOT accounting integration.
- Initial access: read-only.
- Accounting scope only; no Payments.
- OAuth 2.0 authorization-code flow.
- OAuth authorization, token, and revocation endpoints are resolved from Intuit's environment-appropriate discovery document and accepted only when they remain on the expected Intuit HTTPS hosts.
- Invalid or expired refresh grants are treated as reconnect-required, the unusable local token state is cleared, and the caller receives an explicit reconnect-required authorization failure.
- User-requested disconnect uses Intuit's revocation endpoint before local OAuth state is cleared.
- Production Client ID/Secret stored only in OpenBao.
- Production OAuth token state stored separately from sandbox.
- Production OAuth token payload encrypted using AES-256-GCM.
- The AES-256-GCM key is stored in the production OpenBao secret as `token_key_b64`.
- QuickBooks response bodies are not persisted in connector/orchestration event logs; operational metadata is.
- Requester access requires Jason identity/authority, Central Orchestrator governance, and the existing information-release gate.
- The Jason host must **not** be represented as having full-disk/LUKS encryption unless that is separately implemented and verified.

If the Intuit questionnaire asks a legal, privacy-policy, retention, breach-response, or public-policy URL question that is not covered by an existing approved AOT policy, stop and obtain the correct approved answer rather than inventing one.

## Production secret provisioning

Production uses a separate provider identity:

- provider spec: `quickbooks_production`
- logical secret: `quickbooks.production.oauth_client`
- OpenBao KV path: `secret/data/connectors/quickbooks/production/oauth-client`
- AppRole projection:
  `/var/lib/jason/runtime-secrets/openbao/quickbooks-production-oauth-client-approle/`

Required fields:

- `client_id`
- `client_secret`
- `token_key_b64`

Generate the 256-bit token-encryption key locally on Jason. Do not paste the result into chat, source control, a ticket, or documentation:

```bash
python3 -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode('ascii'))"
```

Then create the production secret interactively:

```bash
cd /home/al/projects/jason
sudo python3 tools/provider_secret.py create quickbooks_production
```

Enter the Intuit Production Client ID, Intuit Production Client Secret, and locally generated `token_key_b64` only into the hidden operator prompts.

Verify the provider lifecycle without printing secret values:

```bash
sudo python3 tools/provider_secret.py verify quickbooks_production
```

## Production OAuth state

Production OAuth state is stored separately at:

`/var/lib/jason/openclaw/quickbooks-production/oauth.sqlite3`

The database file is owner-only, and the token payload itself must be stored as AES-256-GCM ciphertext. The encryption key is resolved from OpenBao at runtime.

Production code must fail closed if:

- the production AppRole is unavailable;
- the production token encryption key is unavailable or malformed;
- production OAuth state is plaintext;
- the OAuth environment does not equal `production`.

## Deploy production callback support

Production callback support may be deployed before the live company is authorized. Do not activate the production read profile until the production OAuth connection succeeds.

The callback is:

`https://mcp-jason.teamaot.com/oauth/quickbooks/production/callback`

The sandbox callback remains separate:

`https://mcp-jason.teamaot.com/oauth/quickbooks/callback`

## Sandbox connection lifecycle acceptance

Before submitting an Intuit production questionnaire that attests to connection lifecycle behavior, run a deliberate sandbox acceptance using the same OAuth implementation:

1. Confirm the sandbox company is connected and a bounded `accounting.company.read` succeeds.
2. Run `tools/quickbooks_oauth.py disconnect --environment sandbox --confirm`. This must revoke the current Intuit refresh token before clearing local OAuth state.
3. Confirm sandbox status reports disconnected and no refresh token.
4. Run `tools/quickbooks_oauth.py start --environment sandbox`, complete the Intuit authorization UI, and reconnect the sandbox company.
5. Confirm sandbox status reports connected, realm-bound, and refresh-token present.
6. Run `accounting.company.read` again and confirm the expected sandbox company.
7. Force or naturally exercise one refresh and confirm the newest returned refresh token is persisted.

Do not represent the connect/disconnect/reconnect lifecycle as tested until this acceptance has actually completed.

## Start production authorization

After Intuit production approval, production credential provisioning, and Production redirect registration:

```bash
cd /home/al/projects/jason
PYTHONPATH=implementation python3 tools/quickbooks_oauth.py start --environment production
```

Open the generated authorization URL and select the **live AOT QuickBooks company**, not a sandbox.

A successful Jason callback returns only non-secret connection status.

## Verify production OAuth state

```bash
PYTHONPATH=implementation python3 tools/quickbooks_oauth.py status --environment production
```

Expected evidence:

- connected = true;
- environment = production;
- realm_bound = true;
- has_refresh_token = true;
- secret_values_printed = false.

Do not print token values or the encryption key.

## Activate production reads

The exact production activation profile is:

`JASON_QUICKBOOKS_READ_PROFILE=quickbooks-production-read-v1`

This profile must select:

- Production OpenBao identity;
- Production encrypted OAuth DB;
- Production QuickBooks API base `https://quickbooks.api.intuit.com`.

The deployment must fail closed rather than falling back to development/sandbox state.

## Production acceptance

Run `accounting.company.read` first.

Before any broader read, confirm that CompanyInfo identifies the intended **live AOT company**. If the company identity is unexpected, stop and deactivate production access.

Then run the bounded read-only acceptance sequence:

1. `accounting.company.read`
2. `accounting.account.search` with a small result count
3. `accounting.vendor.search`
4. `accounting.customer.search`
5. `accounting.invoice.search`
6. `accounting.bill.search`
7. `accounting.report.profitloss.read`
8. `accounting.report.balancesheet.read`

Confirm every call:

- resolves through Central Orchestrator;
- uses provider `quickbooks`;
- reports successful information release for the authorized AOT owner;
- contains no write operation;
- contains no Payments operation.

## Token refresh acceptance

After live read acceptance, force one bounded OAuth refresh without printing token values. Confirm:

- refresh succeeds;
- the connection remains production-bound;
- the newest returned refresh token state is persisted;
- the encrypted production OAuth row remains encrypted;
- `accounting.company.read` still succeeds afterward.

## Rollback and disconnect

A production issue must be recoverable without affecting sandbox.

Rollback options include:

1. Deploy with the sandbox profile to return read routing to sandbox while leaving production state intact.
2. Deactivate the production OpenBao AppRole to remove runtime access while preserving the KV secret for controlled recovery.
3. Clear production OAuth state only with explicit operator confirmation.
4. Revoke/disconnect the Intuit app connection from the appropriate Intuit/QuickBooks control when required.

Do not delete the sandbox OAuth database or development OpenBao identity as part of a production rollback.

## Explicit exclusions

This production v1 does **not** authorize:

- creating or editing invoices;
- creating or editing bills;
- journal entries;
- payments;
- bank transactions;
- reconciliations that post changes;
- deletes;
- Payments API access;
- any other QuickBooks mutation.

Any future QuickBooks write authority requires a separate design, capability catalog, risk review, explicit approval model, tests, and production release.
