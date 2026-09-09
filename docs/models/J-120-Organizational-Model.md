# J-120 — Organizational Model

**Status:** Approved Foundation Model  
**Artifact Type:** Canonical Model  
**Owner:** Jason Architecture Authority  
**Applies To:** Jason, AOT, client organizations, partners, vendors, providers, users, and all governed artifacts  

## 1. Purpose

The Organizational Model defines the people, organizations, ownership boundaries, authority relationships, tenancy boundaries, and trust relationships that Jason recognizes.

Jason cannot safely govern work, evidence, knowledge, policy, automation, or access unless it can answer five questions:

1. Who is involved?
2. Which organization or tenant does the matter belong to?
3. Who owns the affected object or information?
4. Who has authority to decide or act?
5. Across which trust boundaries may information or action pass?

This model provides the canonical answers and vocabulary used by every other Jason model, service, connector, workflow, and implementation.

## 2. Scope

This model defines:

- organizational entity types;
- tenancy and isolation boundaries;
- ownership, custody, authority, accountability, and responsibility;
- people, identities, roles, and organizational membership;
- service, vendor, partner, and provider relationships;
- delegation and approval authority;
- rules for cross-organizational access and sharing.

This model does not define:

- authentication mechanisms;
- role permission details;
- application-specific access-control lists;
- connector credentials;
- employee reporting structures beyond what is operationally required;
- the lifecycle of every business object.

Those concerns belong to the Identity, Policy, Security, Object, State, and Connector models.

## 3. Foundational Principles

### 3.1 Organization before system

Jason associates work and information with the organization that owns or governs it before associating it with any external platform. Autotask, Datto RMM, IT Glue, Microsoft 365, OpenClaw, and AI providers are implementations or providers, not organizational authorities.

### 3.2 Explicit tenancy

Every governed object must belong to an explicit tenant or to the Jason system tenant. Tenant ownership must never be inferred solely from a connector, credential, filename, conversation, or model context.

### 3.3 Deny by default

Access, disclosure, transfer, and action across trust boundaries are denied unless an applicable policy and authority explicitly allow them.

### 3.4 Least privilege and need to know

A person, identity, service, agent, or connector receives only the authority and information required for the approved purpose and duration.

### 3.5 Ownership is not authority

Ownership, custody, responsibility, accountability, and authority are separate concepts. They may be assigned to different parties.

### 3.6 Authority must be attributable

Every material decision, approval, delegation, or action must be attributable to a recognized person, role, organization, policy, or system authority.

### 3.7 No implicit cross-tenant context

Data, evidence, knowledge, conversation history, credentials, and operational context from one client tenant must not enter another tenant's processing context without explicit governed authorization.

### 3.8 Providers are replaceable

A provider may supply capabilities, but it does not define Jason's identity, organizational model, policy, or authority structure.

## 4. Canonical Organizational Entities

### 4.1 Organization

A legally, contractually, or operationally recognized body with its own objectives, authority, ownership, and accountability.

Examples include AOT, a managed client, a vendor, a partner, or a regulator.

### 4.2 AOT

Atlantic Office Technologies, the organization that owns and governs Jason and may provide managed services to client organizations.

AOT is an Organization. It is not the default owner of client data, client evidence, or client policy merely because it administers the systems containing them.

### 4.3 Client Organization

An organization receiving services through Jason or AOT. A client organization owns or governs its business data, assets, policies, evidence, approvals, and operational outcomes except where a contract or law establishes otherwise.

### 4.4 Tenant

A logical security, policy, data, and context isolation boundary associated with an organization or an explicitly authorized shared service.

A tenant is not merely a Microsoft 365 tenant, Autotask company, Datto site, or database partition. Those may represent or map to a Jason Tenant, but Jason's tenant definition remains implementation-independent.

### 4.5 System Tenant

The isolated tenant containing Jason's own governance, architecture, operational configuration, shared platform controls, and internal evidence. The System Tenant must not become a repository for unrestricted client content.

### 4.6 Business Unit

A recognized subdivision of an organization with delegated operational or financial responsibility.

### 4.7 Department

A functional subdivision of an organization, such as Finance, Operations, Human Resources, Information Technology, or Compliance.

### 4.8 Team

A group of people organized for a defined operational purpose. A team may span departments but remains within an explicitly defined organizational scope.

### 4.9 Site

A managed operational location associated with an organization or tenant. A site may be physical, virtual, cloud-hosted, or administrative.

### 4.10 Person

A human being recognized by Jason independently of any account, username, mailbox, or application identity.

### 4.11 Identity

A representation of a Person, Service, Agent, Connector, or Organization within a particular security or technology domain. One Person may have multiple Identities.

### 4.12 Role

A named set of expected responsibilities and permitted authority within an organizational context. A Role is assigned; it is not inherent to a Person.

Examples include Client Approver, AOT Technician, Service Manager, Technology Steward, Compliance Officer, and System Administrator.

### 4.13 Vendor

An external organization that sells or licenses products or services. A Vendor relationship does not itself grant operational authority or access.

### 4.14 Provider

An organization or technology supplying a capability through a governed interface. A Provider may also be a Vendor, but the terms are not interchangeable.

### 4.15 Partner

An external organization with a defined cooperative, referral, delivery, support, or contractual relationship.

### 4.16 Service Provider

An organization authorized to perform one or more services for another organization under a defined agreement, policy, and scope.

### 4.17 Regulator or Oversight Authority

An external body with legal, contractual, accreditation, or supervisory authority relevant to an organization.

## 5. Organizational Relationships

Jason recognizes the following canonical relationship types:

- **owns** — possesses legal or organizational ownership;
- **governs** — establishes controlling policy or authority;
- **is accountable for** — bears final responsibility for an outcome;
- **is responsible for** — performs or manages assigned work;
- **has custody of** — physically or logically holds an object without necessarily owning it;
- **administers** — operates or maintains a system or object under delegated authority;
- **provides service to** — delivers an agreed service;
- **receives service from** — consumes an agreed service;
- **employs** — maintains an employment relationship with a Person;
- **contracts with** — maintains a contractual relationship;
- **delegates authority to** — grants defined authority within limits;
- **approves for** — may authorize a defined decision or action;
- **belongs to** — establishes organizational membership;
- **operates within** — places an entity within a tenant or trust boundary;
- **shares with** — permits a governed transfer of information or access;
- **supplies capability to** — provides a capability through a governed connector or service.

Relationships must be explicit, attributable, time-bounded where appropriate, and subject to policy.

## 6. Ownership, Custody, Responsibility, Accountability, and Authority

These concepts must not be collapsed into a single "owner" field.

### 6.1 Ownership

The party possessing the recognized legal, contractual, or organizational claim to an object or information.

### 6.2 Custody

The party currently storing, holding, processing, or protecting an object or information.

### 6.3 Responsibility

The party assigned to perform or manage a task.

### 6.4 Accountability

The party answerable for the final outcome. Accountability remains even when execution is delegated.

### 6.5 Authority

The permission to decide, approve, direct, disclose, modify, or execute within a defined scope.

### 6.6 Example

A client may own its Microsoft 365 data. Microsoft may have custody of the hosted data. AOT may administer the tenant. An AOT technician may be responsible for a remediation task. The client's authorized approver may retain authority to approve a disruptive change. AOT's service manager may be accountable for delivery under the service agreement.

## 7. Tenancy and Isolation

### 7.1 Tenant assignment

Every governed object must include a tenant identifier or a documented reason why it is global or shared.

### 7.2 Shared objects

An object may be shared across tenants only when:

1. the sharing purpose is defined;
2. the sharing authority is verified;
3. the permitted recipients are explicit;
4. the minimum necessary information is used;
5. the action is logged;
6. the sharing can be revoked or expire where practical.

### 7.3 Context isolation

Reasoning providers, agents, workflows, and services must receive only the tenant context required for the current work item. Cached, historical, retrieved, or remembered context must remain tenant-scoped.

### 7.4 Credential isolation

Credentials must be scoped to the organization, tenant, capability, and action for which they are authorized. A shared credential does not create shared authority.

### 7.5 Evidence isolation

Evidence must retain its tenant, source, collection time, custody, classification, and permitted-use metadata throughout its lifecycle.

## 8. Roles and Delegation

### 8.1 Role assignment

A Person or non-human Identity may hold one or more Roles, but each assignment must specify:

- organization;
- tenant;
- scope;
- authority;
- effective date;
- expiration or review date where appropriate;
- assigning authority.

### 8.2 Delegation

Delegated authority must be:

- explicit;
- limited in scope;
- attributable;
- revocable;
- no broader than the delegator's authority;
- recorded for material actions.

### 8.3 Separation of duties

Jason must support policies requiring different parties to request, approve, execute, and verify work. No implementation may assume that possession of administrative access also grants business approval authority.

### 8.4 Emergency authority

Emergency authority may be granted by policy for defined conditions. Its use must be time-limited, logged, reviewed, and followed by retrospective approval or investigation as required by policy.

## 9. Organizational Context Record

Every governed work item should be able to resolve an Organizational Context Record containing at least:

- organization identifier;
- tenant identifier;
- requesting Person and Identity;
- affected organization and tenant;
- responsible party;
- accountable party;
- approval authority;
- applicable service relationship;
- applicable policy domain;
- data classification or handling restrictions;
- relevant sites, departments, or business units;
- cross-boundary transfers requested or performed.

The record may be assembled from multiple systems, but Jason remains authoritative for the normalized organizational context used in governance.

## 10. Constraints

1. No object may exist in an undefined tenant context unless its global scope is explicitly governed.
2. No cross-tenant access may be granted through inference, convenience, or shared tooling alone.
3. No provider may grant organizational authority merely because it exposes an administrative function.
4. No agent may infer approval authority from job title alone.
5. No delegated authority may exceed the delegator's authority.
6. No person may be treated as equivalent to an account or mailbox.
7. No external system identifier may serve as Jason's sole canonical identifier.
8. No client data may be used to improve another client's outcome unless authorized, de-identified where required, and permitted by policy and law.
9. No implementation may bypass the orchestrator's tenant, policy, authority, and audit controls.
10. All material organizational relationship changes must be auditable.

## 11. Security and Privacy Considerations

The Organizational Model is a primary security boundary. Implementations must protect against:

- tenant confusion;
- identity collision;
- unauthorized delegation;
- stale role membership;
- inherited access that exceeds current need;
- data leakage through prompts, logs, caches, reports, or reusable artifacts;
- provider-side retention inconsistent with organizational policy;
- administrative access being mistaken for approval authority;
- vendor or partner access persisting beyond its authorized purpose.

Organizational and role data must be treated as security-sensitive because it determines what Jason may disclose or do.

## 12. MSP Examples

### 12.1 Client mailbox remediation

A client employee reports suspicious forwarding rules. The client owns the mailbox data. Microsoft has custody as the cloud provider. AOT administers the tenant under contract. An AOT technician may investigate within delegated authority. Removing a malicious rule may be pre-authorized by incident-response policy, while restoring or exporting messages may require a client approver.

### 12.2 Datto RMM automation

A Datto component can execute administrative commands, but Datto's technical ability does not grant business authority. Jason must verify the client tenant, affected device, applicable maintenance policy, technician authority, and approval requirements before execution.

### 12.3 Shared knowledge

A general troubleshooting procedure may be held in the System Tenant and reused across clients. Client-specific screenshots, credentials, topology, logs, and outcomes remain within the client tenant unless an explicitly approved de-identification and publication process creates a separate shared knowledge artifact.

### 12.4 Vendor support

A vendor engineer may receive temporary access to a client system only after the authorized party approves the scope, purpose, duration, and data exposure. The access relationship must expire or be revoked when the support activity ends.

## 13. Conformance Requirements

An implementation conforms to J-120 when it:

1. represents Organization, Tenant, Person, Identity, Role, and Provider as distinct concepts;
2. assigns governed objects to explicit tenants;
3. distinguishes ownership, custody, responsibility, accountability, and authority;
4. enforces deny-by-default cross-tenant behavior;
5. records delegation and approval authority;
6. preserves tenant context through services, agents, connectors, evidence, logs, and outputs;
7. prevents external platform identifiers from becoming the sole canonical identity;
8. produces auditable records of material cross-boundary actions.

## 14. Dependencies and Downstream Use

J-120 depends on:

- the Jason Constitution;
- the Decision Architecture;
- the Design Principles;
- the Work and Development Lifecycles;
- the Jason Lexicon rules.

J-120 is authoritative input to:

- J-112 Identity Model;
- J-114 Policy Model;
- J-115 Audit Model;
- J-116 State Model;
- J-117 Object Model;
- J-118 Relationship Model;
- J-119 Event Model;
- Security Architecture;
- Connector Architecture;
- service and domain models;
- approval, authorization, and tenant-isolation controls.

## 15. Architect's Rationale

Jason serves multiple organizations through shared technologies. MSP platforms commonly allow one administrator, workflow, API credential, or AI context to reach many clients. That operational efficiency creates a corresponding risk of tenant confusion, overbroad authority, and unintended data disclosure.

This model establishes organization and tenant context before implementation details. It ensures that technical access is never mistaken for authorization, that providers remain replaceable, and that client ownership and trust boundaries survive changes in tools, vendors, models, and deployment platforms.

The model should be revised when Jason encounters a materially new organizational relationship that cannot be represented without ambiguity. It should not be expanded merely to mirror the organizational hierarchy of a particular provider or application.

## 16. Approval Record

**Decision:** Adopt J-120 as the canonical Organizational Model.  
**Basis:** Required to support tenant isolation, authority verification, ownership attribution, cross-organizational governance, and downstream canonical models.  
**State:** Approved for foundational use.  
