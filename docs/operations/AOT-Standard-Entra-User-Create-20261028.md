# AOT standard Entra account creation — initial source implementation

**Status:** Source-only, disabled by default; no production runtime registration, permissions, credential issuance or write activation.
**Date:** 2026-10-28
**Capability:** identity.user.create

## Intended technician request

An authenticated AOT technician requests a *standard, cloud-only* Microsoft Entra user for one managed client based on an independently approved onboarding request. A trusted AOT-to-client-to-Microsoft-tenant boundary resolves the tenant, verified managed domains, and cloud-only source of authority. A Microsoft on-premises AD-synchronized or federated-account workflow is deliberately **not** routed through this cloud user creation adapter.

## Supported initial operation

Microsoft Graph v1.0 POST /users (https://learn.microsoft.com/en-us/graph/api/user-post-users) supports account creation with accountEnabled, displayName, mailNickname, userPrincipalName and passwordProfile. This adapter deliberately creates the user **disabled** pending secure credential handoff and final onboarding verification. It does not enable users, allocate or purchase licenses, set privileged roles, grant groups, or configure mailbox delegates.

Input is limited to onboarding_request_id, user_principal_name, display_name, mail_nickname and optional given_name, surname and usage_location. All provider credential, target tenant, Graph URL, source of authority and client mapping parameters are supplied by trusted server-side integrations, not conversation arguments.

## Required controls

- Active authenticated AOT human and authorized client request resolved through a trusted onboarding authority. An arbitrary ticket number alone is not proof of client authorization.
- Source system must be explicitly Entra cloud-only for the managed domain, based on verified client/tenant mapping.
- A sealed initial password must already be available under an approved onboarding-request reference. The connector only reads it, without performing credential creation as a side effect of plan preparation.
- A distinct tenant-scoped Graph user-creation token profile is needed. Microsoft documents application User.Create as the least privileged permission for this operation; provider consent and tenant boundaries must be validated before enabling.
- Preparation searches the exact UPN to prevent duplicates and builds a secret-safe execution-plan fingerprint with the password SHA-256 commitment. It cannot return password values in tool responses or audit events.
- Execution rechecks the exact onboarding authorization, tenant, scoped token profile, credential commitment and duplicate search before **one POST only**.
- A fresh independent Graph read of the returned immutable user object must verify ID, UPN, display name, and disabled state. No automatic retry after ambiguous create outcome.
- Repeat requests for an already-existing UPN fail without creating a second account; a technician must examine an ambiguous previous result rather than having Jason create duplicates.

## Activation still required

1. Implement and test the trusted onboarding authorization resolver, including client-approved requester proof and a managed-domain/source-of-authority registry.
2. Provision a bounded user-create Graph application with appropriate consent, separate from the current directory read token profile.
3. Implement the existing sealed initial-credential read interface and **secure human handoff** after successful verification. Never display passwords in ordinary chat, ticket text, logs, or approval cards.
4. Register the existing canonical identity.user.create capability under JKD-001 and Central Orchestrator with exact J-102 plan binding; this source-only connector is not exposed in the live capability catalog.
5. Run controlled test-user acceptance, audit and duplicate tests in the exact authorized test tenant. Add explicit follow-on user enablement and group/license assignment as separate bounded actions.
6. Release through the existing governed production policy; the active freeze is not overridden by code or by this document.

## Rollback

The profile JASON_ENTRA_STANDARD_USER_CREATE_PROFILE=cloud-user-v1 is required for preparation and execution and is unset by default. Removal of the profile disables this adapter. Already-created test users are not silently deleted; any remediation requires a separately authorized, verified identity operation.

## Current evidence

Mocked Graph contract tests verify no extraneous action fields, approved scope, duplicate prevention, sealed-credential commitment, explicit cloud-only source, provider token profile, disabled account creation, post-write readback and secret-safe results. **No live Graph user has been created.**
