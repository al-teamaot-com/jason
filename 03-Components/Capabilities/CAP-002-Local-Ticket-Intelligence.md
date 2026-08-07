# CAP-002: Local Ticket Intelligence

**Status:** Pilot

## Purpose

CAP-002 turns the existing governed Autotask read capability and the local Jason LLM into one useful technician-facing workflow.

The operator supplies a unique Autotask ticket number and identity context. The Central Orchestrator resolves the named capability `support.ticket.analyze`, selects the governed local provider, invokes the registered implementation, persists orchestration lifecycle events, and returns a structured technician briefing.

## Constitutional alignment

CAP-002 preserves the existing architecture instead of creating shortcut paths:

- **Central orchestration:** the technician requests one named capability through the Central Orchestrator.
- **Integrate before innovate:** Autotask access reuses the canonical `autotask.readonly` connector and AppRole contract.
- **Do not put a band-aid on it; fix it:** the canonical Autotask live-read boundary was extended to return an ephemeral ticket snapshot rather than introducing a second ticket transport.
- **Least authority:** the workflow is read-only and creates no Autotask-side change.
- **Local processing:** ticket content is sent only to the loopback Ollama endpoint at `127.0.0.1:11434` during this pilot.
- **Evidence before assertion:** Autotask read evidence, derived briefing evidence, CAP-002 evidence, and durable orchestration events are retained.
- **Data minimization:** the standard Autotask evidence remains hash-backed and excludes raw title and description values.
- **Prompt-injection boundary:** ticket title and description are explicitly treated as untrusted data, never as instructions.
- **One attempt:** the pilot performs no hidden retries or autonomous recovery.

## Capability contract

Canonical capability:

```text
support.ticket.analyze
```

Version:

```text
1.0
```

Pilot execution mode:

```text
local_ai
```

Provider:

```text
jason.local-ticket-intelligence
```

Local model:

```text
qwen3:1.7b
```

## Execution flow

1. The operator submits a ticket number, principal ID, and organization ID.
2. The Central Orchestrator resolves `support.ticket.analyze` through the Kernel capability registry, provider registry, and execution policy engine.
3. The registered CAP-002 invoker calls the canonical governed Autotask read service.
4. Autotask returns exactly one ticket and the company boundary is derived from that authoritative ticket record.
5. The ticket title and description remain in memory for the analysis step.
6. The local Ollama model receives the ticket as untrusted data and produces structured JSON.
7. Jason writes a technician briefing artifact and CAP-002 evidence outside the repository.
8. The Central Orchestrator records the correlated execution lifecycle in the durable event store.
9. The operator receives the summary, likely causes, recommended diagnostic steps, escalation flags, confidence, and artifact references.

## Persisted artifacts

The workflow creates three JSON artifacts under the configured evidence directory:

- canonical Autotask read evidence;
- the derived technician briefing;
- CAP-002 execution evidence linking the Autotask evidence, briefing checksum, local model, identity context, and execution ID.

The Autotask evidence contains hashes of the ticket title and description rather than the raw source text.

The technician briefing is derived work product and may contain a concise summary of ticket details. It is protected with mode `600` and is not stored in the repository.

## Check-only mode

Check-only mode runs capability resolution and policy evaluation through the Central Orchestrator but performs no Autotask request and no Ollama request.

Durable orchestration lifecycle events may still be written because check-only itself is an auditable governance action.

## Explicit exclusions

CAP-002 does not:

- modify an Autotask ticket;
- post notes or status changes;
- run Datto RMM commands;
- contact hosted AI providers;
- permit direct agent-to-agent communication;
- automatically remediate the issue;
- retry, resume, replay, or recover an execution;
- treat model output as verified fact;
- bypass technician judgment or existing approval requirements.

## Pilot success criteria

The pilot is successful when one authorized ticket can be read through the canonical connector, analyzed by the local model through the Central Orchestrator, returned as a useful structured technician briefing, and reconstructed later from durable evidence without exposing credentials or writing back to Autotask.
