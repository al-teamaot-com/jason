# Autotask Write Execution Profile Runbook

**Updated:** 2026-09-16  
**Status:** Active provider-identity/runbook; first bounded live ticket-update pilot completed  
**Current checkpoint:** `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`

## Purpose

This runbook defines the provider-side identity required for Jason's governed Autotask Ticket and TicketNote mutation surface. It is intentionally separate from the accepted `autotask.readonly` execution identity.

Creating or changing an Autotask API user/security level is a consequential provider administration change. Do not perform it as an incidental part of source deployment. The AOT Owner/Autotask administrator must approve live provider configuration changes before credentials are provisioned to Jason.

The first bounded live `service.ticket.update` pilot has now been completed successfully on controlled ticket `T20191013.0001`. That acceptance does not convert this runbook into standing authorization for future mutations.

## Authority model

A mutation is allowed only when all of these are true:

1. Jason authenticates the human requester.
2. Jason authorizes the action under Owner/Admin/Tech/RO policy and client/resource scope.
3. The requester maps to exactly one active Autotask Resource.
4. The requester's effective Autotask security profile permits the concrete action.
5. The dedicated API-only execution identity also has the provider permission required for the entity/action.
6. The API-only execution identity is allowed to impersonate that resource for that entity/action.
7. The same `ImpersonationResourceId` is used for preflight and mutation.
8. Jason has the exact capability grant and any required per-execution approval for the exact request.
9. The concrete Autotask operation succeeds and the resulting durable state is verified through the governed read path.

The requester's Autotask profile is the maximum requester authority. The API-only execution profile is an additional provider-side execution boundary, not a source of requester authority.

## Separate API-only identity

Use a **copy** of the Autotask API User (system) / API-only security level and reduce it to this integration's needs. Do not broaden or repurpose the existing Jason read-only API identity.

Suggested labels:

- Security level: `Jason API - Ticket Mutation`
- API-only resource: `Jason Ticket Mutation API`
- Tracking identifier: Custom/Internal Integration for Jason/AOT

Autotask REST access requires an API-only resource and a tracking/integration identifier. The API-only resource has no UI access.

## Minimum pilot permission intent

The custom API-only security level should grant only the permissions needed for the Ticket/TicketNote slice:

- Service Desk / Ticket access sufficient for the activated Ticket add/edit operations.
- Ticket Note permissions sufficient for the activated TicketNote create/update operations.
- The minimum Resource query visibility required to resolve the authenticated requester's Autotask Resource by exact email.
- Resource impersonation enabled only as needed for the approved surface.
- Impersonation permissions for **Ticket** and **TicketNote** add/edit operations only.
- No delete permission for Tickets or TicketNotes; the REST entities do not support delete and Jason exposes no delete capability.
- No unrelated CRM, contracts, billing, invoicing, projects, purchasing, inventory, or administration mutation rights.

Where Autotask exposes `All`, `Mine`, territory, line-of-business, or similar restrictions, use the narrowest setting that still allows the approved AOT operating model. Jason must treat `Restricted` provider access as conditional rather than as universal permission.

## Requester-side requirement

For provider-native resource impersonation to work, the security level assigned to the human resource being impersonated must allow that resource to be impersonated.

The requester's effective Autotask security profile must also permit the actual Ticket/TicketNote operation. If the human cannot perform an operation in Autotask under that profile, Jason must not acquire that authority on the requester's behalf.

The first live acceptance used Al only. Adding Lindsey, Adam, or other users to a mutation-capable pilot requires their own Jason role/grant plus their own effective Autotask profile; the first pilot is not a blanket authorization for other principals.

## Ticket-specific provider behavior

Autotask states that Ticket REST operations respect the logged-in end user's granular Ticket View/Add/Edit security permissions, with provider-specific handling for some restricted settings. Therefore:

- do not infer permission from the fact that the Ticket endpoint exists;
- use impersonated `entityInformation` preflight for create/update when applicable;
- treat `None` as a hard deny;
- treat `Restricted` as conditional;
- let the concrete mutation remain the final provider enforcement point;
- verify the resulting ticket afterward through the governed read path.

## TicketNote-specific provider behavior

Autotask states that TicketNotes respect the user's ticket-note edit permissions. Ticket note titles may also be required by the Ticket Category configuration.

The pilot/runbook must therefore:

- preflight TicketNotes separately from Tickets;
- populate provider-required note fields (`ticketID`, `description`, `noteType`, `publish`, and `title` when the ticket category requires it);
- avoid assuming that Ticket permission automatically implies TicketNote permission;
- avoid rewriting rich-text note bodies during update unless the intended change explicitly accepts Autotask's text-only REST behavior.

## Credential handling

Provision the dedicated Autotask API credential locally through Jason's canonical secret lifecycle. Do not paste credential values into chat, GitHub, tickets, documentation, or shell command arguments.

The canonical logical secret is `autotask.write`, stored under the dedicated OpenBao production write path and read at runtime through the dedicated write AppRole.

Provisioning or rotating the secret does **not** by itself grant requester authority, activate a capability, satisfy a Jason exact grant, or satisfy per-execution approval.

## Credential-safe validation

Before a new provider configuration is promoted, validate without exposing credential values:

- dedicated write secret resolves only through the write credential boundary;
- ordinary read path continues using `autotask.readonly`;
- requester maps to exactly one active Autotask Resource;
- provider-native impersonation remains active;
- entity/action preflight is acceptable;
- no fallback to a service-account requester occurs;
- the intended active Jason capability/grant/approval path is available;
- provider mutation can be independently read back through the governed read identity.

`None`, ambiguous requester mapping, missing impersonation, unavailable dedicated write credentials, or any unexpected provider response blocks the mutation.

## First bounded live mutation — completed

The original source/design plan called for a disposable create/update/note sequence. The accepted live pilot was narrowed further before execution to one reversible update on an existing controlled test ticket.

Completed acceptance target:

- company: **XYZ Test Company** (`companyID=1158`);
- ticket: `T20191013.0001` (`id=8870`, title `test ticket`);
- field: `priority`;
- pre-mutation value: `3`;
- approved mutation: `3` → `2`;
- capability: `service.ticket.update`;
- due date: unchanged;
- direct provider access: disabled;
- post-mutation governed readback: required and completed.

A fresh governed read on 2026-09-16 returned `priority=2`, confirming durable state after the mutation.

Do **not** repeat the same mutation merely to demonstrate the path again. The accepted proof belongs in `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md` and Jason's audit trail.

## Future live mutation boundary

Any future Autotask write remains a new governed request. Before executing:

1. resolve the target through the governed read path;
2. record the exact current state/reversible field when applicable;
3. confirm the capability is active;
4. confirm the requester's exact Jason grant and Autotask authority;
5. obtain the required per-execution approval bound to the exact request;
6. execute only through Jason's governed action path;
7. do not broaden target, field, or scope after approval;
8. require provider success classification;
9. independently read back the resulting durable state through the governed read path;
10. preserve audit/correlation evidence without credential material.

Broader company scope, additional mutation capability families, and additional principals remain separate governed changes.

## Official provider basis

This runbook is based on the Autotask REST/security model for:

- REST API security and authentication;
- REST API best practices;
- resources/entities that support impersonation;
- `entityInformation`;
- Tickets;
- TicketNotes.

Revalidate provider requirements before materially expanding the mutation surface if Autotask changes its API/security model.
