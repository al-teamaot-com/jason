# QuickBooks Online Provider

## Purpose

QuickBooks Online is the governed accounting evidence provider for Project Jason's AOT-internal financial workflows.

This provider is intentionally **read-only** in its first implementation. It exists to support accounting visibility, reconciliation assistance, procurement/billing cross-checks, and reporting without granting Jason accounting mutation authority.

## Provider identity

- Provider ID: `quickbooks`
- Vendor: Intuit
- API: QuickBooks Online Accounting API
- Authentication: OAuth 2.0 authorization code + refresh token
- OAuth endpoint discovery: Intuit discovery documents (`openid_sandbox_configuration` for sandbox and `openid_configuration` for production), with HTTPS and expected-host validation
- Disconnect: Intuit revocation endpoint using the current refresh token, followed by local OAuth-state clearing only after successful revocation
- Reconnect handling: invalid/expired refresh grants fail closed as an explicit reconnect-required condition
- Authorized OAuth scope: `com.intuit.quickbooks.accounting`
- Payments scope: **not authorized**
- Current live/accepted environment: **sandbox**
- Production implementation state: code-ready but **not live**. Activation remains blocked until Intuit approves the Production Key/app assessment, separate production credentials are provisioned, the AOT live company is explicitly authorized, and production acceptance succeeds.

## Trust and isolation boundary

QuickBooks company scope is established only by the `realmId` returned by Intuit during the completed OAuth flow.

Callers may not supply:

- `realmId` / `realm_id`;
- environment;
- raw QuickBooks query text.

The connector fails closed if the OAuth environment does not match the active Jason connector profile.

Static Intuit application credentials are isolated by environment in OpenBao:

- development: `quickbooks.oauth_client` at `secret/data/connectors/quickbooks/development/oauth-client`;
- production: `quickbooks.production.oauth_client` at `secret/data/connectors/quickbooks/production/oauth-client`.

Sandbox OAuth state uses `/var/lib/jason/openclaw/quickbooks/oauth.sqlite3`. Production OAuth state uses the separate `/var/lib/jason/openclaw/quickbooks-production/oauth.sqlite3` store and requires AES-256-GCM application-layer encryption. The production token encryption key is supplied from OpenBao as `token_key_b64`; plaintext production token rows fail closed.

No OAuth token, Client Secret, or provider credential may be emitted to logs, chat output, evidence, documentation, fixtures, or source control.

For support diagnostics, the shared HTTP transport may capture only the allowlisted Intuit `intuit_tid` response header as a bounded provider trace ID. Successful QuickBooks connector completions audit that value as `intuit_tid`; HTTP failures carry it as sanitized `provider_trace_id` metadata. Raw response headers are not persisted.

## Canonical read capabilities

- `accounting.company.read`
- `accounting.account.search`
- `accounting.vendor.search`
- `accounting.customer.search`
- `accounting.invoice.search`
- `accounting.bill.search`
- `accounting.report.profitloss.read`
- `accounting.report.balancesheet.read`

Search operations use fixed server-authored QuickBooks entity queries with bounded paging. Raw caller-authored query text is prohibited.

## Authorization and information release

Provider fetch authority does not imply requester release authority.

QuickBooks evidence is releasable only when Jason establishes all of the following:

1. AOT organization scope;
2. human requester;
3. valid JKD-001 authority context;
4. observe permission;
5. Central Orchestrator execute path;
6. active trusted Microsoft/Jason identity binding.

Unknown requester authorization fails closed as service-only evidence.

## Activation

The provider and capabilities are registered in dormant PILOT/PLANNED state.

Activation is explicit and environment-bound:

- sandbox: `JASON_QUICKBOOKS_READ_PROFILE=quickbooks-sandbox-read-v1`;
- production: `JASON_QUICKBOOKS_READ_PROFILE=quickbooks-production-read-v1`.

The production profile selects the production API base, production-only OpenBao AppRole, and production-only encrypted OAuth state. Production deployment fails closed if the production AppRole is unavailable; it does not fall back to sandbox credentials or tokens.

The existence of the production profile is **not** approval to connect live books. The Intuit Production Key assessment, production keys, live-company OAuth authorization, and AOT production acceptance remain separate required gates.

## Compliance constraints

Project Jason must follow the current Intuit Developer Terms, QuickBooks Online terms applicable to the connected company, OAuth requirements, production assessment requirements, privacy/security requirements, and branding/marketplace rules applicable to the deployment.

The connector must remain least-privilege. Production remains read-only with the Accounting scope only. A new Intuit scope, Payments access, or any QuickBooks write operation requires a separate reviewed change; technical API availability is not authority to use it.

QuickBooks response bodies are not written to Jason's connector/orchestration event stores; those stores retain operational metadata only. The Jason host must not be represented as using full-disk encryption unless that control is separately implemented and verified.
