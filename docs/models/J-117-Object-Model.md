# J-117 — Object Model

**Status:** Approved Foundation Model  
**Artifact Type:** Canonical Model  
**Owner:** Jason Architecture Authority  
**Applies To:** Every business concept, artifact, service, connector, workflow, event, decision, and implementation governed by Jason

## 1. Purpose

The Object Model defines what exists in Jason's world.

Jason represents the MSP business and the client environments it serves through a limited set of stable, vendor-independent business objects. These objects provide the common language used by governance, policy, orchestration, knowledge, evidence, reporting, connectors, automation, and user interfaces.

The model exists so Jason can answer:

1. What kind of thing is this?
2. Which tenant and organization does it belong to?
3. Who owns, governs, or is responsible for it?
4. What state is it in?
5. How is it related to other objects?
6. What evidence, policy, authority, and history apply to it?
7. Which external systems represent or manage it?

## 2. Scope

This model defines:

- the minimum canonical object types required to represent an MSP business;
- the properties shared by all governed objects;
- the distinction between business objects and vendor implementations;
- rules for object identity, ownership, provenance, versioning, and external mappings;
- requirements for introducing new object types.

This model does not define:

- detailed lifecycle states;
- relationship semantics beyond the minimum needed to identify dependencies;
- events and event processing;
- vendor API schemas;
- database tables, classes, file formats, or user-interface layouts;
- detailed permissions or connector behavior.

Those concerns belong to the State, Relationship, Event, Identity, Policy, Security, Connector, and implementation models.

## 3. Foundational Principles

### 3.1 Model the business, not the software

Jason models enduring business concepts. Vendor objects, API resources, database records, and product terminology are mapped to canonical Jason objects rather than adopted as the definition of reality.

### 3.2 Prefer the smallest useful model

Jason shall maintain only the object types needed to govern real work. A new object type must solve a demonstrated problem that cannot be handled cleanly by an existing type, subtype, attribute, or relationship.

### 3.3 Canonical identity is independent

Every governed object must have a Jason canonical identifier that is independent of any provider, connector, tenant-specific platform, filename, account name, or external record number.

### 3.4 External systems are representations

An Autotask ticket, Datto device, IT Glue document, Microsoft Entra account, or Microsoft 365 mailbox may represent a Jason object, but none is the canonical object itself.

### 3.5 Every object has organizational context

Every governed object must resolve to an organization and tenant, or to an explicitly governed global or shared context, as defined by J-120.

### 3.6 Every material object is attributable and auditable

Jason must preserve who or what created, changed, approved, verified, superseded, or retired a material object.

### 3.7 Objects are not duplicated merely because systems differ

Multiple provider records referring to the same real-world thing should map to one canonical object when identity can be resolved with sufficient confidence.

### 3.8 Uncertainty must remain visible

When object identity, ownership, classification, or mapping is uncertain, Jason records the uncertainty and does not silently convert an inference into fact.

## 4. Common Object Record

Every governed object must support the following common properties, either directly or through governed relationships:

- canonical object identifier;
- object type;
- human-readable name or title;
- organization identifier;
- tenant identifier;
- owner;
- custodian where applicable;
- responsible party;
- accountable party where applicable;
- current lifecycle state;
- creation time and creator;
- last material change time and actor;
- source and provenance;
- confidence or verification status where the object was inferred or discovered;
- classification and handling restrictions;
- applicable policies;
- related evidence;
- external system mappings;
- version or revision information where appropriate;
- retention, review, expiration, or retirement information where applicable;
- audit references.

Not every property must be stored on every provider record. Jason must be able to resolve the complete governed context when the object is used for a decision or action.

## 5. Canonical Object Types

### 5.1 Organization

A legally, contractually, or operationally recognized entity with objectives, authority, ownership, and accountability.

The detailed organizational structure is governed by J-120.

### 5.2 Person

A human being recognized independently of any account, mailbox, username, job title, or provider record.

### 5.3 Identity

A digital representation of a Person, Service, Agent, Connector, or Organization within a security or technology domain.

An Identity is not the same object as the Person or Service it represents.

### 5.4 Asset

Something of business, operational, informational, financial, contractual, or technical value that is owned, governed, managed, protected, or tracked.

Examples include a workstation, server, firewall, software entitlement, building access system, domain name, dataset, or business-critical application.

A Device is a subtype of Asset when the distinction is operationally useful.

### 5.5 Service

A business or technical function delivered, consumed, supported, or depended upon by an organization.

Examples include managed endpoint service, Microsoft 365 email, internet access, backup, cybersecurity monitoring, payroll processing, or service desk support.

A Service is not a product SKU, vendor platform, or connector, though those may enable it.

### 5.6 Agreement

A contract, service agreement, subscription, statement of work, license, policy acceptance, or other governed arrangement defining obligations, scope, rights, service levels, pricing, authority, or responsibility between parties.

### 5.7 Request

An expressed need, question, instruction, desired outcome, or demand for service that may require evaluation, approval, work, or response.

A Request may originate from a Person, system, event, policy, alert, scheduled obligation, or another governed object.

### 5.8 Work Item

A governed unit of work created to evaluate, fulfill, remediate, investigate, change, deliver, or verify an outcome.

Autotask tickets, PSA cases, change records, support cases, and internal action items may represent Work Items.

### 5.9 Task

A discrete, assignable unit of action within a Work Item, Project, Change, Incident, or other governed effort.

A Task must not be used as a substitute for the parent business object when the broader outcome requires its own lifecycle, authority, evidence, or accountability.

### 5.10 Alert

A reported or detected condition that may require attention, validation, suppression, escalation, investigation, or remediation.

An Alert is not automatically an Incident. It becomes or contributes to an Incident only after applicable criteria are met.

### 5.11 Incident

An unplanned interruption, degradation, compromise, policy violation, or loss of expected service, security, availability, integrity, or confidentiality that requires governed response.

### 5.12 Change

A governed modification to an Asset, Service, Configuration, Policy, Environment, Agreement, or other controlled object.

A Change includes its purpose, scope, risk, authority, plan, execution record, verification, and outcome as required by policy.

### 5.13 Project

A temporary, coordinated body of work intended to produce a defined outcome, deliverable, transition, or change under an established scope, ownership, schedule, and acceptance criteria.

### 5.14 Knowledge

Information intended to be retained, understood, reused, taught, referenced, or applied.

Examples include procedures, standards, configurations, diagrams, client notes, troubleshooting methods, architecture documents, and lessons learned.

An IT Glue document, SharePoint page, file, email, or conversation may contain or represent Knowledge, but the storage item is not the canonical definition of the knowledge itself.

### 5.15 Evidence

Information preserved to support, verify, challenge, or reproduce a fact, decision, action, condition, control, or outcome.

Evidence must retain source, collection time, provenance, tenant, integrity, classification, and permitted-use context.

### 5.16 Policy

An authoritative rule, requirement, constraint, standard, exception, or decision criterion governing behavior, access, work, data, or outcomes.

### 5.17 Decision

A recorded conclusion, selection, determination, disposition, risk acceptance, or judgment made by an authorized person, role, policy, or governed system process.

### 5.18 Approval

A specific authorization, denial, conditional authorization, or acknowledgement issued by a recognized authority for a defined scope, purpose, action, and period.

Approval is an object because it has identity, provenance, scope, authority, status, and audit requirements.

### 5.19 Capability

A stable business function Jason can provide, coordinate, or obtain independent of the provider or implementation used to deliver it.

Examples include ticket creation, endpoint inventory, mailbox investigation, evidence collection, scheduling, policy evaluation, or notification.

### 5.20 Connector

A governed interface through which Jason exchanges data, requests actions, or obtains capabilities from an external system or provider.

A Connector is part of Jason's governed world because its scope, authority, health, mappings, and audit behavior materially affect outcomes.

## 6. Supporting Object Forms

The following concepts should normally be represented as subtypes, attributes, records, or relationships rather than new top-level object types unless operational evidence demonstrates otherwise:

- Device — subtype of Asset;
- Configuration Item — an Asset, Service, or governed representation depending on the business meaning;
- Ticket or Case — provider representation of a Work Item;
- Document or Page — representation containing Knowledge or Evidence;
- Account or Mailbox — Identity, Asset, or Service representation depending on context;
- Contract Line or SKU — part of an Agreement or provider mapping;
- Schedule — timing metadata or a governed plan associated with another object;
- Credential — protected secret reference associated with an Identity or Connector, never the secret value in the canonical object model;
- Conversation — a communication record that may contain Requests, Knowledge, Evidence, Decisions, or Approvals;
- Configuration — governed properties of an Asset, Service, Connector, Policy, or implementation;
- Outcome — the verified result associated with a Request, Work Item, Change, Incident, Project, or Decision.

This approach prevents unnecessary object proliferation while preserving important business meaning.

## 7. Object Identity and Resolution

### 7.1 Canonical identifier

Jason assigns or recognizes one canonical identifier for each governed object.

### 7.2 External mappings

An object may map to multiple external records, including:

- Autotask company, configuration item, ticket, contract, project, or contact identifiers;
- Datto RMM site, device, alert, component, or job identifiers;
- IT Glue organization, configuration, flexible asset, password reference, or document identifiers;
- Microsoft tenant, user, group, device, mailbox, site, or service identifiers;
- provider-specific records from any future platform.

Each mapping must record the provider, connector, external identifier, mapping status, last verification time, and relevant tenant context.

### 7.3 Identity resolution

Jason may determine that records refer to the same object using verified identifiers, authoritative mappings, trusted attributes, or governed reconciliation rules.

When confidence is insufficient, Jason must preserve separate candidate objects or mark the mapping as unresolved rather than merging them silently.

### 7.4 Duplicate handling

Duplicate provider records do not automatically create duplicate canonical objects. Reconciliation must consider organizational context, ownership, authoritative sources, and evidence.

### 7.5 Supersession

When one object replaces another, Jason preserves both objects and records the supersession relationship and effective time. Historical audit and evidence must remain attached to the object that existed when the event occurred.

## 8. Source, Provenance, and Authority

Every material object must identify how Jason knows it exists.

Source classifications include:

- authoritative organizational record;
- verified external system state;
- direct observation;
- approved human declaration;
- contractual or policy record;
- discovered or inferred record;
- imported historical record.

A source may establish existence without establishing ownership, authority, correctness, or current status. Those properties require their own evidence and governance.

Provider data must not be treated as automatically authoritative merely because it is accessible through an API.

## 9. Object Creation Rules

A new canonical object may be created when:

1. a recognized source establishes that a distinct business thing exists;
2. the organization and tenant context are resolved;
3. the proposed object type is canonical or approved;
4. the object is not an unresolved duplicate of an existing object;
5. provenance and creation authority are recorded;
6. required classification and handling rules are applied.

Discovery may create a candidate object before full verification. Candidate status must remain visible until verification or disposition.

## 10. Object Type Admission Test

A proposed top-level object type must satisfy all of the following:

1. **Business meaning:** It represents a concept understood by the business, not merely by a product or API.
2. **Durability:** It would still exist if every current vendor or implementation changed.
3. **Distinct governance:** It requires its own lifecycle, ownership, authority, policy, audit, or evidence behavior.
4. **Non-duplication:** It cannot be modeled cleanly as an existing object, subtype, attribute, or relationship.
5. **Operational value:** At least one real workflow, decision, control, report, or service depends on the distinction.
6. **Common language:** Its definition can be made clear enough that business and technical stakeholders use it consistently.

Failure of any test means the concept should not yet become a new top-level object.

## 11. Constraints

1. No provider record may serve as Jason's sole canonical identity for an object.
2. No object may be acted upon without resolving its tenant and organizational context.
3. No object type may be added solely to mirror a vendor API or database schema.
4. No object may silently change type because a provider representation changes.
5. No inferred object may be represented as verified without supporting evidence.
6. No object merge may destroy provenance, history, audit, evidence, or external mappings.
7. No deletion may erase records required for legal, contractual, security, compliance, or audit purposes.
8. No secret value may be stored as a general object property; only a governed secret reference may be represented.
9. No cross-tenant object relationship may be created without explicit authority and policy evaluation.
10. No implementation may redefine a canonical object without an approved architecture change.

## 12. Security and Privacy Considerations

The Object Model must protect against:

- tenant confusion and object misassignment;
- duplicate identities causing access or reporting errors;
- unauthorized merging of client records;
- provider identifiers being mistaken for trusted authority;
- stale or unverified external mappings;
- secrets entering general object storage, prompts, logs, or reports;
- inferred ownership or approval authority;
- loss of provenance during import, synchronization, or migration;
- excessive collection of personal, client, or regulated information;
- retention beyond business, legal, or contractual need.

Implementations should store only the object attributes required for governed outcomes and should retrieve sensitive detail from authoritative systems only when needed.

## 13. MSP Examples

### 13.1 Autotask ticket

Autotask ticket 12345 is an external representation of a Jason Work Item. The Work Item retains its own canonical identity, tenant, requester, service context, policy, state, evidence, decisions, and outcome even if the PSA record is migrated or replaced.

### 13.2 Managed workstation

A workstation may appear in Datto RMM, Microsoft Intune, Autotask, IT Glue, Microsoft Entra, and security tools. Jason represents one Asset with several verified external mappings rather than treating each provider record as a separate machine.

### 13.3 Employee and accounts

A client employee is one Person. The employee's Microsoft 365 account, Duo account, VPN account, local Active Directory account, and application accounts are separate Identities related to that Person.

### 13.4 Knowledge and evidence

A troubleshooting procedure is Knowledge. A command output captured during a specific incident is Evidence. Both may exist in the same document, but Jason preserves their different purpose, lifecycle, authority, and reuse rules.

### 13.5 Alert and incident

A RocketCyber notification is an Alert. After validation shows unauthorized Tor activity affecting a client endpoint, Jason may create or relate an Incident and one or more Work Items. The original Alert remains preserved as source evidence.

### 13.6 Change approval

A firewall rule modification is a Change. The client's authorization is an Approval. The technician's implementation activity is a Task within a Work Item. The before-and-after configuration and test results are Evidence. The verified operational result is the Outcome associated with the Change.

## 14. Conformance Requirements

An implementation conforms to J-117 when it:

1. uses canonical business objects rather than treating vendor records as Jason's world model;
2. assigns every governed object a stable canonical identity;
3. resolves organization and tenant context according to J-120;
4. preserves source, provenance, mappings, and audit history;
5. distinguishes Person from Identity, Knowledge from Evidence, Alert from Incident, Request from Work Item, and Capability from Connector;
6. applies the Object Type Admission Test before introducing new top-level types;
7. represents uncertainty and unresolved mappings explicitly;
8. prevents secret values from entering the general object model;
9. supports later State, Relationship, and Event models without redefining the objects established here.

## 15. Dependencies and Successors

This model depends on:

- Jason Constitution and governance artifacts;
- J-003 Decision Architecture;
- J-120 Organizational Model.

This model is an authoritative dependency for:

- J-116 State Model;
- J-118 Relationship Model;
- J-119 Event Model;
- Identity, Knowledge, Policy, Evidence, Audit, Service, Connector, Security, and Data models;
- future schemas, APIs, workflows, interfaces, and implementations.

## 16. Architect's Rationale

Jason requires a stable understanding of the business before it can safely automate the systems that support the business. Without a canonical Object Model, each connector would import its own vocabulary and Jason would gradually become a collection of vendor-specific records.

This model deliberately limits the initial universe to twenty durable business objects. It separates the real-world concept from the provider representation, requires independent canonical identity, and establishes a high bar for adding new top-level types.

The model is intentionally conceptual rather than technical. Database structures, APIs, provider schemas, and application classes must implement this model, not redefine it. This keeps Jason understandable to business stakeholders, replaceable at the technology layer, and resistant to semantic drift.

## 17. Approval and Review

**Approval Status:** Approved as the canonical definition of what exists in Jason's world.  
**Review Trigger:** A demonstrated operational need that cannot be represented cleanly by an existing object, subtype, attribute, or relationship; a material change to J-120; or evidence that two canonical definitions conflict in practice.  
**Retirement Criteria:** Superseded only by an approved canonical model that preserves traceability and migration guidance for all dependent artifacts.
