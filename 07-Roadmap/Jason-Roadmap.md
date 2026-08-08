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
5. **J-119 Event Model — active draft foundation model**

## Integrated Provider / Infrastructure Foundations

The following provider-neutral foundations are integrated and available to support later canonical-model and capability work:

- **INF-010 Microsoft Cloud Platform Foundation — integrated**
- **INF-011 Kaseya Resource Platform Foundation — integrated**
- **INF-012 Cross-Provider Relationship Foundation — integrated**
- **INF-013 Artifact/Evidence Storage Foundation — integrated**

Their production bindings and provider-specific expansion remain separate governed follow-on work. Integration of a foundation does not itself authorize live provider access, mutation, cross-tenant activity, or autonomous execution.

## Current Primary Workstream

**J-119 Event Model** is the current canonical-model priority.

J-119 must define a provider-neutral representation of material occurrences while preserving the distinction between canonical events, provider/source observations, evidence artifacts, orchestration audit events, state, relationships, and execution authority.

## Phase Principle

**Model the business, not the software.**

Jason represents durable MSP business concepts independently of the products, APIs, databases, and providers used to implement them.

## Dependency Rule

Each model must be usable as an authoritative dependency by the model that follows it. New artifacts should evolve existing models where practical rather than accumulate unnecessary parallel concepts.
