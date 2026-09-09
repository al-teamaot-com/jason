# INF-010 Microsoft Cloud Deployment Checklist

**Status:** PILOT FOUNDATION VALIDATED FOR APPROVED EXACT-USER DIRECTORY LOOKUP  
**Last reconciled:** 2026-08-11

## Goal

Deploy and validate the Microsoft Cloud Platform Foundation without granting production Microsoft permissions or making a live Microsoft API call until the host and governance prerequisites are satisfied.

The 2026-08-11 pilot completed the approved exact-user directory lookup path used to resolve the authenticated Teams user to a current mailbox address. This checklist now records both the deployment controls and the completed pilot evidence.

## Phase 1 — Repository validation

1. Synchronize the Microsoft foundation/runtime branch.
2. Run Microsoft connector tests, including token, tenant-boundary, user-directory, identity-binding, and runtime composition coverage.
3. Run the applicable Microsoft foundation checks.
4. Confirm preflight checks do not contact Microsoft or acquire a token unless explicitly entering the approved live-validation phase.
5. Run Kernel, release, documentation, and whitespace validation.

### Pilot evidence

Focused Microsoft identity bridge/runtime validation passed before live deployment, including a 66-test governed set covering user directory resolution, tenant token adaptation, certificate-token handling, durable client boundaries, Teams identity binding, conversation action intent, email request creation, runtime composition, and deployment contracts.

## Phase 2 — Secret-provider binding

1. Define the OpenBao logical secret contract for the Microsoft certificate credential.
2. Store the private key and certificate outside Git and normal evidence.
3. Record the certificate thumbprint and generation as non-secret metadata.
4. Validate credential resolution without printing private key material.
5. Runtime must not fall back to environment variables, transport-supplied credentials, or historical certificate files.

### Pilot evidence

Canonical logical secret:

```text
microsoft_graph.directory_read
```

Canonical provider reference:

```text
secret/data/connectors/microsoft-graph/production/directory-read
```

Required fields:

```text
private_key_pem
certificate_pem
certificate_thumbprint
generation
```

Verification returned:

```text
field_contract_valid: true
runtime_access_active: true
runtime_token_persisted: false
secret_values_printed: false
status: pass
```

The dedicated AppRole is mounted read-only into `jason-runtime`; the host artifacts remain root-owned with runtime-group read access only.

## Phase 3 — Microsoft application registration

1. Create or validate the AOT-owned application registration.
2. Register the approved certificate public key.
3. Configure only the approved permission profile.
4. Record application ID and non-secret registration metadata.
5. Do not grant broader Exchange, Intune, Defender, directory, or write permissions merely for convenience.

### Pilot evidence

Approved pilot registration metadata:

```text
Tenant ID: f7054323-d52b-4863-8c2f-1898f0b6077c
Application ID: c94301b7-7194-46ab-aab7-94f9366f51a9
Service principal ID: f784d32d-1d6f-4080-97d4-5efa194a14ed
Primary domain: teamaot.com
```

For the exact-user Graph lookup, the least-privileged application permission used by the pilot is:

```text
User.Read.All
```

The runtime profile remains named `directory-read` for the current pilot implementation, but that name does not imply use of broader `Directory.Read.All`.

## Phase 4 — Controlled tenant boundary

1. Select one controlled Microsoft tenant.
2. Record administrator consent or approved adoption evidence.
3. Validate tenant ID, application ID, service principal metadata, and permission profile.
4. Persist the client boundary using the approved durable repository before production use.
5. Require `VALIDATED` state before token acquisition.
6. An authenticated Teams tenant may identify only the external tenant; it may not supply or override application ID, provider, profile, or credentials.

### Pilot evidence

Durable boundary:

```text
Internal client ID: client-aot-internal
Provider: microsoft_graph
External tenant ID: f7054323-d52b-4863-8c2f-1898f0b6077c
Primary domain: teamaot.com
Profile: directory-read
Application ID: c94301b7-7194-46ab-aab7-94f9366f51a9
Status: validated
```

The boundary is stored in the durable SQLite client-boundary repository. The boundary contains identifiers and governance state only; it does not store credentials, certificates, or access tokens.

## Phase 5 — Live token validation

1. Acquire an application token through the governed MSAL certificate provider.
2. Never print or persist the access token in evidence.
3. Record only safe metadata: tenant, application, profile, certificate thumbprint/generation class, expiration class, and success/failure classification.
4. Validate tenant and application values returned by the token provider against the governed boundary.
5. Fail closed on boundary mismatch, credential failure, provider error, or invalid token metadata.

### Pilot evidence

A fresh application token was acquired in memory only. The observed roles included `User.Read.All`. The token itself was not printed or persisted.

## Phase 6 — First Microsoft read

The first live resource call must be narrow, read-only, and tied to an approved purpose.

The approved pilot used an exact user lookup for the already-authenticated Teams object. The user-directory reader requests only the identified user and resolves the mailbox from `mail`, with `userPrincipalName` used only as fallback. It verifies the returned object ID and rejects an explicitly disabled account.

### Pilot evidence

Authenticated object:

```text
bee80bdc-ffb0-4c50-b453-c09d4d411f5f
```

Live Graph lookup resolved:

```text
mail: al@teamaot.com
accountEnabled: true
```

The running `jason-runtime` container subsequently proved the complete governed no-send path:

```text
authenticated Teams tenant/object
-> validated Jason client boundary
-> JKD-003/OpenBao certificate credential
-> MSAL application token
-> Microsoft Graph exact-user lookup
-> al@teamaot.com
```

No email was sent during the identity proof.

## Phase 7 — Conversational identity use

When a Teams user says `me`, the address must be resolved from the currently authenticated Microsoft tenant/object identity. A static email binding or transport-supplied email must not override live directory resolution when the governed directory reader is configured.

The Teams conversation layer may consume the resulting bound principal email as identity context, but it may not call Microsoft Graph or any consequential provider directly. Downstream actions still require normal Jason capability resolution, policy, authority, and orchestration.

### Pilot evidence

The live Teams command:

```text
send me an email
```

resolved `me` to the authenticated user and then continued through the Central Orchestrator and CAP-007. Mailbox receipt independently confirmed delivery.

Full proof:

`docs/sessions/Teams-CAP-007-End-to-End-Operational-Proof-2026-08-11.md`

## Stop conditions

Stop and deny deployment if any of the following occurs:

- client boundary is absent, pending, revoked, failed, or offboarded;
- authenticated tenant does not match the governed boundary;
- returned Microsoft object ID does not match the authenticated object;
- credential material cannot be resolved through the approved secret provider;
- requested permission profile is not registered;
- requested service is outside the permission profile;
- requested operation exceeds the approved mode;
- certificate, tenant ID, or application ID is invalid;
- token or private-key material would be printed or written to normal evidence;
- production consent includes permissions outside the approved profile without governance review;
- a write operation is attempted through the read-only directory milestone;
- a downstream action attempts to bypass the Central Orchestrator;
- runtime attempts to use a file/env/transport credential fallback after OpenBao failure.

## Governance conclusion

The Microsoft foundation is approved for the current single-host pilot exact-user identity-enrichment scope. Microsoft authentication and directory data remain identity evidence, not execution authority. Expansion to broader directory reads, mail send through Graph, tenant administration, Intune, Defender, Exchange mutation, or other consequential Microsoft operations requires separate capability registration, permission review, governance approval, and evidence.
