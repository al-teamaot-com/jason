# CAP-003: Autotask Business Context

**Status:** In progress  
**Owner:** Jason Architecture Authority

## Purpose

CAP-003 broadens Jason's use of Autotask from a ticket-first workflow into a governed business-context capability family.

Autotask is treated as a structured operational resource. Tickets remain important, but they are one business object among companies, contacts, configurations, contracts, projects, and other approved Autotask entities.

## Constitutional direction

CAP-003 follows these Project Jason principles:

- integrate before innovate;
- use the canonical Autotask connector rather than creating a capability-specific transport;
- expose business identifiers to operators and derive provider identifiers when deterministic;
- use narrow named read capabilities rather than a permanent `query everything` capability;
- keep provider reads observe-only by default;
- route higher-level execution through the Central Orchestrator;
- preserve identity, organization, client, correlation, and evidence context;
- retire narrower duplicate implementations after replacement parity is proven.

## Canonical Autotask read capability family

The first CAP-003 foundation expands the canonical connector with explicit read capabilities for:

- `autotask.company.search`;
- `autotask.contact.search`;
- `autotask.configuration_item.search`;
- `autotask.ticket.search`;
- `autotask.contract.search`; and
- `autotask.project.search`.

These capabilities all resolve to provider GET operations through the existing `AutotaskConnector` and the existing `autotask.readonly` credential contract.

The lower-level generic entity capability remains connector infrastructure, but higher-level business workflows should request named canonical capabilities when a named capability exists.

## Business-context assembly

The first composed context is company-centered.

Given a company business name, Jason:

1. performs an exact company search;
2. requires exactly one exact company result;
3. derives the Autotask company identifier from that result;
4. binds subsequent related reads to that derived client boundary;
5. gathers bounded related contacts, configurations, tickets, contracts, and projects; and
6. returns a structured in-memory business-context object for later governed reasoning.

The operator is not required to supply the Autotask company ID.

## Boundary rules

CAP-003 must fail closed when:

- the company name is empty;
- company lookup does not resolve to exactly one exact company;
- the provider response shape is invalid;
- a related read attempts to leave the discovered company boundary; or
- a requested provider operation is not an approved canonical read capability.

Related-record collection is bounded to prevent accidental bulk extraction.

## CAP-002 convergence and retirement

CAP-002 Ticket Intelligence is a validated transitional proof, not a permanent parallel architecture.

CAP-003 must absorb the reusable CAP-002 behavior before CAP-002 is retired. Retirement requires all of the following:

1. CAP-003 can reproduce the governed ticket-analysis use case with equal or stronger controls.
2. Ticket analysis uses the broader Autotask business-context capability family and the same Central Orchestrator boundary.
3. Local LLM processing remains governed and local-only where required.
4. Existing ticket-analysis regression tests pass through the CAP-003 path.
5. Operator commands, capability registration, documentation, roadmap references, and dashboard status are migrated.
6. CAP-002 code, tests, registration, and ticket-specific duplicate orchestration are removed.
7. Regression tests deny reintroduction of the retired duplicate capability.

CAP-002 is not removed until replacement parity is proven.

## Planned next increment

The next CAP-003 increment will place company-context assembly behind the Central Orchestrator, add local-LLM business briefing generation, and perform a governed live company-context validation. Ticket-analysis parity and CAP-002 retirement follow after that validation succeeds.
