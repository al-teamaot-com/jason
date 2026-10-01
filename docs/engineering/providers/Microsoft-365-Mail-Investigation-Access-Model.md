# Microsoft 365 Mail Investigation Access Model

**Status:** Proposed implementation
**Capability:** CAP-003 – Microsoft 365 Mail Investigation / Missing-Misplaced Email
**Provider family:** Microsoft Graph, Exchange Online, Microsoft Purview Audit
**Mode:** Unattended application access, read-only by default

## 1. Goal

Give AOT technicians a frictionless Jason workflow for mail-delivery and missing-message investigations across managed Microsoft 365 tenants.

A technician should not need to:

- sign in to the client tenant;
- request temporary mailbox FullAccess;
- know a customer administrator credential;
- reconnect Microsoft Graph or Exchange Online interactively;
- approve scopes during an investigation;
- construct Graph, Exchange, or Purview queries;
- know which provider surface answers a specific question.

Client onboarding may require one authorized tenant administrator to grant consent and create the governed Exchange RBAC assignments. Normal technician use after onboarding must be non-interactive.

## 2. Design Decision

Use one AOT-owned multitenant confidential application for the Microsoft 365 **investigation read plane**.

Proposed profile:

`mail-investigation-read`

Authentication:

- certificate-backed client credentials;
- certificate private key stored only in the approved Jason/OpenBao secret boundary;
- tenant-specific token acquisition using the validated Kernel Client Boundary;
- short-lived app tokens cached only in memory;
- no client secrets, user refresh tokens, technician tokens, or customer passwords.

This extends the existing Microsoft Graph application-identity foundation. It does not create a new identity architecture.

## 3. Permission Philosophy

The profile is intentionally **complete for the known investigation workflow**, rather than being reduced so far that technicians repeatedly encounter consent or RBAC blockers.

Least privilege is enforced at four boundaries:

1. **Read identity only** — no mail send, mailbox modification, delegate modification, rule modification, or audit-setting write authority.
2. **Client boundary** — every token is minted for exactly one validated client tenant.
3. **Mailbox content scope** — Graph mailbox content is authorized with Exchange Online Application RBAC, not an unscoped Microsoft Entra `Mail.Read` grant.
4. **Capability surface** — Jason exposes only reviewed operations; callers cannot supply arbitrary Graph URLs, Exchange cmdlets, tenants, app IDs, or tokens.

Future remediation uses a separate mutation identity and separate approval-bound capabilities.

## 4. Pre-Consented Application Permissions

The investigation read identity should receive the following application permissions in each onboarded client tenant.

### Microsoft Graph / Entra

- `AuditLog.Read.All`
  - user sign-in investigation;
  - directory audit reads when required.
- `Directory.Read.All`
  - users;
  - service principals;
  - OAuth delegated permission grants;
  - directory identity correlation needed during investigations.

### Microsoft Purview Audit Search API

- `AuditLogsQuery-Exchange.Read.All`
  - mailbox move/delete/update actor attribution;
  - Exchange mailbox audit events;
  - query creation and result retrieval without technician authentication.

Use the workload-specific Exchange audit permission rather than `AuditLogsQuery.Read.All` unless CAP-003 later requires cross-workload audit searches.

### Exchange Online PowerShell / REST management

- Office 365 Exchange Online application permission: `Exchange.ManageAsApp`.
- The client-tenant service principal must be assigned to a custom Exchange RBAC role group described below.

### Exchange Online Application RBAC for mailbox content

- `Application Mail.Read`
  - assigned through Exchange Online RBAC for Applications;
  - scoped to the approved mailbox population.

Do **not** also grant an unscoped Microsoft Entra `Mail.Read` or `Mail.ReadBasic.All` application permission. Exchange RBAC and Entra application grants are additive; an unscoped grant would defeat the mailbox resource scope.

## 5. Mailbox Resource Scope

CAP-003 must support investigations for any normal managed mailbox in an onboarded client tenant without asking a technician to alter mailbox permissions.

Recommended production scope:

- user mailboxes;
- shared mailboxes;
- other explicitly supported mailbox classes required by AOT support.

Exclude by default where practical:

- discovery/system mailboxes;
- arbitration/system recipients;
- unsupported special-purpose mailboxes.

The onboarding implementation should create and validate an Exchange Application RBAC management scope that represents the supported mailbox population.

If a client contract requires narrower scope, the Kernel Client Boundary may reference a client-specific approved scope.

## 6. Exchange Read Role Group

Create one client-local Exchange role group for the service principal:

`Jason Mail Investigation Read`

The role group must contain only read/query capabilities needed by CAP-003.

Required runtime command families include:

- `Get-MessageTraceV2`
- `Get-MessageTraceDetailV2`
- `Get-Mailbox`
- `Get-Recipient`
- `Get-InboxRule` including `-IncludeHidden`
- `Get-EXOMailboxPermission`
- `Get-EXORecipientPermission`
- `Get-TransportRule`
- `Get-MobileDevice`
- `Get-MobileDeviceStatistics` / `Get-EXOMobileDeviceStatistics`
- other read-only Exchange commands proven necessary by the CAP-003 acceptance test.

The onboarding implementation should derive custom roles from supported Exchange parent roles and remove all unneeded role entries. No `Set-*`, `New-*`, `Add-*`, `Remove-*`, `Enable-*`, `Disable-*`, `Release-*`, or other modifying command should exist in the read role group.

The exact management-role parents and role entries must be discovered and validated in the AOT tenant with Exchange RBAC before production onboarding is generated.

## 7. Quarantine Handling

Message trace should be the authoritative first test for whether Exchange accepted, delivered, redirected, failed, or quarantined a message.

Direct quarantine inspection is a separate provider concern because app-only least-privilege support for quarantine cmdlets is not as cleanly documented as the Graph/Exchange mailbox read surfaces.

CAP-003 v1 should:

1. classify quarantine from authoritative trace evidence;
2. return quarantine identifiers/details available from the trace;
3. use a separately approved quarantine-read capability only when a supported non-interactive permission model is production-proven.

Do not broaden the investigation identity to Exchange Administrator or Global Administrator solely to avoid this one edge-case blocker.

## 8. Purview Audit Strategy

Use the Microsoft Purview Audit Search Graph API rather than requiring a technician-bound `Search-UnifiedAuditLog` session.

Jason should:

1. create an audit query for the exact time range and Exchange operations;
2. poll the query state with bounded retry;
3. retrieve records;
4. correlate mailbox owner, actor, IP, client/app metadata, operation, subject/message identifier, and folder where available;
5. return an explicit telemetry gap when the event predates audit coverage or the client license/retention does not contain the record.

Relevant operations include:

- `Move`
- `MoveToDeletedItems`
- `SoftDelete`
- `HardDelete`
- `Update`
- `UpdateInboxRules`
- other Exchange record types proven useful in acceptance testing.

## 9. Technician Experience

Target interaction:

`Jason, investigate missing email for <client>, mailbox <mailbox>, from <sender>, subject <subject>, around <time>.`

The technician authenticates only to Jason/AOT.

Jason resolves:

- AOT technician identity and authority;
- Autotask company/client;
- validated Microsoft tenant boundary;
- approved investigation profile;
- client-local service principal;
- correct provider surface;
- all application tokens.

No Microsoft sign-in prompt should appear during normal investigations.

## 10. One-Time Client Onboarding

Extend the existing Microsoft client onboarding flow to support `mail-investigation-read`.

One authorized client administrator completes the onboarding once.

The onboarding workflow must:

1. resolve and validate the client tenant ID;
2. create or confirm the local enterprise application/service principal;
3. grant tenant admin consent to the approved application permissions;
4. register the service principal inside Exchange Online where required;
5. create/validate the `Jason Mail Investigation Read` Exchange role group;
6. create/validate Exchange Application RBAC `Application Mail.Read` scope;
7. assign the client service principal to the required Exchange roles/scopes;
8. test Graph directory reads;
9. test sign-in read;
10. test one mailbox Graph read against an approved test mailbox;
11. prove a system/out-of-scope mailbox is rejected when scope is configured to exclude it;
12. test Exchange message trace;
13. test hidden Inbox-rule read;
14. test mailbox delegation read;
15. test mobile-device read;
16. test Purview Exchange audit query;
17. persist only non-secret boundary/consent metadata;
18. mark the profile `validated` only after all required checks pass.

After onboarding, technician investigations require no client reauthentication.

## 11. Validation State

Each client/profile boundary should retain capability-specific validation flags, for example:

- `graph_directory_read`
- `entra_signin_read`
- `graph_mail_read`
- `exchange_trace_read`
- `exchange_mailbox_config_read`
- `exchange_delegate_read`
- `exchange_mobile_read`
- `purview_exchange_audit_read`

A profile is production-ready only when required flags are healthy.

License-dependent evidence should be reported separately from permission failures.

## 12. Runtime Behavior

For each investigation:

1. derive the client from governed context;
2. resolve the validated Microsoft boundary;
3. acquire app-only tokens for the required Microsoft resource;
4. execute only registered CAP-003 reads;
5. never expose tokens or certificates;
6. persist correlation IDs and safe evidence;
7. classify provider failures distinctly from authoritative empty results;
8. do not ask the technician to reauthenticate when consent is already valid.

If consent is revoked or a client boundary is disabled, fail closed with a client-onboarding/remediation status rather than falling back to technician credentials.

## 13. Mutation Separation

The read identity must not have:

- `Mail.ReadWrite`;
- `Mail.Send`;
- mailbox delegation write;
- Inbox-rule write;
- mailbox forwarding write;
- audit-setting write;
- OAuth grant revocation;
- device removal;
- message move/update/delete authority.

Future remediation should use a separate identity/profile such as:

`mail-investigation-remediation`

Every mutation remains exact-target bound, approval-controlled, audited, and read-back verified.

## 14. Certificate and Consent Lifecycle

The AOT application certificate must support overlapping rotation.

Certificate rotation must not require client tenant reconsent when the application ID and permission set are unchanged.

Permission-profile expansion **does** require client tenant admin consent to the new permission set. Therefore the initial production onboarding should include the full known CAP-003 read permission set so technicians do not encounter later scope prompts during normal work.

A quarterly technology-steward review should check Microsoft permission/API changes and reduce permissions where possible without breaking the approved workflow.

## 15. Offboarding

Client offboarding must:

1. disable the Kernel boundary immediately;
2. reject new token requests;
3. clear matching in-memory token caches;
4. remove/revoke the client enterprise application consent;
5. remove Exchange service-principal role-group membership and Application RBAC assignments;
6. verify Graph/Exchange/Purview access is denied;
7. preserve non-secret audit evidence.

## 16. Acceptance Test

Use AOT first.

The test must prove, without an interactive Microsoft technician login:

1. exact-tenant token acquisition;
2. message trace V2;
3. transport-rule evidence;
4. mailbox forwarding read;
5. hidden Inbox-rule read;
6. exact message location via Graph;
7. read/unread and message metadata;
8. FullAccess, SendAs, and SendOnBehalf reads;
9. Exchange audit-setting read;
10. mailbox move/delete actor correlation through Purview Audit Search API;
11. sign-in history;
12. OAuth grant/service-principal correlation;
13. Exchange ActiveSync/mobile device state;
14. retention/archive/hold state;
15. client boundary rejection;
16. mailbox resource-scope rejection for an excluded mailbox;
17. no write capability in the read identity.

Use Lori's September 30, 2026 toner case as the reference workflow, but create a controlled new test message so current auditing can prove actor attribution.

## 17. Implementation Sequence

1. Update the `mail-investigation-read` permission profile.
2. Add token acquisition support for Exchange Online and Purview resources using the existing certificate credential.
3. Build the Exchange read adapter.
4. Expand the Graph mailbox reader to folder search/location and mailbox metadata.
5. Build sign-in and OAuth-grant readers.
6. Build Purview Audit Search reader.
7. Extend Microsoft onboarding to install and validate the Exchange role/scopes.
8. Add CAP-003 orchestration and result model.
9. Run AOT controlled acceptance.
10. Onboard one managed client pilot.
11. Promote only after client-boundary and no-write tests pass.
