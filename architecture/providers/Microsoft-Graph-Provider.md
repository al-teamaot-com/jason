# Microsoft Graph Provider

**Provider name:** `microsoft_graph`
**External platform:** Microsoft Graph and Microsoft Entra ID
**Provider owner:** Jason Integration SDK
**Technology Steward:** Microsoft Platform Steward
**Environment:** Multitenant production
**Status:** Design

## 1. Purpose

The Microsoft Graph provider gives Project Jason governed access to approved Microsoft 365 and Microsoft Entra data across managed client tenants.

The provider must make client onboarding simple for technicians while preserving:

- tenant isolation;
- least privilege;
- explicit client approval;
- centralized credential handling;
- complete audit correlation;
- simple offboarding;
- separate read and mutation identities.

## 2. First Milestone

The first milestone implements guided onboarding for one client tenant using the `directory-read` access profile.

The first milestone does not implement a broad Microsoft 365 integration.

### Included

- one AOT-owned multitenant application registration;
- one reviewed Directory Read permission profile;
- tenant-specific administrator consent;
- client-to-tenant mapping;
- consent callback validation;
- application-token validation;
- safe read tests;
- technician-friendly onboarding status;
- technician-friendly offboarding status.

### Excluded

- mailbox content;
- sending email;
- SharePoint content;
- Teams messages;
- security alerts;
- Intune;
- delegated technician sessions;
- GDAP dependency;
- write permissions;
- mutation execution;
- per-client app registrations.

## 3. Application Model

The initial design uses one AOT-owned multitenant application registration for the Directory Read profile.

The application object exists in the AOT home tenant.

Each managed client tenant creates its own local service principal when an authorized administrator grants tenant-wide consent.

Jason uses the same application identity across tenants, but requests tokens from the specific client tenant authority.

## 4. Technician Experience

The target technician command is:

`jason microsoft onboard-client`

The guided flow should:

1. ask the technician to select an existing Jason client;
2. ask for or confirm the Microsoft primary domain;
3. select the approved `directory-read` profile;
4. create a signed, expiring onboarding transaction;
5. generate the tenant-specific Microsoft admin-consent URL;
6. open or display the consent URL;
7. receive and validate the Microsoft callback;
8. confirm the returned tenant matches the intended client;
9. test application-token issuance;
10. test approved Graph reads;
11. store the client-to-tenant mapping;
12. record the validation evidence;
13. display a plain-language completion report.

The technician must not:

- create a client secret;
- copy a certificate;
- create a service principal manually;
- construct Graph URLs;
- enter application permission GUIDs;
- edit JSON;
- store tenant credentials;
- grant permissions beyond the selected profile.

## 5. Initial Access Profile

### Profile name

`directory-read`

### Purpose

Read basic tenant identity, directory, domain, group, and licensing information without mailbox, content, security, or write access.

### Proposed application permissions

| Permission | Purpose |
|---|---|
| `User.Read.All` | Read users |
| `Group.Read.All` | Read groups and approved group properties |
| `Domain.Read.All` | Read verified tenant domains |
| `Organization.Read.All` | Read organization information |
| `LicenseAssignment.Read.All` | Read subscribed license SKUs and assignments |

The final permission list must be verified against the exact implemented operations before app registration.

`Directory.Read.All` is not approved for the first milestone.

## 6. Initial Validation Operations

After consent, Jason should validate:

- `GET /organization`
- `GET /domains`
- `GET /subscribedSkus`
- `GET /users?$top=1`
- `GET /groups?$top=1`

Validation must use minimal field selection where supported.

No client-sensitive record contents should be persisted in the onboarding record.

## 7. Client Tenant Registry

The tenant registry is configuration and governance metadata, not secret storage.

Each record should include:

| Field | Purpose |
|---|---|
| `client_id` | Stable Jason client identifier |
| `tenant_id` | Microsoft tenant identifier |
| `primary_domain` | Verified primary or onboarding domain |
| `profile` | Approved access profile |
| `status` | Pending, validated, failed, revoked, or offboarded |
| `consented_at` | Consent completion time |
| `validated_at` | Last successful validation time |
| `application_id` | Approved Jason app registration ID |
| `service_principal_id` | Client-tenant service principal ID when discoverable |
| `consent_transaction_id` | Correlation to onboarding transaction |
| `last_error_code` | Safe failure classification |
| `offboarded_at` | Offboarding completion time |

No client secrets, tokens, passwords, or certificates may appear in this registry.

## 8. Secrets

The first profile should use a centrally managed certificate-based application identity where practical.

The private key or certificate credential must remain in OpenBao or another approved Jason secret boundary.

The client tenant contributes no secret.

The proposed logical secret is:

`microsoft_graph.directory_read`

The secret contract should contain only the credential material required by the AOT-owned application identity.

Non-secret values such as application ID, tenant IDs, authority host, and Graph base URL belong in governed configuration.

## 9. Consent Security

Each onboarding attempt must use:

- a random transaction identifier;
- a signed state value;
- an expiration time;
- an intended Jason client identifier;
- an intended domain or tenant hint;
- a single-use completion rule;
- callback validation;
- audit correlation.

Jason must fail closed when:

- state is missing or invalid;
- the transaction expired;
- the callback tenant does not match the intended client;
- consent was denied;
- token issuance fails;
- validation operations fail;
- the client is already mapped to another active tenant;
- the tenant is already mapped to another active client without explicit review.

## 10. Offboarding

The target command is:

`jason microsoft offboard-client <client>`

Offboarding should:

1. disable the tenant mapping immediately;
2. prevent new token requests;
3. identify the client service principal;
4. provide or initiate the approved revocation process;
5. verify access no longer works;
6. retain non-secret audit evidence;
7. mark the record offboarded.

Removing the Jason-side mapping alone is not sufficient. Client-tenant consent must also be revoked.

## 11. Audit Requirements

Required audit events include:

- onboarding started;
- consent URL created;
- consent callback received;
- consent validated;
- tenant mapping created;
- token validation completed;
- Graph operation validation completed;
- onboarding failed;
- offboarding started;
- access disabled;
- consent revocation confirmed;
- offboarding completed.

Audit records must not contain:

- access tokens;
- refresh tokens;
- client secrets;
- private keys;
- authorization codes;
- full callback URLs containing sensitive parameters.

## 12. Read and Mutation Boundary

The first milestone is read-only.

Write permissions require:

- a separate application identity;
- a separate permission profile;
- separate consent;
- JIS mutation policies;
- explicit technician authority;
- business reason;
- approval;
- verification;
- rollback or compensating guidance.

Directory Read consent must never imply mutation authority.

## 13. Known Risks

- Microsoft permission requirements may change.
- Tenant consent can be revoked outside Jason.
- Client conditional-access or tenant policies may block onboarding.
- Broad application permissions create substantial exposure if mishandled.
- National-cloud tenants may require different authorities and Graph endpoints.
- Existing client service principals may conflict with onboarding assumptions.

## 14. Technology Steward Review

Review Microsoft identity and Graph changes at least quarterly and before expanding any access profile.

The review must evaluate:

- permission changes;
- deprecated APIs;
- consent-flow changes;
- certificate requirements;
- token-policy changes;
- national-cloud support;
- opportunities to reduce permissions.

## 15. Production Validation

The first provider implementation is not production validated until:

- the AOT multitenant app is created;
- the Directory Read profile is confirmed;
- one test client tenant completes guided consent;
- token issuance succeeds;
- all five validation operations succeed;
- no write access is granted;
- no secret value is exposed;
- offboarding is tested.

## 16. Application Identity and Token Acquisition

The Directory Read profile uses an AOT-owned multitenant confidential
application with a certificate credential.

Token acquisition must:

- use the validated tenant ID from the Kernel Client Boundary Registry;
- use Microsoft Graph `.default` scope only;
- use MSAL rather than custom OAuth implementation;
- use an in-memory application-token cache only;
- reject boundaries that are not active and validated;
- prevent token reuse across clients or tenants;
- prevent token, certificate, or private-key disclosure;
- invalidate cached access following offboarding or certificate rotation.

The authoritative design is:

`Microsoft-Graph-Application-Identity.md`

## 17. Current Implementation Status

The Microsoft Graph provider foundation currently includes:

- technician onboarding design;
- tenant-specific administrator-consent URL generation;
- signed and expiring Kernel onboarding state;
- administrator-consent callback validation;
- Microsoft onboarding orchestration;
- provider-independent client-boundary records;
- certificate credential contracts;
- MSAL-backed application-token acquisition;
- validated-boundary enforcement;
- tenant-isolated in-memory token caching;
- safe token-error translation.

The following are not yet implemented:

- OpenBao-backed certificate retrieval;
- production Microsoft application registration;
- persistent client-boundary storage;
- live tenant onboarding;
- Microsoft Graph resource operations;
- CLI onboarding commands;
- production validation.

The provider remains read-only by design. No mutation identity or write
permission has been introduced.
