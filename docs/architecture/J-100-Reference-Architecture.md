# J-100 — Jason Reference Architecture

## Purpose

This document defines the enduring architectural building blocks of Jason. It intentionally defines *what must exist*, not *how it is implemented*.

## Authoritative Components

### Governance
Defines mission, policy, authority, and architectural compliance.

### Orchestration
Coordinates work, routes requests, and enforces governance. It never embeds implementation-specific logic.

### System Registry
Maintains Jason's authoritative, machine-readable operational topology and system-state record. It relates declared, observed, and verified state for production components, capabilities, providers, dependencies, identity bindings, governance paths, credential references, deployments, and verification methods. It is authoritative for operational description but never self-authorizing and never silently remediates drift.

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
Records significant decisions, actions, approvals, changes, and evidence sufficient for independent review and historical reconstruction.

### Communications
Provides controlled interaction with people and external systems through governed interfaces.

### Monitoring
Observes the health and material operational state of Jason's components. Monitoring may supply observed-state evidence to the System Registry but does not redefine declared state or independently authorize remediation.

## Architectural Rule

No component may bypass Governance, Policy, or Audit.

No component shall depend directly on a specific external product, provider, or implementation. All external interaction occurs through the Connector Framework.

No production component, capability, provider, dependency, identity binding, or governance path is considered operational until represented in the System Registry with a defined verification method.

The System Registry describes and verifies operational topology; the Central Orchestrator remains the sole coordination authority for governed changes and remediation.

Human-readable names, hostnames, labels, aliases, prefixes, site names, and similar values are resource selectors, not durable resource identity. Jason must never promote a selector to identity because it resembles an internal naming convention or because a provider returned a first result.

Resource discovery must preserve enough candidate results to detect ambiguity. A selector may resolve automatically only when governance and authoritative provider evidence leave exactly one authorized candidate and that candidate exposes a durable resource identifier. If multiple authorized candidates remain, Jason must fail closed and request disambiguation rather than guessing, choosing the first result, or leaking candidate details outside the requester's authority scope.

Once a durable resource identifier has been resolved, subsequent operations should use that identifier whenever the provider supports it. Provider-specific identifiers remain behind the Connector Framework and are carried through governed capability contracts rather than embedded in conversational assumptions or workflow-specific scripts.

## Definition of Completion

This document is complete when every future architectural element can be placed within one or more of these components without changing their fundamental responsibilities.
