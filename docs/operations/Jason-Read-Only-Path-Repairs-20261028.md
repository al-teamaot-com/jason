# Project Jason — read-only operational path repairs (2026-10-28)

## Owner rule

Authenticated AOT staff must be able to perform supported, tenant-bound and provider-authorized read-only investigations without ad hoc internal read permission grants. Information disclosure still requires positive requester identity, source authorization and secret protection. Production writes, remote execution and disruptive operations remain separately governed.

## IT Glue sanitized technician metadata

For registered Jason-managed organization, configuration, flexible asset and attachment-metadata lookups, the invoker must first remove credential-named fields from the *released* result and then classify sensitivity of that redacted result. The original implementation classified the raw API payload before redacting fields, causing ordinary asset/organization discovery to be blocked even when all credential fields were removed. It returned `DERIVED_OUTPUT_TRANSFORMATION_REQUIRED` and requested a pointless approval.

The replacement deliberately does **not** grant raw secrets, restricted document content, missing requester bindings, or provider service-account privileges. If an inline token/password/private key remains in a free-text value after field redaction, the result remains `DERIVED_OUTPUT_ONLY` and the release authorizer refuses it. Restricted document reads retain their independent ACL evidence checks. The source response is not republished or reclassified by caller-supplied flags. Tests validate the complete release authorizer, redacted credential fields, inline secret refusal, and no-trusted-binding denial.

## Microsoft Graph directory-role enumeration

`GET /directoryRoles` and `GET /directoryRoles/{id}/members` on Graph v1.0 do not support `$top`; the old connector sent it for every bounded request, producing `HTTP 400`. Do not send `$top` for these two endpoints. Instead apply the requested maximum to a locally projected allowlist and report `truncated=true` if the source page exceeds it or supplies `@odata.nextLink`. Reject malformed source records. Never follow an arbitrary provider next link or return unbounded caller-visible data. The Conditional Access policies endpoint *does* support `$top` and is unchanged.

References: Microsoft Graph v1.0 `directoryrole-list`, `directoryrole-list-members`, and `conditionalaccessroot-list-policies` official API references.

## Separate provider authorization dependencies (not solved by this code change)

Conditional Access `HTTP 403` requires confirmation that the exact tenant-bound Graph application has `Policy.Read.All` application permission and tenant admin consent, plus a governed profile/boundary that permits it. The currently configured `directory-read` profile is limited to `User.Read.All`; broadening a profile or granting tenant permissions is a separately approved authorization change, **not** part of this source repair. Directory role enumeration requires `RoleManagement.Read.Directory` or an approved equivalent and the same tenant proof. Where sign-in logs are not registered in Jason's live catalog, new read capabilities and appropriate `AuditLog.Read.All` consent need separate work.

KFS `PROVIDER_TRANSPORT_FAILURE` is not a Jason JKD-001 authorization denial. Jason's host resolves and negotiates TLS with the approved `api.kyods.com` endpoint; the connector's dealer API login and provider-response path requires separate authenticated provider diagnostics without printing or bypassing managed credentials. Do not fabricate meter readings or mark KFS healthy based on network TLS alone.

## Acceptance

Protected tests and isolated release preproduction must pass; source integrity, approval binding, provider identity, confidentiality and rollback protections remain in place. After a separately authorized production deployment, use live governed requests to validate a non-sensitive IT Glue organization lookup and a directory-role read. Recheck Conditional Access and KFS separately and report source/permission failures accurately.
