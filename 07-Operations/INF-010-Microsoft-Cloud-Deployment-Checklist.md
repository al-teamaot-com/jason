# INF-010 Microsoft Cloud Deployment Checklist

## Goal

Deploy and validate the Microsoft Cloud Platform Foundation without granting production Microsoft permissions or making a live Microsoft API call until the host and governance prerequisites are satisfied.

## Phase 1 — Repository validation

1. Synchronize the Microsoft foundation branch.
2. Run connector tests, including `test_microsoft_cloud_platform.py`.
3. Run `tools/microsoft_cloud_foundation_check.py`.
4. Confirm the check reports `network_contacted: false` and `token_acquired: false`.
5. Run Kernel, release, documentation, and whitespace validation.

## Phase 2 — Secret-provider binding

1. Define the OpenBao logical secret contract for the Microsoft certificate credential.
2. Store the private key and certificate outside Git and normal evidence.
3. Record the certificate thumbprint and generation as non-secret metadata.
4. Validate credential resolution without printing private key material.

## Phase 3 — Microsoft application registration

1. Create or validate the AOT-owned multitenant application registration.
2. Register the production certificate public key.
3. Configure only the approved initial permission profile.
4. Record application ID and non-secret registration metadata.
5. Do not grant broader Exchange, Teams, Intune, Defender, or write permissions during the first read-only milestone.

## Phase 4 — Controlled tenant onboarding

1. Select one controlled Microsoft test tenant.
2. Start the existing Jason administrator-consent workflow.
3. Complete consent using an authorized Microsoft administrator.
4. Validate the tenant ID and client boundary.
5. Persist the boundary using the approved durable repository before production use.

## Phase 5 — Live token validation

1. Acquire an application token through the existing MSAL certificate provider.
2. Never print or persist the access token in evidence.
3. Record only safe metadata: tenant, application, profile, certificate thumbprint, expiration class, and success/failure classification.
4. Validate cache isolation and client invalidation.

## Phase 6 — First Microsoft read

The first live resource call must be narrow, read-only, and tied to a named capability. Recommended first target:

`GET /organization`

or a single approved user lookup using the `directory-read` profile.

The live read must produce sanitized evidence and must not introduce mutation permissions.

## Stop conditions

Stop and deny deployment if any of the following occurs:

- client boundary is absent, pending, revoked, failed, or offboarded;
- credential material cannot be resolved through the approved secret provider;
- requested permission profile is not registered;
- requested service is outside the permission profile;
- requested operation exceeds the approved mode;
- certificate, tenant ID, or application ID is invalid;
- token or private-key material would be printed or written to normal evidence;
- production consent includes permissions outside the approved profile;
- a write operation is attempted during the read-only milestone.
