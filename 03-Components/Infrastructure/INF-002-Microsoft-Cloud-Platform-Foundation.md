# INF-002 Microsoft Cloud Platform Foundation

## Purpose

INF-002 establishes Microsoft 365 and Azure/Entra services as a first-class governed provider family for Jason.

The platform foundation is intentionally broader than a single Microsoft Graph connector. It provides a shared identity, tenant, permission-profile, endpoint, and request-policy layer for capabilities that use Microsoft cloud services.

## Existing foundation reused

Jason already contains Microsoft onboarding and certificate-token foundations including:

- Microsoft administrator-consent request and callback validation;
- provider-independent client-boundary records;
- Microsoft onboarding orchestration;
- certificate credential contracts;
- MSAL-backed application-token acquisition;
- tenant-isolated token caching;
- safe Microsoft error translation.

INF-002 extends those foundations rather than replacing them.

## Microsoft service families

The canonical service catalog includes:

| Service | Initial provider | Primary surface | Foundation mode |
|---|---|---|---|
| Microsoft Graph | `microsoft_graph` | Graph v1.0 | governed |
| Entra ID | `microsoft_entra` | Graph v1.0 | governed |
| Exchange Online | `microsoft_exchange_online` | Exchange/Graph | governed |
| SharePoint Online | `microsoft_sharepoint_online` | Graph v1.0 | governed |
| OneDrive | `microsoft_onedrive` | Graph v1.0 | governed |
| Teams | `microsoft_teams` | Graph v1.0 | governed |
| Intune | `microsoft_intune` | Graph v1.0 | governed |
| Defender | `microsoft_defender` | Graph initially; product APIs may be separate providers | governed |
| Purview | `microsoft_purview` | Graph initially | observe/read |
| Service Health | `microsoft_service_health` | Graph v1.0 | observe/read |
| Licensing | `microsoft_licensing` | Graph v1.0 | governed |

A capability selects the service family it needs. Agents do not select arbitrary endpoints directly.

## Permission profiles

Permission profiles are policy data. They are deliberately narrower than the total permissions an application might technically be able to request.

Initial profiles include:

- `directory-read`
- `identity-investigation-read`
- `mail-investigation-read`
- `device-compliance-read`
- `security-investigation-read`
- `collaboration-permissions-read`

All initial profiles are read-only. A future write-capable profile requires separate governance, documentation, tests, approval classes, and production evidence.

## Request policy

`MicrosoftCloudRequest` describes a provider request before execution.

The foundation enforces:

1. registered service family;
2. registered permission profile;
3. profile-to-service authorization;
4. safe request path construction;
5. read-mode method restrictions;
6. provider-supported operation mode;
7. fail-closed bounded automation;
8. canonical public-cloud base endpoints.

The request builder returns a governed request description. It does not itself acquire a token or perform network I/O.

## Architectural rules

### Identity first

Every Microsoft call must be bound to an approved Jason client boundary and Microsoft tenant identity before a token is acquired.

### Least privilege by profile

Capabilities request named permission profiles, not arbitrary permission strings.

### Provider family, not capability coupling

Capabilities such as mail investigation or identity investigation consume governed Microsoft providers through the orchestrator. They must not embed Microsoft credentials, tenant mappings, or direct provider-to-provider calls.

### Read before write

The first production Microsoft milestone is read-only. Write operations must be introduced as separate governed increments.

### No token exposure

Access tokens, certificates, private keys, refresh material, and Microsoft diagnostic payloads that may contain protected information must not enter normal evidence or logs.

## Planned capability families

The Microsoft platform is intended to support at least:

- Microsoft 365 user investigation;
- Entra identity and access investigation;
- mailbox and mail-flow investigation;
- account-compromise investigation;
- Microsoft 365 offboarding review;
- tenant security-posture review;
- license optimization;
- Teams membership and configuration investigation;
- SharePoint and OneDrive permission investigation;
- Intune device-compliance investigation;
- Defender incident investigation;
- Microsoft service-health correlation.

## Deployment prerequisites

Before live deployment Jason still requires:

1. OpenBao-backed Microsoft certificate credential resolution;
2. AOT-owned production multitenant Microsoft application registration;
3. documented permission-profile-to-consent mapping;
4. durable client-boundary and onboarding storage;
5. a controlled test tenant;
6. live token validation without token display;
7. the first narrow read-only Microsoft resource operation;
8. tenant offboarding and cache-invalidation validation;
9. operational evidence and deployment records.

## Current status

**Foundation built; host deployment not yet performed.**

The service catalog, permission-profile catalog, governed request builder, and fail-closed policy tests are implemented in the repository. No new Microsoft production permission, tenant consent, credential, or live API request is introduced by this increment.
