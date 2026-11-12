# Governed organization matching — reusable foundation

**Development-only (draft PR #1331).** This engine is provider-neutral and is **not** registered as an active Jason MCP capability. It performs no provider reads or writes and creates no accounting transactions or durable mappings.

## Goal

Any separately **approved** Jason process may ask the same organization-resolution service to compare two already-authorized sets of organization records. The service must not become a path around a provider's authorization or information-release controls.

Examples of potential callers: Autotask ↔ QuickBooks customer reconciliation, ConnectBooster billing identity alignment, quote/procurement customer identification, copier customer record correlation, and future approved MSP systems.

## Architecture and contract

- `OrganizationRecord` normalizes source, durable ID, client/tenant scope, display/legal name, telephone, email, business domain and street/postal evidence.
- `autotask_company` and `quickbooks_customer` adapters normalize native provider fields without making network requests or guessing a mapping. QuickBooks subcustomer `DisplayName` and `CompanyName` are preserved separately.
- `match_organizations` is a bounded, deterministic pure calculation. It rejects duplicate source IDs and mixed tenant/client scope, uses nonnegative evidence scores, rejects public/test-email domain evidence and emits stable candidates.
- `GovernedOrganizationMatchService` verifies the **specific principal + approved process + exact scope + source pair** before processing. It requires source evidence identifiers and retrieves previously approved mapping links through a trusted registry, never accepting a caller-proposed approval flag.
- The service records *only* source evidence IDs, approved process and scope identifiers, and aggregate decision counts to its audit interface; customer names or raw financial data are not written into that audit.
- Authorization in this source layer is **injected**, not provided by a live host. Caller must wire it to Jason's existing real requester/permission and provider information-release policy prior to activation.
- The current version proposes matches but does not persist them; the approved mapping registry is a separate, governed future capability.

## Status contract

- **verified**: an independently approved and persisted one-to-one mapping was supplied by the trusted registry, with an approval identifier. The matching engine cannot create this state itself.
- **probable**: a unique strong candidate supported by an exact normalized company name and at least one separate channel of evidence. **Never becomes a persisted link without verification.**
- **possible**: weaker or fuzzy name evidence, even if the highest candidate.
- **ambiguous**: duplicate possible target customers, overlapping source contenders, or similar competing evidence. No automatic choice.
- **unmatched**: no admissible candidate.

A company name alone is insufficient for verification. The matcher never treats shared public/free-email domains or synthetic test domains as independent business identity proof. It rejects matching across different client scopes and does not equate Autotask IDs to QuickBooks IDs without evidence.

## Restrictions and acceptance

- Inputs must be sourced from independently authorized read paths. Caller is responsible for minimization/retention and exact client/tenant binding.
- Confirmed mappings require governed review and readback against both systems. Source provenance, mapping changes, revocation and supersession must be durable and audited by the future mapping registry.
- No customer merge, account update, invoice change, payment, bank action, QuickBooks write, or Autotask write is authorized by this feature.
- Sample QuickBooks sandbox customers are not AOT production customer matches.
- Before production, complete approved-process policy wiring, data sensitivity/release tests, multi-tenant deny tests, provider-backed pagination, duplicate review workflow and signed-off financial acceptance.

Focused CI: `.github/workflows/organization-matching.yml`. Related issues: #403, #200. The source-level tests include provider-shaped Autotask and QuickBooks fixtures and verify no direct provider access.
