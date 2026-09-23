# Microsoft Graph Technician Onboarding Procedure

**Status:** Design
**Applies to:** Microsoft Graph Directory Read onboarding

## Goal

A technician should be able to connect a managed Microsoft 365 tenant without manually engineering an Entra application relationship.

The expected technician effort is:

1. select the client;
2. confirm the domain;
3. choose the approved access profile;
4. complete one Microsoft administrator consent screen;
5. review Jason's validation result.

## Planned Command

`jason microsoft onboard-client`

## Guided Questions

Jason should ask:

- Which Jason client is being connected?
- What is the client's Microsoft primary domain?
- Which approved profile is required?

For Milestone 1, the only selectable profile is:

`Directory Read`

## Plain-Language Permission Summary

Before generating the consent link, Jason should display:

### Directory Read

Allows Jason to read:

- users;
- groups;
- organization details;
- verified domains;
- license information.

Does not allow Jason to:

- create or modify users;
- create or modify groups;
- reset passwords;
- read mailbox content;
- send email;
- read SharePoint files;
- read Teams messages;
- make security changes.

## Technician Confirmation

The technician must confirm:

- the correct client was selected;
- the correct Microsoft domain was entered;
- the client authorized the onboarding;
- the person completing consent has authority in that tenant;
- the displayed access profile matches the intended service.

## Consent Flow

Jason should:

1. create an expiring onboarding transaction;
2. generate the Microsoft admin-consent URL;
3. show the client, domain, profile, and expiration;
4. open the URL or provide one copyable link;
5. wait for the callback;
6. validate state and tenant;
7. test access automatically;
8. display the result.

## Successful Result

Jason should display a result similar to:

Microsoft Graph onboarding completed.

Client: FaithFormation
Tenant domain: faithformation.org
Tenant ID: validated
Profile: Directory Read
Admin consent: verified
Organization read: passed
Domain read: passed
License read: passed
User read: passed
Group read: passed
Write permissions: not granted

## Failed Result

Failure output should explain the next action without exposing technical secrets.

Examples:

- Consent was denied by the tenant administrator.
- The Microsoft tenant did not match the selected client.
- The consent transaction expired.
- Jason could not obtain an application token.
- The tenant granted consent, but a required read test failed.
- The client appears to be connected to a different Microsoft tenant.

The output should include a safe correlation ID for escalation.

## Validation Evidence

Jason should retain:

- client identifier;
- tenant identifier;
- profile;
- consent time;
- validation time;
- validation operation names;
- pass or fail result;
- safe error classifications;
- audit correlation ID.

Jason should not retain sample user, group, mailbox, or file content as onboarding evidence.

## Revalidation

Planned command:

`jason microsoft validate-client <client>`

Revalidation should:

- confirm the mapping remains enabled;
- obtain a new tenant token;
- repeat the approved validation operations;
- update the last validation time;
- report consent or permission drift.

## Offboarding

Planned command:

`jason microsoft offboard-client <client>`

The technician should see:

- the mapped tenant;
- the active permission profile;
- the effect of offboarding;
- whether Microsoft consent revocation was confirmed.

Jason must disable the local mapping before attempting remote revocation.

## Support Escalation

When automated onboarding cannot complete, Jason should generate a concise escalation package containing:

- client;
- domain;
- safe tenant ID when known;
- current onboarding step;
- Microsoft error code;
- Jason correlation ID;
- recommended next action.

No token, secret, authorization code, or private key may appear in the package.

## Application Credential Handling

The technician onboarding workflow does not ask the technician or
client administrator for an application credential.

Jason's AOT-owned certificate identity is provisioned centrally.

The technician:

- selects the client;
- confirms the domain and access profile;
- completes the administrator-consent workflow;
- reviews the validation result.

The technician does not:

- create a client secret;
- upload a certificate;
- copy a private key;
- copy an access token;
- manage token caching;
- enter the application ID manually during ordinary onboarding.

## Current Implementation Status

The internal onboarding foundation now supports:

- creation of a Kernel onboarding transaction;
- signed, expiring, single-use state;
- tenant-specific Microsoft administrator-consent URLs;
- safe consent callback parsing;
- tenant UUID validation;
- duplicate client and tenant protection;
- creation of a pending client-boundary record;
- certificate-based token-provider contracts;
- rejection of boundaries that are not validated.

The technician-facing CLI command is not yet implemented.

The workflow is therefore not yet available for routine technician use.

Before release, Jason still requires:

- durable transaction and boundary storage;
- production callback hosting;
- OpenBao-backed certificate resolution;
- production application registration;
- automated token and Graph validation;
- plain-language CLI output;
- controlled offboarding;
- operational documentation.
