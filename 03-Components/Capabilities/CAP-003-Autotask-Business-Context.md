# CAP-003: Autotask Business Context

**Status:** Live validated; convergence in progress  
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
- keep local LLM processing loopback-only for this pilot;
- pass bounded, business-relevant context to the local model rather than raw provider objects; and
- retire narrower duplicate implementations after replacement parity is proven.

## Canonical Autotask read capability family

CAP-003 expands the canonical connector with explicit read capabilities for:

- `autotask.company.search`;
- `autotask.contact.search`;
- `autotask.configuration.search`;
- `autotask.ticket.search`;
- `autotask.contract.search`; and
- `autotask.project.search`.

These capabilities resolve to provider GET operations through the existing `AutotaskConnector` and the existing `autotask.readonly` credential contract.

The lower-level generic entity capability remains connector infrastructure, but higher-level business workflows should request named canonical capabilities when a named capability exists.

## Business-context assembly

The first composed context is company-centered.

Given a company business name, Jason:

1. performs an exact company search;
2. requires exactly one exact company result;
3. derives the Autotask company identifier from that result;
4. binds subsequent related reads to that derived client boundary;
5. gathers bounded related contacts, configurations, tickets, contracts, and projects;
6. projects provider records into a bounded set of business-relevant fields for local reasoning;
7. invokes the approved loopback-only local LLM through the governed CAP-003 runtime; and
8. produces a structured briefing plus controlled evidence artifacts and durable orchestration history.

The operator is not required to supply the Autotask company ID.

## Local reasoning boundary

CAP-003 does not send entire Autotask provider objects to the local model.

The local-analysis projection:

- includes only selected business-relevant fields;
- bounds each related-record collection used for reasoning;
- truncates long text values;
- excludes provider/internal metadata that is not needed for the briefing;
- limits the local model context and response size; and
- treats all provider content as untrusted data rather than instructions.

This keeps the pilot practical on the CPU-only Jason host while strengthening privacy, determinism, and prompt-injection resistance.

## Live validation

On 2026-08-07, CAP-003 completed a governed live execution for Autotask company ID `208` using the business name `James Bales Financial LLC`.

The successful execution:

- resolved the company through the canonical Autotask read path;
- discovered provider company ID `208` rather than requiring it from the operator;
- read 16 contacts, 17 configurations, 25 tickets, 0 contracts, and 0 projects;
- invoked local model `qwen3:1.7b` through loopback-only Ollama;
- completed in approximately 98 seconds on the CPU-only pilot host;
- produced a structured business briefing with low confidence;
- created protected briefing and evidence artifacts outside the repository;
- persisted a four-event Central Orchestrator lifecycle ending in `orchestration.capability.completed`; and
- made no provider-side change.

Low-confidence model conclusions remain advisory interpretation. Durable provider facts and controlled evidence remain the authoritative basis for operational decisions.

## Boundary rules

CAP-003 fails closed when:

- the company name is empty;
- company lookup does not resolve to exactly one exact company;
- the provider response shape is invalid;
- a governed secret cannot be resolved;
- a provider read fails;
- a related read attempts to leave the discovered company boundary;
- a requested provider operation is not an approved canonical read capability;
- the local model is unavailable, times out, or violates the structured-response contract; or
- evidence would overwrite an existing artifact or be written inside the repository.

Related-record collection and local-model context are bounded to prevent accidental bulk extraction and unnecessary model processing.

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

## Next increment

The next CAP-003 increment is convergence and hardening:

- add CAP-003 to continuous integration and release validation;
- prove ticket-analysis parity through the broader CAP-003 architecture;
- migrate remaining operator, roadmap, and dashboard references;
- retire CAP-002 only after parity is proven;
- add regression protection against reintroducing the duplicate ticket-specific capability; and
- perform final documentation, release, and merge validation.
