# Autotask ContractServices scoped read — preproduction design and tests

**Date:** 2026-11-04
**State:** Isolated, **dormant source** only. No Jason capability registration, no provider reads/writes, no production deployment.
**Related:** Commercial RW audit draft PR #2308; vendor-cost reconciliation #200; billing assurance #403; contract intelligence #435; invoice read repair #2147.

## Problem proved by live evidence

The existing Jason **read-only** Autotask API credential reports `userAccessForQuery=None` on `ContractServices`. The **existing Jason RW** account reports `userAccessForQuery=Restricted` for `ContractServices`, with `canQuery=true`. Generic v13 dynamic reads deliberately require `All` and must not be widened to `Restricted`. Live RW tests have already proved bounded reads for Products, Services, ProductVendors, ServiceBundles, Contracts, BillingItems and Invoices. Three of three sampled BillingItems with an invoiceID matched the invoice ID and company ID on provider GET. These facts do not authorize unrestricted ContractServices reads or any commercial write.

## Scoped source primitive

`implementation/connectors/autotask/contract_service_scope.py` is a pure fail-closed validator with no provider transport, OpenBao resolver, callback registration, or production activation.

For an explicitly authorized company and contract:
1. Require positive exact `contract_id` and `expected_company_id` from the authenticated requester context (not from an untrusted payload alone).
2. Require a **separately authorized** parent Contract record whose `id` and `companyID` exactly match.
3. Require entity metadata from the **same eventual provider credential**, `canQuery=true` and `userAccessForQuery` either `All` or `Restricted`. `None`, `Mine` and ambiguous access fail closed.
4. Require field metadata proves both `id` and `contractID` queryable.
5. Compile only an exact `contractID=...` equality search with `MaxRecords` 1–100. No broad all-contract read.
6. Validate every result row's durable `id`, `contractID`, optional companyID, uniqueness, row count, and parental scope **before** returning any rows. Reject the whole page on mismatch; never release partial results.
7. **Do not** mistake one bounded page for complete pagination or full company inventory.

## Not yet integrated or granted

- A separate governed read capability with exact contract and client selectors, verified requester role, information-release checks and post-read contract membership must be designed and reviewed.
- A credential-safe, read-only provider adapter must use an **explicitly approved** RW-read secret policy; the current `autotask.readonly` identity has `None` and cannot access this entity. Do not change the global read credential, copy secrets or expose direct raw HTTP.
- Preserve the vendor-native entity-specific `Restricted` response. A scoped access check is necessary, but the provider's final record-level authorization and the independent Jason client-disclosure gate must both pass.
- Add bounded continuation/duplicate protections and exact child-to-parent joins, negative requester and cross-client release tests, observed provider GET proof, and a safe rollback path.
- Complete matching contract unit quantity/price to BillingItems and actual Invoices before claiming end-to-end billing assurance.
- No source activation or production promotion without CI, integration review, exact candidate and rollback SHA, and separate owner approval under production freeze.

## Verification in isolated worktree

Isolated source base: `97b4ec71a3e0ec5805b91eec42ca32905ea18c85` (latest remote main observed on 2026-11-04). Existing unrelated `procurement_teams_flow.py` changes on the user's separate working branch were left untouched.

Offline fake-transport-focused `pytest` on the new scope guard, dormant read connector and existing read/mutation foundation: **108 passed**. Tests cover positive exact-contract scoping, parent-company mismatch, denial of `None`/`Mine`/unknown, page bounds, field metadata, partial mixed-contract injection, duplicate IDs, bad row types, optional company mismatch, and no provider/secret execution surface. **No live ContractServices read attempted.**

**No production change, direct provider bypass, credential change, or financial mutation.**

## Dormant provider connector candidate

`implementation/connectors/autotask/contract_service_connector.py` adds a **source-only**, non-registered `DormantScopedContractServicesReadConnector`. It requires an injected **trusted** `ContractCompanyAuthorizer` and does not expose an MCP or runtime capability. This helper currently runs only with fake provider transport in tests.

When wired by a future reviewed governed adapter, the candidate uses the existing `autotask.write` logical credential, compiles the parent contract GET with the existing canonical Autotask operation compiler, then requires an exact requester/company authorization *before* any ContractServices metadata or child read. The candidate currently rejects all `context.client_id` values other than `None` (AOT-internal-only review); a future authenticated client-context resolver is required before any customer-scoped access can be activated. It retrieves same-credential provider schema, compiles only an exact contractID query, validates every child row against the parent, and rejects provider pagination that it cannot certify. All network operation shapes in this candidate are GET-only. It makes no direct public API available and introduces no impersonation shortcut or runtime permission grant.

The response distinguishes `boundedPageValidated=True` from `fullContractCoverageVerified=False` to avoid claiming complete recurring billing coverage based on a single bounded page.

The source is **not safe to register in production yet**: it lacks the wired canonical requester/company authorization backend, verified disclosure policy, full contract pagination, exact provider-backed ContractServices proof, cross-client negative acceptance, and all financial release gates.
