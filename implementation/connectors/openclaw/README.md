# OpenClaw Connector

This package is the provider-neutral ingress boundary between OpenClaw and the Jason orchestrator.

## Purpose

OpenClaw supports two distinct governed ingress shapes:

1. **Named capability requests** for already-structured machine/service work.
2. **Teams conversation turns** where OpenClaw supplies authenticated Microsoft transport evidence and human text only; Jason binds identity, interprets the resource inquiry, evaluates authority/policy, resolves capabilities/providers, verifies evidence, and renders the response.

These paths must not be conflated. A normal Teams conversation must not allow OpenClaw to assert a Jason principal, organization, client, capability, provider, connector, shell command, or agent route.

## Non-negotiable boundaries

- OpenClaw never calls Autotask, Datto RMM, IT Glue, Microsoft Graph, or another provider directly through this connector.
- OpenClaw cannot submit an arbitrary URL or HTTP request.
- Agents do not possess authority.
- Client scope comes from Jason identity/authority state, not from free-form prompt text.
- Unknown capabilities and unresolved conversational intents fail closed.
- Duplicate request IDs fail closed.
- Connector failures return sanitized errors and retain detail only in correlated audit records.
- No secrets are accepted in request payloads.
- Deterministic capability dispatch does not require an LLM.
- Reasoning used for conversational interpretation may propose provider-neutral resource/fact structure, but cannot choose or invoke a provider.

## Named capability request example

```json
{
  "request_id": "req-1",
  "correlation_id": "corr-1",
  "capability": "autotask.ticket.get",
  "requested_mode": "observe",
  "execution_mode": "deterministic",
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

For backward compatibility, existing named-capability envelopes that omit `execution_mode` default to `deterministic`. `requested_mode` remains the authority/permission mode for this transport contract.

## Teams conversation turn example

The application-layer envelope is signed by the registered OpenClaw machine identity. The signature and key metadata are omitted below for readability.

```json
{
  "kind": "conversation.turn",
  "request_id": "req-conversation-1",
  "correlation_id": "corr-conversation-1",
  "issued_at": "2026-08-10T19:30:00+00:00",
  "expires_at": "2026-08-10T19:32:00+00:00",
  "nonce": "unique-nonce",
  "channel": "msteams",
  "text": "Who is logged into AOT-50282?",
  "transport_identity": {
    "microsoft_tenant_id": "<tenant-id>",
    "microsoft_object_id": "<object-id>",
    "authentication_assurance": "botframework-authenticated"
  },
  "conversation_id": "<teams-conversation-id>",
  "message_id": "<teams-message-id>"
}
```

This envelope intentionally contains **no** `principal_id`, `organization_id`, `client_id`, `capability`, `provider`, `connector`, or command/tool selection. Those are Jason-owned decisions downstream of transport authentication.

## Teams conversation trust chain

`Teams -> Bot Framework authentication in OpenClaw -> signed OpenClaw machine envelope -> Jason conversation ingress -> Microsoft identity binding -> provider-neutral resource inquiry -> capability metadata planning -> JKD-001 authority -> Central Orchestrator -> provider resolution -> governed connector -> evidence verification -> Teams response`

The conversation ingress authenticates the OpenClaw machine signature first, then validates envelope shape, freshness and replay protection. Message text is not written to its audit events; identifiers and correlation metadata are recorded instead.

## Integration points

The reference package defines protocols for these Jason services:

- Capability Dispatcher
- Identity and Authority evaluator
- Audit sink
- Replay/idempotency store
- Teams conversation flow

Production transport authentication should use the existing registered OpenClaw Ed25519 machine identity (or an approved successor). Private signing keys remain on the OpenClaw side and must never appear in prompts, envelopes, logs, or repository content.

## Local validation

```bash
cd implementation/connectors/openclaw
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```
