# OpenClaw Connector

This package is the provider-neutral ingress boundary between OpenClaw and the Jason orchestrator.

## Purpose

OpenClaw may submit a structured request for a named Jason capability. The connector validates the request contract, rejects replayed request IDs, asks the Identity and Authority service for a decision, records audit events, and dispatches only registered capabilities.

The connector does not require an AI provider or AI API credential. A request such as `autotask.ticket.get` is ordinary deterministic software execution after the capability and authority checks pass.

## Non-negotiable boundaries

- OpenClaw never calls Autotask, Datto RMM, IT Glue, Microsoft Graph, or another provider directly through this connector.
- OpenClaw cannot submit an arbitrary URL or HTTP request.
- Agents do not possess authority.
- Client scope comes from the validated principal and execution context, not from free-form prompt text.
- Unknown capabilities fail closed.
- Duplicate request IDs fail closed.
- Connector failures return sanitized errors and retain detail only in correlated audit records.
- No secrets are accepted in the request payload.
- No LLM is involved in deterministic capability dispatch.

## Request example

```json
{
  "request_id": "req-1",
  "correlation_id": "corr-1",
  "capability": "autotask.ticket.get",
  "requested_mode": "observe",
  "arguments": {
    "ticket_id": "12445279"
  },
  "principal": {
    "principal_id": "person-al",
    "channel": "teams",
    "external_user_id": "openclaw-user-1",
    "organization_id": "aot",
    "client_id": "client-jbf",
    "authentication_assurance": "external_authenticated"
  }
}
```

## Integration points still required

The reference package defines protocols for these Jason services:

- Capability Dispatcher
- Identity and Authority evaluator
- Audit sink
- Replay/idempotency store

Production transport authentication belongs outside the package and should use a short-lived machine identity, mutual TLS, or signed requests. Transport credentials must be retrieved through the Secrets Broker and must never appear in OpenClaw prompts or capability arguments.

## Local validation

```bash
cd implementation/connectors/openclaw
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```
