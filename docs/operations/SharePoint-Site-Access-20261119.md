# AOT SharePoint site access — isolated implementation contract (2026-11-19)

Status: **engineering partial, not deployed or operational**. This work extends the existing reusable reader in PR #1330; do not merge this branch directly into protected `main` until all acceptance tests and the release authorization have been satisfied.

## Scope and noninterference

- One dedicated Jason workload Entra application and Microsoft Graph connector covers all AOT-owned SharePoint sites; never impersonate the Owner or use the ChatGPT SharePoint connector.
- The AOT Accounting bank-statement repository is an ordinary consumer of the same site/library/document authorization layer; no separate SharePoint authentication, access editor, or connector.
- This branch is rooted in `feature/reusable-sharepoint-reader-20261012`, not in any PMv4 core, playbook, or Autotask catalog work branch.
- No protected ticket worker, service/bundle write path, playbook registry, runtime deployment, credentials, or production freeze is altered by these source changes.

## Runtime site policy

`site_access_registry.SharePointSiteAccess` supplies a persistent SQLite store with immutable-by-default site discovery, an enabled flag, monotonic revision, audit history and last scan evidence. Site IDs are exact Microsoft Graph identifiers and scope is fixed to the configured AOT tenant. New discoveries are **disabled**. Subsequent discovery cannot reset the switch. Any unknown site, wrong tenant, or disabled site fails closed.

Grafana displays the state but **does not write the database directly**. A narrowly permissioned Jason API accepts site identifier, desired state, expected revision, verified authenticated Owner/admin identity and exact approval reference; after policy evaluation, it calls `set_enabled`. The API must log request/correlation ID and prohibit broad permission expansion. An enable action changes Jason's *site access policy*, never underlying Graph app roles or separate sensitive-document release policy. UI must obtain the readback after every switch.

The site gate must execute on **every** SharePoint provider operation, immediately before Graph access, and on any scheduled operation. All file searches and downloads still require caller identity, sensitivity/release and tenant/client checks. Provider writes, if independently approved in future, must use the same site gate plus their separate exact-action authorization.

## Daily discovery

Scheduler: existing Jason scheduler, 05:00 America/New_York is reserved for the financial organizer, so this separate daily discovery should use another configurable time. Discover all AOT tenant sites via authenticated **app-only** Graph traversal with bounded paging and retry/backoff, verify completeness and tenant ID, then commit a single `discover(...)` transaction. Never publish a partial successful scan. If Graph fails, call `discovery_failed` and retain fail-closed existing site decisions. No site auto-enable, no restart, no deployment, no PR needed for ordinary site toggles.

## Grafana page

AOT SharePoint Sites table: display name, site URL, site identifier, enabled/disabled, first/last seen, policy revision, last scan, per-site last successful authorized operation, last failure. Authorized toggle action calls the governed Jason API (not a Grafana SQL update or Graph permission change). Show recent audit events and explicit errors; disabled sites remain visible.

## Production acceptance (not yet achieved)

1. Dedicated Jason app certificate and OpenBao profile validated; app-only Graph discovery works in AOT tenant.
2. Reusable reader manifest is registered in governed Jason MCP; identity, site access and document release rules are bound to every operation.
3. AOT Accounting and a second AOT site both pass limited real readback under Jason's service identity.
4. Disabled site fails closed for search, metadata, content and scheduled processing; enabled site works immediately without rebuild, restart or deploy.
5. New AOT site is discovered in a real daily run and starts disabled; repeat scan preserves settings; failed partial scan does not enable anything.
6. Grafana retrieves real site state and demonstrates authenticated on/off round trip with exact audit evidence.
7. Unauthorized requesters and external/client tenants are denied; no leak from content or metadata.
8. Representative PMv4 ticket-processing, services/bundles, and JSON playbook registry smoke tests show no regression.
9. Independent release review, exact candidate SHA + rollback and current Owner production authorization completed before deployment.

## Current engineering evidence

Source branch `feature/sharepoint-site-access-config-20261119` now contains durable site access state management, a bounded app-only Microsoft Graph `getAllSites` enumerator with full pagination and atomic daily-scan semantics, the site-gated connector wrapper, a governed admin service with exact revision and approval validation injection, unit tests, and focused CI. These components are **source-only**: the existing Jason scheduler has not yet been wired to invoke the scanner, the Grafana page and authenticated API have not been deployed, the wrapper has not yet been registered as the live connector, and the site/certificate/provider acceptance has not run. `Sites.Read.All` alone does not establish app-only runtime access. Do not claim functionality based solely on these code files.
