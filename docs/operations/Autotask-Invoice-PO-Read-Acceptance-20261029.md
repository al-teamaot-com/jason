# Invoice/PO read-access acceptance — isolated workstream #2147

Date: 2026-10-29. **Investigation and preproduction preparation only; no production permission changes or deployment.**

## Owner policy
Use #2077 as the broad internal query model: Jason may investigate all data accessible through AOT's legitimately authorized provider integration. Approved AOT staff generally receive read-only results, subject to authenticated requester, staff role, context, data classification, tenant boundary and outbound information-release policy. No blanket provider-rights bypass, no leakage to external users, no implied write permission. Reconcile requester-specific constraints in #2059 before allowing sensitive data release.

## Verified live provider behavior
All calls went through Jason's governed MCP read capability (no direct provider access).
- `service.purchase.order.search` completed and returned two PO records (ids 1000, 1002); correlation `corr_mcp_5619aeaa8f4e42c6adef496bb1ce3892`.
- `service.purchase.order.item.search` for PO id 1000 completed and returned one item referencing `orderID=1000`; correlation `corr_mcp_57808f05d8704ca88271e46c7a3eda66`.
- `service.invoice.search` failed with `PROVIDER_HTTP_STATUS_500`; correlation `corr_mcp_6b1a2292a513459495c5b99036c88e8c`.
- `service.entity.describe` for Invoices returned `canQuery=true`, `userAccessForQuery=None` and `userAccessForUpdate=None`; correlation `corr_mcp_fa4b0e2d83c54ea2874f7c3938879f42`.
- `service.entity.describe` for BillingItems returned `canQuery=true`, `userAccessForQuery=None` and `userAccessForUpdate=None`; correlation `corr_mcp_10de3cf0c428429a8bbf0ce48c6c56d3`.
- Prior bounded billing item search also returned provider HTTP 500, recorded in `docs/operations/Autotask-Live-Schema-Observations-20261027.json`.

**Interpretation:** Entity capability `canQuery=true` denotes API query support, not this authenticated integration user's permission. Both invoice and billing metadata explicitly report query access `None`. Treat the HTTP 500 as a provider error associated with a possible permission problem, not definitive proof of its root cause. No generic alternate route may be used to evade the denial.

## Independent next steps, no PM needed
1. Determine the effective Autotask API integration identity / requester impersonation mode **without exposing tokens**. Compare the exact API user's security level against legitimate AOT finance/read-only staff access. Log the approved role change request, not credentials.
2. If authorized by AOT, provision the **minimum provider-supported read permissions** for `Invoices` and `BillingItems` to the AOT integration identity, with no change to create/update/delete. If Autotask requires different permissions or unsupported endpoint access, document exact behavior and ask provider support.
3. Re-run governed `service.entity.describe` for both. Require `userAccessForQuery` to reflect permitted scope before attempting record extraction. Verify invoice search and exact invoice read with bounded pagination; verify billing item search and exact read; check joins, error behavior and no implicit mutation.
4. Test authorized AOT staff cross-client read disclosure, unauthorized staff and external customer denial, sensitive-field redaction, and audit evidence. Provider query access does not itself authorize disclosure.
5. Keep PO search/read and item search as foundational canaries; negative-test PO mutations as denied without exact approval.
6. Before eventual integration, rebase and regression-test against concurrent ticket-processing changes. PM/exact SHA/rollback are needed **for release**, not diagnosis or isolated preproduction development.

## Acceptance tracking
- [x] Live PO search
- [x] Live PO item search and PO linkage
- [x] Live invoice and billing entity schema authorization diagnosis
- [ ] Identify effective provider security-level configuration
- [ ] Authorized provider read-only permission correction, if supported
- [ ] Governed live invoice search/read and billing search/read
- [ ] Cross-client and negative disclosure acceptance
- [ ] Isolated preproduction tests and ticket-regression verification
- [ ] Production release approval (separate; not granted)
