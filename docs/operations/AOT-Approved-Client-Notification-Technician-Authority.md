# AOT technician-approved client-notification authority (source-only)

**Classification:** HIGH RISK (organization role grant, client-visible provider writes, runtime and MCP deployment contract).
**Status:** engineering candidate ONLY, not an authorization to deploy, activate, mutate provider records or send a notification.
**Related:** #2104, #2337, #2365, V4 owner/regular-user identity separation.

## Problem and intended experience

The existing `service.ticket.client.notification.create` provider and source-approved template are operational but the regular authenticated AOT technician is denied `NO_MATCHING_AUTHORITY_GRANT`; the only manual exact-grant API authenticates a *separate* V4 administrator. This is an operations-model gap, not a request to impersonate an admin. A client-visible ticket notification is a normal, technician-facing Autotask task, with native resource permissions and separately governed approval.

**Solution:** use a separately activated, source-controlled JKD-001 organization-role `EXECUTE` grant for *human technicians* limited to the already approved client-notification provider, retaining mandatory per-action approval. This is generic for future approved workflow templates, not a script written for one ticket. No standing broad platform administrator privilege and no administrative login or per-user grant during the routine technician send.

## Three independent guards

1. **Source-controlled activation.** `config/aot-client-notification-technician-profile.json` must declare exactly schema `1.0` and profile `approved-workflow-technician-v1`. Native Release Manager, runtime and MCP deployment verify the same source-defined value; no environment override. Historical source absent/off, recovery and preproduction default OFF; a rollback resets it to empty. Any malformed/unknown/symlinked policy is denied.
2. **Authenticated human and established exact-action approval.** The policy matcher requires an active AOT human identity (not service/autonomy, wrong tenant, disabled or privileged V4 administrator); active MCP-enabled `service.ticket.client.notification.create`; the exact `autotask_client_notification` approved/available external provider; current `EXECUTE` approval-required grant. The real requester must still supply an authenticated imperative; Jason creates its regular short-lived, argument-fingerprinted approval and records the execution and audit under that user's identity. No ability to remove approval requirements or gain arbitrary provider write authority.
3. **Authoritative message and recipient.** The provider re-reads Autotask ticket and ticket contact using native impersonated tech permissions, binds recipient to the contact, honors notification opt-out, and refuses any unpublished source-controlled workflow/template/body. The **XYZ acceptance** uses the stronger exact guard: ticket `T20260926.0088`/ID `141431`, company `1158`, contact `30683022`, recipient `al.bccomputers@gmail.com`, workflow `xyz_client_notification_acceptance`, template `xyz-controlled-client-notification-acceptance-v1`. No other ticket or recipient may use this XYZ workflow.

This *broadens which approved client-notification workflows an eligible AOT technician may invoke*, while retaining the individual templates' own client/contact and source-review restrictions. It is NOT an implicit authorization to send real customer notifications to arbitrary customers. Candidate activation and its risk must be explicitly reviewed at the high-risk release boundary.

## Acceptance / rollback

- Preproduction with actual provider mutations disabled; unit/contract tests for profile on/off, incorrect profile/issuer, missing grant, wrong AOT identity/tenant, V4 admin exclusion, changed provider, disabled/unknown scope, approval missing/expired/mismatched, and any alternate workflow/recipient before provider send.
- Release Manager verifies exact main/candidate/rollback SHA, source scope digest, independent security review, CI, CCC, preproduction, one production transaction and rollback; retains original production freeze and Owner engineering pause after deployment. **This document is not release authorization.**
- Live XYZ: fresh governed pre-read ticket/contact/notification history, one **real approved** native provider send under the human requester, distinct new provider-side notification receipt, actual mailbox receipt, duplicate suppression, ticket readback unchanged, no mistaken Gromelski sends. Negative tests cannot create provider writes.
- Failure to obtain the existing release authorization or any required provider authorization remains fail-closed. Do not bypass Entra, overwrite identity/grant databases, run a direct Autotask API from the host, or mistake an isolated test for live delivery.
- Rollback to known-good source resets `JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE` to empty and denies use of the standing grant. A previously persisted grant remains inert until reactivation of a reviewed policy; explicit revocation is available through governed admin tools.

## Current production boundary

As of this source candidate, actual production has **no** `JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE` activation. The previous controlled XYZ send returned `NO_MATCHING_AUTHORITY_GRANT` and notification history has no new authorized acceptance send. The new policy is only a development fix until an exact candidate receives the required high-risk PM release review and authorization.
