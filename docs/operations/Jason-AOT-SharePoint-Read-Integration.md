# Jason AOT SharePoint Read Integration

## Section Goal

Give Jason a governed, application-only, read-only path to AOT SharePoint and OneDrive for Business so SharePoint can participate as an operational evidence and documentation source without granting mutation authority.

## Initial capability scope

The first implementation exposes four canonical read capabilities:

- `documentation.sharepoint.site.search` — find authorized SharePoint sites.
- `documentation.sharepoint.library.list` — list document libraries for an exact site.
- `documentation.sharepoint.document.search` — search SharePoint/OneDrive business documents through Microsoft Graph Search.
- `documentation.sharepoint.item.read` — read exact file/folder metadata by durable drive/item identity.

No upload, update, move, delete, sharing, permission-management, or other SharePoint write capability is registered.

## Governance boundary

The runtime is feature-gated by `JASON_SHAREPOINT_READ_ENABLED` and defaults to disabled.

When enabled, the provider is `microsoft_sharepoint` with permission profile `sharepoint-read`. The expected Microsoft application permission is `Sites.Read.All`. Authentication is application-only through Jason's governed Microsoft certificate/token path and a validated client boundary. Jason must not fall back to an interactive user's SharePoint session or the ChatGPT SharePoint connector.

The connector additionally fails closed for any organization other than `aot` and preserves the existing AOT client boundary default `client-aot-internal` when no narrower client scope is supplied.

## Auditing

Every provider request and completion is emitted through the existing connector audit sink into orchestration telemetry. Tokens and credentials are never written to audit events.

## Activation prerequisites

Before setting `JASON_SHAREPOINT_READ_ENABLED=true` in production:

1. create/validate a `microsoft_sharepoint` client boundary for AOT using profile `sharepoint-read`;
2. ensure the governed Microsoft application identity has admin consent for `Sites.Read.All`;
3. stage the SharePoint logical credential `microsoft_sharepoint.read` in the approved OpenBao path/policy;
4. perform a harmless live site-search proof against AOT SharePoint;
5. verify capability discovery, tenant isolation, audit events, and document-search output;
6. leave all SharePoint write capabilities absent.

## Current implementation state

Source implementation is complete and feature-gated. Manual connector/capability checks pass and modified Python modules compile cleanly. Host-side live permission probing cannot resolve the container-mounted Microsoft credential, so activation must be tested from the governed runtime deployment context after the SharePoint boundary/credential is staged.
