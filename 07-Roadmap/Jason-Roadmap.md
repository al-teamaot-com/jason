# Jason Roadmap

## Foundation Phase

- Governance and constitutional principles — established
- Decision architecture — established
- Vendor and implementation independence — established
- Common-language and lexicon direction — established

## Jason's World — Canonical Models Phase

1. **J-120 Organizational Model — approved foundation model**
2. **J-117 Object Model — approved foundation model**
3. **J-116 State Model — approved foundation model**
4. **J-118 Relationship Model — approved foundation model**
5. **J-119 Event Model — approved foundation model**

The initial canonical-model foundation set is now complete.

## Integrated Provider / Infrastructure Foundations

The following provider-neutral foundations are integrated and available to support implementation work:

- **INF-010 Microsoft Cloud Platform Foundation — integrated**
- **INF-011 Kaseya Resource Platform Foundation — integrated**
- **INF-012 Cross-Provider Relationship Foundation — integrated**
- **INF-013 Artifact/Evidence Storage Foundation — integrated**

Their production bindings and provider-specific expansion remain separate governed work. Integration of a foundation does not itself authorize live provider access, mutation, cross-tenant activity, or autonomous execution.

## Current Primary Workstream

With J-119 approved, the next primary workstream is the **first governed provider/resource convergence slice**.

Preferred implementation sequence:

1. converge existing IT Glue and Datto RMM reads behind the INF-011 generic resource gateway;
2. bind resulting provider resource evidence to INF-012 relationship evaluation through the Central Orchestrator;
3. emit J-119 canonical observations/events only through governed normalization boundaries;
4. pass large supporting evidence through INF-013 artifact/evidence references;
5. preserve existing CAP-001/CAP-003 Autotask behavior and avoid creating provider-specific one-off capability names where the generic resource model applies.

This slice should remain read-only until its identity, tenant, evidence, relationship, event, audit, and policy boundaries are proven.

## Queued Follow-ons

After the first IT Glue + Datto RMM convergence slice:

- governed OpenBao certificate binding and controlled Microsoft test-tenant onboarding for INF-010;
- additional Kaseya/security provider adapters only where verified APIs exist;
- first approved physical artifact/evidence store binding for INF-013;
- broader cross-provider relationship and event normalization.

### Governed Technician Access / RBAC — accepted design, queued

Implement exactly four human access levels for Jason:

- **Owner** — full authority. May read, write, execute, approve, administer, and modify Jason's Constitution, governance/security policies, authorization model, role definitions, approval rules, and provider/configuration boundaries.
- **Admin** — full operational administration. May investigate and perform authorized operational remediation, but may not modify the Constitution, governance/security policies, role definitions, approval rules, Owner authority, or elevate their own authority.
- **Tech** — may read anything within their authorized scope and may ask Jason to run approved Datto RMM components/scripts on positively identified devices. No governance, authorization, role, or unrestricted provider-administration changes. Higher-risk actions remain subject to policy and approval.
- **RO (ReadOnly)** — limited allowlisted read-only access. No writes, execution, approval authority, or information release outside the user's permitted scope.

Authorization design requirements:

- Keep **role** separate from **scope**. Role controls what classes of action a person may perform; scope controls which clients, tenants, providers, resources, or devices they may access.
- Compute effective authorization from **role + scope + action risk** through the Central Orchestrator; model discretion must never bypass the authorization decision.
- Govern Tech component execution through an approved component/action catalog and risk classification. Routine diagnostic/remediation components may be Tech-executable; destructive actions, security-agent removal, broad/mass deployment, identity/security-control changes, and similar high-risk actions require elevated authority or approval.
- Only **Owner** may change the authorization model itself, Owner membership/authority, constitutional controls, or the policy that defines the four access levels.
- Prevent self-elevation and privilege escalation by Admin, Tech, or RO users.
- Require positive target resolution before any device execution; ambiguous or incomplete endpoint resolution must fail closed.
- Make effective permissions explainable and auditable so Jason can answer what a user is allowed to do and record both permitted and denied authorization decisions.

## Phase Principle

**Model the business, not the software.**

Jason represents durable MSP business concepts independently of the products, APIs, databases, and providers used to implement them.

## Dependency Rule

Each model and capability must be usable as an authoritative dependency by what follows it. New artifacts should evolve existing models where practical rather than accumulate unnecessary parallel concepts.
