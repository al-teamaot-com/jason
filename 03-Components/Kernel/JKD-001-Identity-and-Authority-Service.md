# JKD-001 — Identity and Authority Service

**Status:** Approved for initial implementation  
**Version:** 0.1  
**Project:** Jason Kernel  
**Owner:** Jason Architecture Authority

## 1. Purpose

The Identity and Authority Service establishes who or what is participating in an operation, which organization and client boundary applies, and what authority exists before Jason accesses information or performs work.

Jason must never act merely because an authenticated person or system requested an action.

Before processing a capability request, Jason must determine:

1. Who or what initiated the request.
2. Which organization, tenant, and client boundary applies.
3. In what role the requester is operating.
4. What authority has been delegated.
5. Whether approval is required.
6. Whether the identity and authority evidence is sufficiently trustworthy.

Authentication proves identity. Authorization determines permitted access. Delegation establishes what another party may do on someone's behalf. Policy determines whether the permitted action should actually occur. These concerns must remain separate.

## 2. Responsibilities

The service is responsible for:

- resolving people, applications, systems, devices, organizations, agents, groups, roles, and capabilities into canonical identities;
- mapping external provider identities to Jason identities;
- establishing organization, tenant, and client context;
- resolving roles and delegated authority;
- recording authentication strength and identity confidence;
- issuing short-lived execution contexts for the orchestrator;
- requiring approval where delegated authority is insufficient;
- preventing cross-client and cross-tenant access;
- preserving an auditable record of identity and authority decisions.

The service is not responsible for:

- performing business actions;
- calling operational connectors;
- deciding the technical solution;
- evaluating every business policy;
- storing passwords or API secrets;
- permitting direct agent-to-agent communication.

## 3. Canonical identity types

Version 0.1 supports:

- Person
- Organization
- Service Principal
- System
- Device
- Agent
- Capability
- Group
- Role

An agent is an identity but never an independently authoritative principal. An agent may return structured results or request a named capability only through the orchestrator.

## 4. Canonical identity record

```yaml
identity:
  id: "idn_01JASON..."
  type: "person"
  display_name: "Al Davis"
  status: "active"

  organization_id: "org_aot"
  home_tenant_id: "tenant_aot"

  external_identifiers:
    - provider: "microsoft_entra"
      tenant_id: "..."
      object_id: "..."
    - provider: "autotask"
      resource_id: "..."

  roles:
    - role_id: "role_msp_owner"
      scope: "organization"
      scope_id: "org_aot"

  authentication:
    assurance_level: "high"
    method: "mfa"
    authenticated_at: "2026-07-30T14:00:00Z"

  lifecycle:
    created_at: "..."
    updated_at: "..."
    disabled_at: null

  provenance:
    source: "microsoft_entra"
    confidence: 1.0
```

External identifiers must never become the primary Jason identity. Providers may change without changing Jason's internal identity.

## 5. Authority model

Authority is always scoped.

```yaml
authority_grant:
  id: "grant_..."
  subject_id: "idn_..."
  capability: "ticket.investigate"

  scope:
    organization_id: "org_aot"
    client_id: "client_edgewater"
    resource_type: "ticket"
    resource_id: null

  permission: "execute"
  constraints:
    maximum_risk: "medium"
    business_hours_only: false
    approval_required: false

  effective_from: "..."
  effective_until: null

  granted_by: "idn_..."
  evidence_reference: "evidence_..."
  status: "active"
```

Supported permission levels:

- `observe`
- `recommend`
- `request_approval`
- `execute`
- `administer`

`administer` permits management of authority records. It does not grant unrestricted operational access.

## 6. Execution context

The service returns an immutable, short-lived execution context to the orchestrator.

```yaml
execution_context:
  context_id: "ctx_..."
  correlation_id: "corr_..."

  requester:
    identity_id: "idn_..."
    identity_type: "person"

  acting_as:
    organization_id: "org_aot"
    role_id: "role_service_manager"

  target:
    client_id: "client_edgewater"
    tenant_id: "tenant_edgewater"

  capability:
    name: "ticket.investigate"
    requested_mode: "recommend"

  authority:
    result: "allowed"
    maximum_mode: "recommend"
    approval_required: false
    matched_grants:
      - "grant_..."

  authentication:
    assurance_level: "high"
    age_seconds: 46

  issued_at: "..."
  expires_at: "..."
```

All downstream capability requests must include this context.

A capability must reject requests that:

- lack a valid context;
- use an expired context;
- attempt to change client or tenant scope;
- request more authority than the context permits;
- reuse a context issued for another capability;
- lack a correlation identifier.

## 7. Decision outcomes

The service returns one of five results:

- `allowed`
- `allowed_limited`
- `approval_required`
- `denied`
- `indeterminate`

Jason must fail closed on `denied` and `indeterminate`.

Example:

```yaml
result: "allowed_limited"
requested_mode: "execute"
maximum_mode: "recommend"
reason_code: "AUTHORITY_MODE_EXCEEDED"
```

Jason may prepare a recommendation but may not perform the action.

## 8. Client isolation

Client isolation is a kernel-level invariant.

Every operational resource must belong to:

- one specific client;
- AOT internal operations; or
- a controlled shared-services scope.

The service must prevent:

- using one client's ticket to retrieve another client's device;
- passing evidence between unrelated clients;
- searching cross-client memory without explicit authority;
- reusing connector credentials outside their permitted tenant;
- generating output that exposes another client's information.

A missing client scope is not interpreted as global access. It is an invalid or incomplete request.

## 9. Approval model

Approval is a formal object rather than an informal statement buried in a conversation.

```yaml
approval:
  id: "apr_..."
  request_id: "req_..."
  requested_action: "mailbox.delete"
  target_client_id: "client_..."
  risk_level: "high"

  requested_by: "idn_..."
  required_approval_class: "client_authorized_contact"

  status: "approved"
  decided_by: "idn_..."
  decided_at: "..."
  expires_at: "..."

  conditions:
    - "export_mailbox_before_deletion"

  evidence_reference: "evidence_..."
```

Approvals must be explicit, attributable, scope-specific, time-limited where appropriate, bound to the exact proposed action, and invalidated when material facts change.

Approval to disable a mailbox does not imply approval to delete it.

## 10. Initial APIs

### Resolve identity

```http
POST /v1/identities/resolve
```

### Evaluate authority

```http
POST /v1/authority/evaluate
```

### Issue execution context

```http
POST /v1/execution-contexts
```

### Validate execution context

```http
POST /v1/execution-contexts/validate
```

### Request approval

```http
POST /v1/approvals
```

### Record approval decision

```http
POST /v1/approvals/{approval_id}/decision
```

## 11. Events emitted

- `identity.resolved`
- `identity.resolution_failed`
- `authority.allowed`
- `authority.limited`
- `authority.denied`
- `authority.indeterminate`
- `approval.requested`
- `approval.approved`
- `approval.denied`
- `approval.expired`
- `execution_context.issued`
- `execution_context.rejected`
- `client_boundary.violation_attempted`

Events describe what happened. They do not independently trigger actions. Policies interpret events.

## 12. Audit requirements

Every authority decision must record:

- requester identity;
- acting role;
- organization, tenant, and client scope;
- requested capability;
- requested authority mode;
- authentication assurance;
- matched grants;
- applicable restrictions;
- decision and reason code;
- timestamp and correlation ID;
- policy version;
- approver where applicable.

Sensitive credentials and authentication tokens must never appear in audit logs.

## 13. Version 0.1 storage

Use a relational database. PostgreSQL is preferred for the first shared build. SQLite may be used for a single-node prototype.

Minimum tables:

- `identities`
- `external_identity_mappings`
- `organizations`
- `clients`
- `roles`
- `role_assignments`
- `authority_grants`
- `approval_requests`
- `approval_decisions`
- `execution_contexts`
- `audit_events`

Use opaque internal identifiers. Preserve provider identifiers only as mappings.

## 14. Initial policy rules

```yaml
rules:
  - id: deny_missing_client_context
    effect: deny
    when:
      operational_request: true
      client_id: null

  - id: deny_cross_client_scope
    effect: deny
    when:
      requester_client_scope_mismatch: true

  - id: agents_cannot_hold_independent_authority
    effect: deny
    when:
      requester_type: agent
      orchestrator_context_present: false

  - id: high_risk_requires_approval
    effect: require_approval
    when:
      risk_level:
        - high
        - critical

  - id: expired_authentication_requires_reauthentication
    effect: indeterminate
    when:
      authentication_age_exceeds_policy: true
```

The policy set is intentionally small. It should expand only when working capabilities reveal demonstrated needs.

## 15. Failure behavior

| Failure | Required behavior |
|---|---|
| Identity provider unavailable | Use a valid cached mapping only; otherwise return `indeterminate`. |
| Duplicate identity match | Return `indeterminate`; do not guess. |
| Missing client scope | Reject the request. |
| Expired authority | Reject or request renewed approval. |
| Database unavailable | Fail closed for execution. |
| Approval service unavailable | Preserve the pending request; do not execute. |
| Context tampering | Reject and emit a security event. |
| Cross-client mismatch | Reject, audit, and flag for review. |

## 16. Minimum test suite

1. A valid AOT technician can investigate a ticket for an assigned client.
2. The same technician cannot access an unrelated client without a grant.
3. An agent request without orchestrator context is denied.
4. A technician requesting a high-risk action receives `approval_required`.
5. An approved request succeeds only within the approved scope.
6. Approval for one ticket cannot be reused for another.
7. An expired execution context is rejected.
8. A disabled identity loses access immediately.
9. Conflicting identity mappings return `indeterminate`.
10. Every decision produces a complete audit record.
11. No secret or access token appears in logs.
12. A cross-client evidence reference is rejected.

## 17. Definition of done

Version 0.1 is complete when:

- canonical identities can be created and resolved;
- external identities can be mapped;
- client context is mandatory;
- scoped authority grants can be evaluated;
- approval requests can be created and decided;
- execution contexts can be issued and validated;
- cross-client access is prevented;
- decisions are auditable;
- Capability #001 can use the service end to end.

## 18. Deliberately deferred

Do not build yet:

- behavioral identity scoring;
- distributed identity federation;
- dynamic trust scoring;
- a sophisticated attribute-based policy language;
- automated delegation inference;
- universal vendor identity synchronization;
- self-modifying authority policies.

These may become appropriate later but are not required for the first working vertical slice.

## 19. Immediate implementation sequence

1. Create the relational schema.
2. Implement identity resolution.
3. Implement scoped authority evaluation.
4. Issue signed execution contexts.
5. Implement formal approval objects.
6. Add complete audit events.
7. Connect the service to Capability #001 — Professional Ticket Investigation.
