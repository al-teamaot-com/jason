# J-100 — Jason Reference Architecture

## Purpose

This document defines the enduring architectural building blocks of Jason. It intentionally defines *what must exist*, not *how it is implemented*.

## Authoritative Components

### Governance
Defines mission, policy, authority, and architectural compliance.

### Orchestration
Coordinates work, routes requests, and enforces governance. It never embeds implementation-specific logic.

### Capability Registry
Defines the capabilities Jason provides. Capabilities are enduring; implementations are replaceable.

### Connector Framework
Provides governed boundaries between Jason capabilities and external systems. Connectors are replaceable implementations and shall never define Jason's architecture.

### Identity
Represents people, systems, services, and organizations independently of any identity provider.

### Context
Maintains the information required for Jason to perform work consistently across interactions.

### Knowledge
Preserves institutional knowledge, evidence, and architectural artifacts as durable organizational assets.

### Policy
Applies governance, approvals, security, compliance, and business rules before actions are taken.

### Audit
Records significant decisions, actions, approvals, and evidence sufficient for independent review.

### Communications
Provides controlled interaction with people and external systems through governed interfaces.

### Monitoring
Observes the health of Jason's components and reports conditions affecting dependable operation.

## Architectural Rule

No component may bypass Governance, Policy, or Audit.

No component shall depend directly on a specific external product, provider, or implementation. All external interaction occurs through the Connector Framework.

## Definition of Completion

This document is complete when every future architectural element can be placed within one or more of these components without changing their fundamental responsibilities.