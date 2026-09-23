# J-118 — Relationship Model

**Status:** Approved Foundation Model  
**Artifact Type:** Canonical Model  
**Owner:** Jason Architecture Authority  
**Applies To:** Every governed object, state, decision, event, service, connector, workflow, and implementation in Jason

## 1. Purpose

The Relationship Model defines how the objects in Jason's world are connected.

Objects without relationships are isolated records. Relationships give those objects business meaning by explaining ownership, authority, dependency, responsibility, service delivery, evidence, impact, and context.

Jason must be able to answer:

1. How are these objects connected?
2. What does that connection mean?
3. Who established or verified it?
4. When did it become effective, and does it still apply?
5. What authority, policy, agreement, evidence, or condition governs it?
6. What other objects may be affected if the relationship changes?
7. Can the relationship be trusted strongly enough to support a decision or action?

## 2. Scope

This model defines:

- the minimum canonical relationship vocabulary;
- the common record required for governed relationships;
- relationship direction, scope, confidence, provenance, and lifecycle;
- rules for authority and dependency chains;
- impact traversal and explainability;
- cross-tenant and external-system relationship constraints;
- requirements for introducing new relationship types.

This model does not require a graph database or prescribe a storage technology. SQL, document, graph, API, and hybrid implementations may conform when they preserve the required meaning and governance.

## 3. Foundational Principles

### 3.1 Relationships carry business meaning

A relationship is not merely a technical link or foreign key. It states a governed fact or claim about how two objects relate.

### 3.2 Relationships are first-class records

A material relationship may have its own identity, source, scope, authority, effective dates, confidence, policy, evidence, state, and audit history.

### 3.3 Explain through relationships, not assumptions

Jason must explain material conclusions and actions through verified objects and relationships whenever practical. Administrative access, physical proximity, shared naming, or provider association must not be treated as proof of authority or business meaning.

### 3.4 Use the smallest useful vocabulary

Jason shall maintain a limited canonical relationship vocabulary. Provider-specific links and synonyms must map to canonical relationships rather than multiplying the model.

### 3.5 Direction matters

`A owns B` is not equivalent to `B owns A`. Every relationship type must define its direction and, where useful, its inverse.

### 3.6 Relationship confidence remains visible

Discovered, inferred, reported, verified, disputed, expired, and revoked relationships must not be represented as equivalent.

### 3.7 Relationships are time-aware

A relationship may be valid only during a defined period. Historical relationships must remain available for audit and reconstruction even after they are no longer current.

### 3.8 Tenant boundaries remain authoritative

A relationship must not create cross-tenant access, context transfer, or authority merely because two objects are technically connected.

## 4. Common Relationship Record

Every material governed relationship must support:

- canonical relationship identifier;
- canonical relationship type;
- source object identifier and type;
- target object identifier and type;
- organization and tenant context;
- human-readable meaning;
- relationship direction;
- relationship state;
- effective start time;
- expiration, review, revocation, or supersession time where applicable;
- creator or establishing authority;
- source and provenance;
- verification status and confidence;
- applicable policy, agreement, approval, or delegation;
- scope and limitations;
- related evidence;
- classification and handling restrictions;
- external-system mappings where applicable;
- last material change time and actor;
- audit references.

Not every provider must store every field. Jason must be able to resolve the complete governed relationship context before relying on it for a material decision or action.

## 5. Canonical Relationship Vocabulary

### 5.1 Organizational and structural relationships

- **owns** — possesses recognized legal, contractual, organizational, or business ownership of an object.
- **belongs to** — establishes membership within an organization, tenant, business unit, department, team, site, project, or governed collection.
- **contains** — establishes a parent-child or whole-part structure without necessarily establishing ownership.
- **represents** — indicates that one object is the recognized digital, documentary, provider, or operational representation of another.
- **maps to** — connects a canonical Jason object or relationship to an external-system record or equivalent representation.

### 5.2 Operational relationships

- **requests** — states that a Person, Identity, Organization, Event, Alert, Policy, or other object initiated or expressed a Request or Work Item.
- **performs** — identifies the party or capability executing work or an action.
- **affects** — states that an Incident, Change, Alert, Work Item, Decision, or Event has actual or potential impact on another object.
- **supports** — states that an Asset, Service, Knowledge item, Capability, Person, or provider contributes to the operation or delivery of another object.
- **depends on** — states that one object requires another object, relationship, condition, or capability to function or achieve its intended outcome.

### 5.3 Governance and authority relationships

- **governs** — states that a Policy, Organization, Role, Agreement, or authority establishes controlling requirements for another object or relationship.
- **approves** — records that a recognized authority authorized, denied, conditionally authorized, or acknowledged a defined object, action, scope, or decision.
- **authorizes** — grants permission to perform a defined action within stated scope, conditions, and duration.
- **is accountable for** — identifies the party answerable for the final outcome.
- **is responsible for** — identifies the party assigned to perform, coordinate, or manage the work.

### 5.4 Knowledge and evidence relationships

- **documents** — states that Knowledge records, describes, explains, or preserves information about another object, relationship, process, or outcome.
- **references** — creates a governed informational citation or association without asserting ownership, authority, or proof by itself.
- **provides evidence for** — states that Evidence supports, challenges, verifies, or reproduces a fact, condition, control, decision, action, or outcome.
- **supersedes** — states that one object or relationship replaces another while preserving the prior record and history.

### 5.5 Technical and protective relationships

- **connects to** — states that two Assets, Services, Identities, Connectors, or environments maintain a defined technical connection.
- **communicates with** — states that information or protocol traffic is exchanged between objects.
- **monitors** — states that an object or capability observes another object, condition, service, or control.
- **protects** — states that a control, service, asset, policy, or capability reduces risk to another object.

These canonical relationships may have governed subtypes when operational precision is required. A subtype must not change the canonical meaning.

## 6. Relationship Direction and Inverses

Every relationship definition must identify:

- the valid source object types;
- the valid target object types;
- whether the relationship is directional;
- whether an inverse relationship is recognized;
- whether multiple simultaneous relationships are permitted;
- whether the relationship may be transitive;
- whether the relationship may create authority, responsibility, dependency, or impact.

Examples:

- `Organization owns Asset` may be viewed inversely as `Asset is owned by Organization`.
- `Person approves Change` is not equivalent to `Person performs Change`.
- `Service depends on Asset` must not automatically imply that `Asset depends on Service`.
- `Connector maps to external record` does not imply that the external system governs the canonical object.

## 7. Relationship State and Verification

A relationship must use J-116 state dimensions rather than compressing all meaning into a single status.

Typical lifecycle states include:

- Candidate
- Active
- Suspended
- Expired
- Revoked
- Superseded
- Retired

Typical verification states include:

- Unknown
- Reported
- Inferred
- Discovered
- Corroborated
- Verified
- Disputed
- Rejected

An active relationship may still be unverified. A verified relationship may be historical and no longer active. Implementations must preserve both dimensions.

## 8. Authority Chains

Material action authority must be explainable through an attributable relationship chain.

A valid chain may include:

1. a Person or Identity;
2. a Role assignment;
3. an Organization or Tenant context;
4. a delegation or approval relationship;
5. an applicable Agreement or Policy;
6. a defined scope and effective period;
7. the affected object or action.

Possession of a credential, administrator role, API permission, RMM tool, or physical access does not by itself establish business authority.

Jason must stop or escalate when the authority chain is missing, ambiguous, expired, disputed, broader than the requested action, or dependent on an unverified relationship.

## 9. Responsibility and Accountability

Responsibility and accountability must remain distinct.

A Work Item may be:

- requested by a client employee;
- assigned to an AOT technician;
- performed through a Datto RMM capability;
- approved by a client approver;
- governed by an Agreement and Policy;
- accountable to an AOT service manager.

No implementation may collapse these relationships into one generic owner or assignee field when the distinctions affect authority, workflow, communication, or audit.

## 10. Dependency and Impact Analysis

Jason must support traversal of verified relationships to determine:

- what depends on an affected object;
- what services or clients may be impacted;
- what controls, documentation, monitoring, or agreements apply;
- which parties must be notified, consulted, or approve;
- what evidence is required before and after a change;
- what secondary risks or obligations may arise.

Impact traversal must be bounded by tenant, authorization, classification, relevance, confidence, and cost.

An unverified or inferred dependency may justify investigation, but it must not be presented as confirmed impact.

## 11. Relationship-Based Explainability

For a material recommendation, decision, or action, Jason should be able to produce a human-readable explanation such as:

> This technician may perform the firewall restart because the technician holds an active AOT engineer role, AOT provides managed network service to the client under an active agreement, the firewall is within the managed scope, the maintenance policy permits the action during the current window, and the required approval is active.

The explanation should identify:

- the conclusion or proposed action;
- the decisive relationships;
- the supporting evidence and policy;
- unresolved uncertainty;
- any missing authority or verification;
- the expected impact and verification method.

Jason must not expose sensitive graph details beyond the audience's authorized need to know.

## 12. Cross-Tenant Relationships

A relationship crossing tenant boundaries must record:

- the purpose;
- the participating organizations and tenants;
- the establishing authority;
- the allowed data or action scope;
- handling restrictions;
- effective and expiration times;
- revocation method;
- audit requirements.

A cross-tenant relationship does not merge tenant context. Shared vendors, platforms, personnel, knowledge, or infrastructure must not cause client data or reasoning context to bleed between tenants.

## 13. Provider and Connector Relationships

External systems may expose links such as company-to-ticket, device-to-site, mailbox-to-user, or document-to-organization. These links are evidence for mapping but are not automatically canonical truth.

Each provider relationship mapping must retain:

- provider and connector;
- external identifiers;
- source tenant;
- mapped canonical relationship;
- mapping confidence;
- last verification time;
- source authority;
- detected conflicts or ambiguity.

Provider relationships must not silently grant ownership, authority, accountability, or permission.

## 14. Relationship Discovery and Bounded Curiosity

When Jason identifies a missing, broken, suspicious, or incomplete relationship relevant to an outcome, it should pursue the smallest useful investigation.

Examples include:

- resolving which Asset an Alert actually affects;
- determining which Service depends on a failed Asset;
- verifying whether an approver still holds authority;
- identifying whether a Work Item is covered by an Agreement;
- determining whether a discovered Identity belongs to the expected Person;
- collecting only the relevant time range or event subset needed to establish a communication or dependency relationship.

Jason should expand the investigation only when the current evidence is insufficient and the expected value justifies the additional access, cost, time, or data exposure.

## 15. Relationship Type Admission Test

A new canonical relationship type must satisfy all of the following:

1. **Business meaning:** It expresses a durable business concept rather than a provider field or database join.
2. **Distinct semantics:** Existing canonical relationships cannot express the meaning without ambiguity.
3. **Governance value:** The distinction affects authority, policy, workflow, evidence, impact, reporting, or audit.
4. **Clear direction:** Source, target, direction, and inverse can be defined consistently.
5. **Operational use:** At least one real decision, service, investigation, control, or report depends on it.
6. **Common language:** Business and technical stakeholders can understand and use it consistently.

Synonyms and provider-specific labels should map to an existing canonical relationship whenever possible.

## 16. Constraints

1. No relationship may create authority merely because a technical connection exists.
2. No inferred relationship may be treated as verified without supporting evidence.
3. No relationship may bypass tenant, policy, classification, approval, or audit controls.
4. No provider-specific link may become canonical solely because it appears in an API.
5. No relationship change may erase required historical meaning, evidence, or provenance.
6. No transitive relationship may be assumed unless the relationship definition explicitly permits transitivity.
7. No shared provider, credential, person, or system may implicitly create a cross-tenant relationship.
8. No administrative capability may be confused with ownership, accountability, or approval authority.
9. No relationship traversal may expose more data than the authorized purpose requires.
10. No unexplained relationship chain may support a high-impact autonomous action.

## 17. MSP Examples

### 17.1 Device alert investigation

A Datto RMM Alert maps to a Jason Alert, affects a managed Asset, may threaten a supported Service, and creates or contributes to a Work Item. The Asset belongs to a client tenant, is monitored by a Capability, and is covered by an Agreement. Jason uses those relationships to determine scope, priority, authority, and communication requirements.

### 17.2 Microsoft 365 user departure

A Person may have multiple Identities, mailboxes, devices, group memberships, vendor accounts, and approval roles. Disabling one Entra Identity does not prove that every access relationship has ended. Jason traverses the governed relationships to identify remaining access, delegated authority, custody, and evidence requirements.

### 17.3 Firewall replacement

A firewall Asset supports internet access, VPN, security monitoring, compliance controls, and documented network topology. It may be covered by an Agreement, monitored through Connectors, and depended upon by multiple Services. A replacement Change must evaluate those relationships before execution and verify them afterward.

### 17.4 Knowledge reuse

A troubleshooting procedure in the System Tenant may document a Capability and reference general vendor behavior. Client-specific logs or screenshots provide evidence for a client Work Item but do not become shared Knowledge until an authorized de-identification and publication process creates a separate governed relationship.

## 18. Conformance Requirements

An implementation conforms to J-118 when it:

1. represents relationships independently of provider-specific links;
2. preserves source, target, type, direction, tenant, provenance, state, and confidence;
3. distinguishes ownership, responsibility, accountability, approval, and technical access;
4. supports effective dates, expiration, revocation, supersession, and historical reconstruction;
5. prevents ungoverned cross-tenant relationships and context transfer;
6. supports explainable authority and dependency chains;
7. preserves uncertainty rather than silently converting inference into fact;
8. supports bounded relationship traversal for impact analysis and investigation;
9. maps provider links to canonical relationships without granting unintended authority;
10. records material relationship changes in the audit record.

## 19. Canonical Statement

> Jason understands the business by understanding how governed objects relate. It explains decisions through relationships, not assumptions.
