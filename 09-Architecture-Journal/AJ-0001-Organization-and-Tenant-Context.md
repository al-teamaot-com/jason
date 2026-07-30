# AJ-0001 — Organization and Tenant Context Precede Implementation

**Observation:** Jason serves multiple organizations through common administrative platforms, automation engines, connectors, and reasoning providers.

**Realization:** A provider account, application company record, connector credential, or technical administrative role cannot be treated as the canonical representation of organizational ownership or authority.

**Decision:** Establish J-120 as the canonical Organizational Model. Every governed object and action must resolve explicit organization, tenant, ownership, authority, and trust-boundary context.

**Impact:** The Object, State, Relationship, Event, Identity, Policy, Audit, Security, and Connector models must depend on J-120. Implementations must preserve tenant context across prompts, agents, workflows, evidence, logs, and outputs.
