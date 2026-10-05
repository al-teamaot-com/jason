# QuickBooks Online Provider

## Purpose

QuickBooks Online is the governed accounting evidence provider for Project Jason's AOT-internal financial workflows.

This provider is intentionally **read-only** in its first implementation. It exists to support accounting visibility, reconciliation assistance, procurement/billing cross-checks, and reporting without granting Jason accounting mutation authority.

## Provider identity

- Provider ID: `quickbooks`
- Vendor: Intuit
- API: QuickBooks Online Accounting API
- Authentication: OAuth 2.0 authorization code + refresh token
- Authorized OAuth scope: `com.intuit.quickbooks.accounting`
- Payments scope: **not authorized**
- Current approved environment: **sandbox only**
- Production state: blocked pending separate Intuit production credentials, production assessment/compliance completion, and a new explicit Jason production activation profile.

## Trust and isolation boundary

QuickBooks company scope is established only by the `realmId` returned by Intuit during the completed OAuth flow.

Callers may not supply:

- `realmId` / `realm_id`;
- environment;
- raw QuickBooks query text.

The connector fails closed if the OAuth environment does not match the active Jason connector profile.

Static Intuit application credentials are stored in OpenBao under the development-only logical secret `quickbooks.oauth_client`. Rotating provider-issued OAuth access/refresh tokens and the OAuth-bound Realm ID are stored in the protected QuickBooks OAuth state database.

No OAuth token, Client Secret, or provider credential may be emitted to logs, chat output, evidence, documentation, fixtures, or source control.

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

Sandbox activation requires the exact profile:

`JASON_QUICKBOOKS_READ_PROFILE=quickbooks-sandbox-read-v1`

No production profile exists in this implementation. Adding one is a separate trust decision and change.

## Compliance constraints

Project Jason must follow the current Intuit Developer Terms, QuickBooks Online terms applicable to the connected company, OAuth requirements, production assessment requirements, privacy/security requirements, and branding/marketplace rules applicable to the deployment.

The connector must remain least-privilege. A new Intuit scope or QuickBooks write operation requires a separate reviewed change; technical API availability is not authority to use it.
