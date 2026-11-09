# Financial Statement Maintenance

## Purpose

`TODO-FIN-001` is the governed Jason maintenance workflow for AOT financial statements. It runs from Jason's existing auxiliary maintenance process at 05:00 `America/New_York`, recursively scans the configured SharePoint `Bank Checking Accounts Register` root, and normalizes verified bank, line-of-credit, and credit-card statements into `Bank Statements - Organized`.

The workflow is disabled by default. Deploying the code does not activate SharePoint mutation authority.

## Production authority boundary

Use a dedicated Microsoft client boundary with provider `microsoft_sharepoint` and profile `sharepoint-write`. The Microsoft application should use the least-privilege `Sites.Selected` application permission and receive **write** access only to the AOT Accounting Documents SharePoint site. Do not grant tenant-wide `Sites.ReadWrite.All` for this workflow.

The dedicated OpenBao AppRole must resolve only the logical credential `microsoft_graph.sharepoint_write`. Directory-read or mail credentials are not accepted as a fallback.

Required production settings:

- `JASON_FINANCIAL_STATEMENT_MAINTENANCE_ENABLED=true`
- `JASON_FINANCIAL_STATEMENT_TENANT_ID=<validated AOT tenant id>`
- `JASON_FINANCIAL_STATEMENT_DRIVE_ID=<AOT Accounting Documents drive id>`
- `JASON_FINANCIAL_STATEMENT_ROOT_PATH=Bank Checking Accounts Register`
- `JASON_FINANCIAL_STATEMENT_TIMEZONE=America/New_York`
- `JASON_FINANCIAL_STATEMENT_RUN_HOUR=5`
- dedicated SharePoint-write OpenBao role/secret host paths

Activation requires the normal PMV3 exact-revision production authorization plus verified provider consent/site grant. Missing credentials, boundary validation, tenant/drive identifiers, or provider permission fail closed.

## Safety and completion

The implementation has no delete operation. Exact duplicates are left intact and reported. Ambiguous/unclassified documents remain in place. Canonical filename collisions fail closed. Every move/rename is provider-read back before it is counted successful.

A run with any file error is recorded but is not marked complete; it becomes eligible for another attempt after 15 minutes. An error-free run is recorded once for the local calendar day, making subsequent scheduler ticks idempotent.

The operational objective is not complete until production evidence proves the scheduler executed at/after 05:00 Eastern, the intended SharePoint root was scanned, provider mutations/readback behaved correctly, and a subsequent no-change run is idempotent.

## November 9 integration review

The source branch was merged with current `main` before CI verification. Active PR #2373 also edits runtime composition and Compose for separately governed client notifications; PR #2380 adds a disabled-by-default outbound opt-in environment setting to Compose. Those changes occupy independent settings and execution paths from the financial-statement SharePoint-write integration. Record both in PR #2336's integration coordination field and revalidate if either PR merges before this workstream.

Source integration is not permission to activate production. A dedicated SharePoint-write `Sites.Selected` site grant and OpenBao AppRole credentials must be verified before a production release can enable this workflow.
