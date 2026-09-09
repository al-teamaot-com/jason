# CAP-003: Autotask Business Context

**Status:** Complete; live validated and converged  
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

CAP-003 uses explicit read capabilities for:

- `autotask.company.search`;
- `autotask.contact.search`;
- `autotask.configuration.search`;
- `autotask.ticket.search`;
- `autotask.contract.search`; and
- `autotask.project.search`.

These capabilities resolve to provider GET operations through the existing `AutotaskConnector` and the existing `autotask.readonly` credential contract.

## Business-context assembly

The first composed context is company-centered.

Given a company business name, Jason:

1. performs an exact company search;
2. requires exactly one exact company result;
3. derives the Autotask company identifier from that result;
4. binds subsequent related reads to that derived client boundary;
5. gathers bounded related contacts, configurations, tickets, contracts, and projects;
6. optionally resolves a focused ticket explicitly by ticket number and verifies it belongs to the resolved company;
7. projects provider records into a bounded set of business-relevant fields for local reasoning;
8. invokes the approved loopback-only local LLM through the governed CAP-003 runtime; and
9. produces a structured briefing plus controlled evidence artifacts and durable orchestration history.

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

The runtime explicitly labels record counts as bounded reads. Evidence records both the operator-requested company name and the canonical provider-resolved company name, avoiding ambiguity between input identity and authoritative provider identity.

## Live business-context validation

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

The counts above are bounded retrieved records, not provider-wide totals.

## Ticket-analysis parity validation

On 2026-08-07, execution `cap003-ticket-parity-live-004` proved that the broader CAP-003 architecture can replace the former CAP-002 ticket-intelligence runtime.

The execution:

- used the same `autotask.business.context` capability rather than a second ticket-specific orchestration path;
- resolved `James Bales Financial LLC` to company ID `208`;
- explicitly resolved focused ticket `T20260805.0064` through `autotask.ticket.search`;
- verified the focused ticket belonged to the resolved company boundary;
- included the focused ticket even though it was outside the normal bounded company ticket window;
- invoked local model `qwen3:1.7b` locally;
- completed in approximately 117 seconds on the CPU-only pilot host;
- produced protected evidence with `provider_side_change=false` and no raw provider content persisted; and
- persisted the expected four-event orchestration lifecycle ending in `orchestration.capability.completed`.

Low-confidence model conclusions remain advisory interpretation. Durable provider facts and controlled evidence remain the authoritative basis for operational decisions.

## CAP-002 retirement

CAP-002 Ticket Intelligence was a successful transitional proof. After live CAP-003 ticket-focus parity was proven, the duplicate CAP-002 runtime package, tests, and ticket-specific operator command were removed.

The historical CAP-002 document remains as institutional memory and is marked retired/superseded. Release regression tests deny reintroduction of the retired `support.ticket.analyze` implementation path.

## Continuous validation

The repository validation workflow now includes a dedicated CAP-003 job that:

- compiles CAP-003 and its shared runtime dependencies;
- runs the CAP-003 test suite; and
- runs the CAP-003 convergence release gates.

The showcase installer also restarts Prometheus and Grafana after configuration updates and waits for both services to report healthy, preventing the stale scrape/provisioning state observed during CAP-003 validation.

## Boundary rules

CAP-003 fails closed when:

- the company name is empty;
- company lookup does not resolve to exactly one exact company;
- a focused ticket is missing, ambiguous, or belongs to another company;
- the provider response shape is invalid;
- a governed secret cannot be resolved;
- a provider read fails;
- a requested provider operation is not an approved canonical read capability;
- the local model is unavailable, times out, or violates the structured-response contract; or
- evidence would overwrite an existing artifact or be written inside the repository.

Related-record collection and local-model context are bounded to prevent accidental bulk extraction and unnecessary model processing.

## Closeout

CAP-003 is complete for this increment. It establishes the canonical governed path for company-centered Autotask reasoning and focused ticket analysis without maintaining parallel ticket-specific architecture.

Future Autotask intelligence should build on this capability family rather than recreate CAP-002-style provider-specific orchestration.
