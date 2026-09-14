# Autotask Write Execution Profile Runbook

## Purpose

This runbook defines the provider-side identity required for Jason's governed Autotask Ticket and TicketNote mutation pilot. It is intentionally separate from the accepted `autotask.readonly` execution identity.

Creating or changing an Autotask API user/security level is a consequential provider administration change. Do not perform it as an incidental part of source deployment. The AOT Owner/Autotask administrator must approve the live provider configuration before credentials are provisioned to Jason.

## Authority model

A mutation is allowed only when all of these are true:

1. Jason authenticates the human requester.
2. Jason authorizes the action under Owner/Admin/Tech/RO policy and client/resource scope.
3. The requester maps to exactly one active Autotask Resource.
4. The requester's effective Autotask security profile permits the concrete action.
5. The dedicated API-only execution identity also has the provider permission required for the entity/action.
6. The API-only execution identity is allowed to impersonate that resource for that entity/action.
7. The same `ImpersonationResourceId` is used for preflight and mutation.
8. The concrete Autotask operation succeeds and the resulting durable state is verified.

The requester's Autotask profile is the maximum requester authority. The API-only execution profile is an additional provider-side execution boundary, not a source of requester authority.

## Create a separate API-only identity

Use a **copy** of the Autotask API User (system) / API-only security level and reduce it to this integration's needs. Do not broaden or repurpose the existing Jason read-only API identity.

Suggested labels:

- Security level: `Jason API - Ticket Mutation`
- API-only resource: `Jason Ticket Mutation API`
- Tracking identifier: Custom/Internal Integration for Jason/AOT

Autotask REST access requires an API-only resource and a tracking/integration identifier. The API-only resource has no UI access.

## Minimum pilot permission intent

The custom API-only security level should grant only the permissions needed for the first Ticket/TicketNote slice:

- Service Desk / Ticket access sufficient for Ticket **Add** and **Edit** operations.
- Ticket Note permissions sufficient for TicketNote **Create** and **Update** operations.
- The minimum Resource query visibility required to resolve the authenticated requester's Autotask Resource by exact email.
- Resource impersonation enabled only as needed for the pilot.
- Impersonation permissions for **Ticket** and **TicketNote** add/edit operations only.
- No delete permission for Tickets or TicketNotes; the REST entities do not support delete and Jason exposes no delete capability.
- No unrelated CRM, contracts, billing, invoicing, projects, purchasing, inventory, or administration mutation rights.

Where Autotask exposes `All`, `Mine`, territory, line-of-business, or similar restrictions, use the narrowest setting that still allows the approved AOT operating model. Jason must treat `Restricted` provider access as conditional rather than as universal permission.

## Requester-side requirement

For provider-native resource impersonation to work, the security level assigned to the human resource being impersonated must allow that resource to be impersonated. For the first live acceptance, that resource is Al only.

Al's effective Autotask security profile must also permit the actual Ticket/TicketNote operation. This is intentional: if Al cannot perform an operation in Autotask under his profile, Jason must not acquire that authority on his behalf.

Do not add Lindsey or Adam to the live mutation acceptance until Al's path has passed. They are intended to begin later as Jason `Tech` users, with their own Autotask profiles remaining authoritative maximums.

## Ticket-specific provider behavior

Autotask states that Ticket REST operations respect the logged-in end user's granular Ticket View/Add/Edit security permissions, with provider-specific handling for some restricted settings. Therefore:

- do not infer permission from the fact that the Ticket endpoint exists;
- use impersonated `entityInformation` preflight for create/update;
- treat `None` as a hard deny;
- treat `Restricted` as conditional;
- let the concrete mutation remain the final provider enforcement point;
- verify the resulting ticket afterward through the governed read path.

## TicketNote-specific provider behavior

Autotask states that TicketNotes respect the user's ticket-note edit permissions. Ticket note titles may also be required by the Ticket Category configuration.

The pilot must therefore:

- preflight TicketNotes separately from Tickets;
- populate the provider-required note fields (`ticketID`, `description`, `noteType`, `publish`, and `title` when the ticket category requires it);
- avoid assuming that Ticket permission automatically implies TicketNote permission;
- avoid rewriting rich-text note bodies during update unless the intended change explicitly accepts Autotask's text-only REST behavior.

## Credential handling

After the provider identity/security level exists, provision its Autotask API credentials locally on Jason through the canonical secret lifecycle:

```bash
sudo python3 tools/provider_secret.py create autotask_write
```

The command prompts locally for:

- Autotask API username;
- API secret;
- integration/tracking code.

Do not paste those values into chat, GitHub, tickets, documentation, or shell command arguments.

The canonical logical secret is `autotask.write`, stored under the dedicated OpenBao production write path and read at runtime through the dedicated `autotask-write` AppRole. Provisioning this secret does **not** activate write tools or expose mutations through MCP.

## Credential-safe validation sequence

Before entering credentials, the source/operator contract can be checked without provider contact:

```bash
python3 tools/provider_secret.py create autotask_write --check-only
```

After the provider identity and secret are provisioned:

```bash
sudo python3 tools/provider_secret.py verify autotask_write
```

Then run the existing provider-native impersonation acceptance for Al using its documented `--live-read` mode, followed by the mutation-readiness probe:

```bash
sudo python3 tools/autotask_mutation_readiness.py \
  --live-read \
  --principal-id '<AL_JASON_PRINCIPAL_ID>' \
  --correlation-id '<ACCEPTANCE_CORRELATION_ID>' \
  --expected-principal-email 'al@teamaot.com' \
  --evidence-output '/var/lib/jason/acceptance/autotask-mutation-readiness.json'
```

The readiness probe is read-only by construction. It allows provider `GET` requests only. It compiles the future POST/PATCH requests so the exact connector path is exercised, but it never dispatches them; any non-GET provider call is blocked before network I/O.

Expected provider preflight results for the four operations are `All` or an understood/acceptable `Restricted` condition. `None`, ambiguous requester mapping, missing impersonation, unavailable dedicated write credentials, or any unexpected provider response blocks the pilot.

## First live mutation boundary

Do not create or update an Autotask record merely because the readiness probe passes.

The first live acceptance remains a separate explicit approval. After that approval, the intended sequence is:

1. Resolve **XYZ Test Company** uniquely through the governed read path.
2. Create one clearly disposable acceptance ticket under that company.
3. Read it back and verify company, attribution, and requester impersonation evidence.
4. Apply one bounded ticket PATCH and verify it.
5. Create one ticket note and verify it.
6. Apply one bounded update to that pilot-created note and verify it.
7. Record sanitized evidence and leave production write capability disabled unless every check passes.

Production activation, broader company scope, and adding Lindsey/Adam remain later governed changes.

## Official provider basis

This runbook is based on the current Autotask REST documentation for:

- REST API security and authentication;
- REST API best practices;
- Autotask REST API resources / entities that support impersonation;
- the `entityInformation` REST call;
- Tickets;
- TicketNotes.

Revalidate those provider requirements before production activation if Autotask changes its API/security model.
