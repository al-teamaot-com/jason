# Autotask Read Coverage Audit — 2026-10-27

**Status: documentation / provider-metadata inventory only; no new production reads activated.**

| Measurement | Evidence-backed value |
|---|---:|
| Public documentation candidate entity names | 230 |
| Distinct union of public and source-known names | 230 |
| Existing Jason connector source-known names | 31 |
| Live governed schema checks succeeded | 38 |
| API integration userAccessForQuery=All | 35 |
| API integration userAccessForQuery=None | 3 |
| Live entity-record queries validated through new generic route | 0 |
| Named entity families with at least one live read route | 22 |
| Vendor candidate metadata verified | 16.5% |

## Important distinctions

The published index contains candidates, not an authenticated API account's permissions. The presence of `canQuery=true` alone is insufficient; user-specific `userAccessForQuery=None` remains a provider denial. The metadata evidence is not a successful record query, field-completeness test, child traversal, pagination test, or proof that a user may receive a result. An API read and requester disclosure remain separate decisions.

Known provider-account metadata restrictions: BillingItems, ContractNotes, Invoices.

## Next engineering gates

1. Continue live governed entityInformation/fields metadata discovery for the remaining names; record unsupported names and query-only endpoints separately.
2. Review field visibility, sensitive attachments and labor, child relations, and preserve named audited provider routes without enabling generic raw HTTP.
3. Add the missing versioned bounded read-only routes, full pagination and exact ID proof, plus negative requester-disclosure and mutation non-escalation tests.
4. Merge reviewed source under protected CI. Production promotion stays frozen until a separate exact-SHA owner exception, verified baseline and native rollback.

Sources: [Autotask REST entity index](https://autotask.net/help/developerhelp/content/apis/rest/Entities/_EntitiesOverview.htm), governed AOT `service.entity.describe` metadata snapshot in `Autotask-Live-Schema-Observations-20261027.json`. Machine-readable detailed evidence classification is in the sibling CSV.
