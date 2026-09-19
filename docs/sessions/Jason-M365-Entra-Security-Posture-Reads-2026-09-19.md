# Jason Microsoft 365 / Entra Security-Posture Reads — 2026-09-19

## Section Goal
Give Jason narrow governed Microsoft 365 / Entra security-posture reads that can support client security reviews and evidence-backed questionnaire answers without allowing conversation input to select a tenant, application credential, Graph host, arbitrary Graph path, or write operation.

## Initial read slice
- `identity.authentication.methods.read` — registered authentication method types for one exact Entra user. Secret method material is not projected.
- `identity.conditional.access.search` — bounded Conditional Access policy state, conditions, grant controls, and session controls.
- `identity.directory.role.search` — bounded activated Entra directory roles.
- `identity.directory.role.members.search` — bounded members of one exact activated role.

All reads derive the Microsoft tenant from the authenticated requester's existing trusted Microsoft/Jason binding and validated client boundary. Graph v1.0 public cloud is fixed. The caller cannot supply a tenant, token, application ID, Graph URL, permission profile, or HTTP method.

## Deliberate exclusions from this slice
Exchange Online protection configuration is not implemented through arbitrary Graph calls. Exchange transport rules, anti-malware, anti-spam, Safe Links/Safe Attachments, quarantine, and related controls require an authoritative supported Exchange administration/read surface and will be implemented separately rather than approximated from Graph.

## Permission expectation
The existing source catalog already defines `identity-investigation-read` with AuditLog/Directory/IdentityRisk/Reports/UserAuthenticationMethod read permissions, but production currently uses the narrower `directory-read` profile. Production proof must therefore determine which new reads the currently consented application can perform and fail closed on missing consent. No permission is broadened as part of source deployment.

## Acceptance
1. Source tests prove exact tenant derivation, bounded results, exact role/user selectors, fixed Graph v1.0 paths, and safe projection.
2. Deploy with the existing credential/boundary profile only; do not alter tenant consent.
3. Production-prove each capability individually.
4. Record missing Graph permissions/consent as explicit desk-dependent blockers rather than bypassing them.
5. Preserve `direct_provider_access=false` and Central Orchestrator information-release controls.

## Production checkpoint
Source revision `124621a` is deployed. Existing tenant-bound `identity.user.search` remains healthy. The new authentication-method and Conditional Access reads reached Microsoft Graph but returned HTTP 403, confirming the current narrow application consent does not authorize those data sets. Directory-role enumeration returned HTTP 400 and is not claimed as accepted. No Microsoft application permissions, tenant consent, certificate credential, or client boundary were broadened during this work. Production acceptance is therefore **PARTIAL / DESK-DEPENDENT**.
