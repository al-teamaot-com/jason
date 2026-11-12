# Microsoft 365 governed operations: reusable capability design

Status: Source-only development slice; no production registration, consent or Microsoft mutations.

## Goal
Extend the existing Microsoft Graph integration without creating one tool per request.
One governed executor resolves a named, registered operation under the authoritative
Jason client/tenant boundary and exact-action approval. Do not accept arbitrary Graph
URLs, methods or provider tokens from an assistant.

## Reuse
- Microsoft-Graph-Provider.md: tenant onboarding and boundary lifecycle.
- microsoft_graph/service_catalog.py: services and permission profiles.
- orchestrator/connector_invoker.py: governed prepare/plan/invoke lifecycle.
- Kernel Client Boundary Registry: authoritative client/tenant mapping.
- Existing MSAL/OpenBao token layer: tenant-specific credentials and caching.

## Initial operation descriptors
- identity.group.create: POST /v1.0/groups, security or Microsoft 365 groups.
- identity.group.member.add: POST group membership reference, verified object IDs.

Descriptors are NOT executable Graph calls. An execution adapter must independently
check scope and authorization and build fixed provider payloads (including
securityEnabled, mailEnabled, groupTypes) from approved semantic parameters.
Reject role-assignable and dynamic groups, unknown fields, unregistered operations,
privileged membership changes, and client/tenant substitution.

## Permissions
Use separate write-scoped application identity. Verify current least-privilege
Graph permissions for each operation before consent, including Group.Create and
GroupMember.ReadWrite.All and any member-type-dependent requirements. GDAP is not
equivalent to unattended app-only permission in customer tenants.

## Remaining acceptance
1. Implement shared adapter within existing central governed execution-plan flow.
2. Fail closed on invalid boundary, consent, authorization, duplicate and scope drift.
3. Pre-read identity; prevent duplicates and ambiguous objects.
4. Execute exactly once with idempotency and retry classification.
5. Post-read group identity/properties or exact membership from same tenant.
6. Add audit, safe errors, provider fakes, denied cross-tenant and revoked-grant tests.
7. Prove independent deployment with ticket-core regression verification.
8. Obtain governed production release authorization and validate customer consent.

No Microsoft tenant was altered and no production deployment was attempted.
