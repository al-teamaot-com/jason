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

Offline fake-transport-focused `pytest` on the new scope guard and existing read/mutation foundation: **82 passed**. Tests cover positive exact-contract scoping, parent-company mismatch, denial of `None`/`Mine`/unknown, page bounds, field metadata, partial mixed-contract injection, duplicate IDs, bad row types, optional company mismatch, and no provider/secret execution surface. **No live ContractServices read attempted.**

**No production change, direct provider bypass, credential change, or financial mutation.**
