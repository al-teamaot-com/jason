# Microsoft Graph Application Identity and Token Acquisition

**Status:** Design
**Provider:** `microsoft_graph`
**Profile:** `directory-read`
**Applies to:** Unattended Microsoft Graph application access

## 1. Purpose

This document defines how Project Jason proves its Microsoft application
identity and acquires tenant-scoped Microsoft Graph access tokens.

The design must preserve:

- least privilege;
- client and tenant isolation;
- centralized credential control;
- short-lived access;
- safe token caching;
- certificate rotation;
- complete audit correlation;
- simple technician onboarding;
- no client-managed secrets.

## 2. Identity Model

Jason uses one AOT-owned multitenant confidential application for the
initial Directory Read profile.

The application object exists in AOT's Microsoft Entra tenant.

Each authorized client tenant contains its own local enterprise
application or service principal after administrator consent.

The application ID is shared across authorized tenants.

The tenant ID used for token acquisition must come from an active,
validated Kernel Client Boundary record.

A client tenant does not provide Jason with a password, secret,
certificate, or refresh token.

## 3. Credential Type

The initial production identity uses a certificate credential.

Client secrets are not approved for the production Directory Read
identity.

The certificate design consists of:

- a private key held only inside an approved Jason secret boundary;
- the matching public certificate registered on the AOT application;
- certificate thumbprint metadata;
- issuance and expiration metadata;
- an explicit rotation procedure.

The private key must never be:

- committed to the repository;
- exposed to technicians;
- placed in client configuration;
- included in logs or audit events;
- passed into an agent context;
- persisted in a token cache.

## 4. Logical Secret Contract

Proposed logical secret:

`microsoft_graph.directory_read`

Proposed OpenBao path:

`secret/data/connectors/microsoft-graph/production/directory-read`

Approved secret fields:

- `private_key_pem`
- `certificate_pem`
- `certificate_thumbprint`

The final field names must be verified against the selected MSAL
certificate credential format before implementation.

Non-secret configuration includes:

- application ID;
- authority host;
- Microsoft Graph base URL;
- approved scope;
- permission profile name;
- client tenant IDs;
- certificate expiration date when safe metadata is sufficient.

## 5. Token Authority

Each token request must use the validated client tenant authority:

`https://login.microsoftonline.com/<tenant-id>`

The following authorities are not approved for provider execution:

- `common`
- `organizations`
- `consumers`
- an unverified domain supplied directly by a capability request.

The tenant ID must be obtained from the Kernel Client Boundary Registry.

The request must fail closed when the boundary is:

- missing;
- pending;
- failed;
- revoked;
- offboarded;
- mapped to another client;
- mapped to another application;
- mapped to an unapproved profile.

## 6. Scope

The only approved token scope for the first milestone is:

`https://graph.microsoft.com/.default`

Individual Graph application permissions must not be supplied in the
runtime token request.

The permissions contained in the resulting application token are the
application permissions already configured on the AOT app registration
and consented in the client tenant.

## 7. Token Acquisition Library

Jason must use Microsoft Authentication Library for Python, MSAL.

Jason must not implement:

- OAuth token signing;
- client assertion creation;
- token endpoint retries;
- token response parsing;
- token cache semantics

when those responsibilities are already provided safely by MSAL.

The token-acquisition layer should wrap MSAL behind a small JIS contract
so the rest of Jason does not depend directly on MSAL implementation
details.

## 8. Token Cache

The initial implementation uses an in-memory application-token cache.

Access tokens must not be written to:

- disk;
- PostgreSQL;
- OpenBao;
- audit logs;
- evidence storage;
- CLI output;
- exception messages.

The cache key must include at least:

- application ID;
- tenant ID;
- scope;
- credential generation or certificate thumbprint.

A cached token must not be returned for another tenant, application,
profile, or certificate generation.

MSAL remains responsible for determining whether its cached token is
usable.

Jason must discard the associated cache when:

- the client boundary is disabled;
- consent is revoked;
- the certificate is rotated;
- the application ID changes;
- the permission profile changes;
- token validation indicates that access is no longer authorized.

## 9. Token Result Contract

The rest of Jason should receive a narrow result object containing only
what is required to make the immediate provider request.

The result may contain:

- access token;
- token type;
- expiration time;
- tenant ID;
- application ID;
- approved scope.

The result must not contain:

- private key;
- certificate contents;
- OpenBao token;
- AppRole SecretID;
- raw MSAL diagnostic responses;
- authorization codes;
- user credentials.

The access token must remain transient and must never enter a structured
audit record.

## 10. Error Handling

The token layer must translate provider errors into safe error
classifications.

Examples include:

- `MICROSOFT_BOUNDARY_NOT_VALIDATED`
- `MICROSOFT_CONSENT_REQUIRED`
- `MICROSOFT_APPLICATION_NOT_FOUND`
- `MICROSOFT_CERTIFICATE_REJECTED`
- `MICROSOFT_PERMISSION_DENIED`
- `MICROSOFT_TOKEN_SERVICE_UNAVAILABLE`
- `MICROSOFT_TOKEN_RESPONSE_INVALID`

Raw token responses and verbose provider descriptions must not be
returned to technicians or agents without sanitization.

Every failure should include a Jason correlation ID.

## 11. Audit Requirements

Required safe audit events include:

- token acquisition requested;
- client boundary authorized;
- application identity resolved;
- token cache hit or miss;
- token acquisition succeeded;
- token acquisition failed;
- certificate rotation detected;
- tenant access disabled.

Audit metadata may contain:

- correlation ID;
- Jason client ID;
- tenant ID;
- application ID;
- permission profile;
- certificate thumbprint;
- safe result classification;
- elapsed time.

Audit metadata must not contain:

- access token;
- private key;
- certificate body;
- client assertion;
- OpenBao credential values;
- raw token endpoint response.

## 12. Certificate Rotation

Certificate rotation must support an overlap period.

The preferred sequence is:

1. generate a new key pair inside the approved secret workflow;
2. add the new public certificate to the AOT application;
3. update the OpenBao credential version;
4. validate token issuance with the new certificate;
5. invalidate the old in-memory token cache;
6. remove the old certificate after the overlap period;
7. record rotation evidence without credential material.

Rotation must not require reconsent in each client tenant when the
application ID and permission set remain unchanged.

## 13. Offboarding

When a client is disabled or offboarded:

1. disable the Kernel boundary before any remote work;
2. reject new token requests immediately;
3. remove associated in-memory cache entries;
4. revoke or remove client-tenant consent;
5. verify that token acquisition or Graph access no longer succeeds;
6. retain safe audit evidence.

## 14. First Implementation Slice

The first implementation PR after this design should provide:

- a token-provider interface;
- a certificate credential contract;
- an MSAL-backed application-token provider;
- boundary validation before token acquisition;
- in-memory caching only;
- dependency injection for tests;
- safe error translation;
- no Graph operation calls.

## 15. First Live Validation

After the application registration, certificate, OpenBao identity, and
token provider exist, the first live validation should:

1. use one authorized test tenant;
2. resolve its validated Kernel boundary;
3. acquire a Graph application token;
4. avoid displaying the token;
5. call one narrow read-only endpoint;
6. record only safe validation evidence;
7. confirm a different or disabled tenant cannot reuse the token.

## 16. Deferred Work

The following remain out of scope:

- delegated user authentication;
- GDAP-based execution;
- national-cloud authorities;
- managed identity;
- federated workload identity;
- persistent distributed token caches;
- Exchange, Teams, SharePoint, Security, or Intune profiles;
- mutation identities;
- write permissions.

## 17. Implementation Status

The certificate-backed token-provider foundation is implemented.

The current implementation provides:

- `MicrosoftCertificateCredential`;
- `MicrosoftCredentialSource`;
- `MicrosoftApplicationToken`;
- `MicrosoftApplicationTokenProvider`;
- `MsalCertificateTokenProvider`;
- tenant-specific Microsoft authorities;
- Microsoft Graph `.default` scope enforcement;
- validated Kernel boundary enforcement;
- profile enforcement;
- application and tenant identifier validation;
- credential-generation-aware MSAL application caching;
- per-client cache invalidation;
- safe Microsoft and credential error translation;
- dependency injection for Microsoft-free automated testing.

The implementation uses MSAL for confidential-client token acquisition
and application-token caching.

No Microsoft Graph resource endpoint is called by the token provider.

## 18. Kernel Boundary Lifecycle Behavior

Token acquisition uses the Kernel Client Boundary Registry as the
authoritative source of client-to-tenant mappings.

| Boundary state | Token-provider behavior |
|---|---|
| `validated` | Eligible for token acquisition when the provider, profile, application ID, and tenant ID are approved |
| `pending` | Rejected as not validated |
| `failed` | Treated as having no active usable boundary |
| `revoked` | Treated as having no active usable boundary |
| `offboarded` | Treated as having no active usable boundary |

The Microsoft provider does not redefine the Kernel lifecycle model.

## 19. Implemented Safe Error Classifications

The token provider currently emits safe classifications including:

- `MICROSOFT_BOUNDARY_NOT_FOUND`
- `MICROSOFT_BOUNDARY_NOT_VALIDATED`
- `MICROSOFT_PROFILE_NOT_APPROVED`
- `MICROSOFT_BOUNDARY_IDENTIFIER_INVALID`
- `MICROSOFT_CREDENTIAL_RESOLUTION_FAILED`
- `MICROSOFT_CERTIFICATE_REJECTED`
- `MICROSOFT_APPLICATION_NOT_FOUND`
- `MICROSOFT_CONSENT_REQUIRED`
- `MICROSOFT_PERMISSION_DENIED`
- `MICROSOFT_TOKEN_SERVICE_UNAVAILABLE`
- `MICROSOFT_TOKEN_RESPONSE_INVALID`
- `MICROSOFT_TOKEN_ACQUISITION_FAILED`

Raw access tokens, credential values, Microsoft diagnostic
descriptions, and private-key material are not included in these
errors.

## 20. Cache Isolation and Invalidation

The implementation caches MSAL confidential-client application
instances in memory.

The cache key includes:

- application ID;
- Microsoft tenant ID;
- approved scope;
- credential generation.

This prevents application instances and token caches from being reused
across tenants, applications, scopes, or certificate generations.

`invalidate_client()` removes matching local application instances and
asks MSAL to remove cached client tokens.

Local cache invalidation does not claim to revoke an already issued
Microsoft access token remotely.

## 21. Remaining Work

The token-provider foundation is not yet production ready.

Remaining work includes:

1. finalize the OpenBao certificate secret contract;
2. implement the OpenBao-backed Microsoft credential source;
3. create the AOT-owned multitenant application registration;
4. generate and register the production certificate;
5. configure the approved Directory Read application permissions;
6. complete administrator consent in a controlled test tenant;
7. persist Kernel boundary and onboarding records outside memory;
8. perform live token acquisition without displaying the token;
9. implement the first narrow Graph read capability;
10. validate offboarding and cache invalidation;
11. record production-validation evidence;
12. complete Microsoft milestone closeout.
