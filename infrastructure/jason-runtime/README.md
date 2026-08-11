# Jason Runtime Service

This deployment runs the governed Project Jason conversational runtime as a separate container. OpenClaw remains the Microsoft Teams interface and transport provider; it does not become Jason authority and the Jason source tree is not embedded into the OpenClaw image.

## Runtime topology

```text
Microsoft Teams
    |
    v
OpenClaw (Bot Framework authenticated transport)
    |
    | signed conversation.turn envelope
    v
Jason Runtime :8080 (Docker-network only)
    |
    +--> JKD-001 identity and authority state
    +--> governed capability/provider resolution
    +--> System Registry read-only operational-state provider
    +--> OpenBao ephemeral connector secret resolution
    +--> Datto RMM provider capability
    +--> Microsoft Graph identity enrichment
    +--> AWS SES governed email provider
    +--> local Ollama bounded structured reasoning
    |
    | governed reply on authenticated return path
    v
OpenClaw
    |
    v
Microsoft Teams
```

Jason does not publish port 8080 to the host. The runtime joins only the existing local bridge networks needed to reach OpenClaw, OpenBao, and Ollama.

## Security boundary

- Process UID/GID is `1000:1000`, matching the owner of the existing Jason state.
- Root filesystem is read-only and Linux capabilities are dropped.
- `/var/lib/jason/authority` and `/var/lib/jason/openclaw` remain the durable writable state boundaries.
- The trusted-key subdirectory is over-mounted read-only.
- OpenClaw private signing keys are never mounted into the Jason runtime.
- Only active public keys from the governed trusted-key registry authenticate OpenClaw machine envelopes.
- OpenBao AppRole credential files are mounted read-only and used only by the applicable provider secret resolver.
- Datto, Microsoft, and AWS credential values and access tokens are not exposed to the reasoning layer.
- Ollama receives provider-neutral planning metadata or provider evidence only for bounded structured interpretation. It cannot select providers, invoke connectors, or assert final evidence values.
- The System Registry query provider is deterministic and read-only. It cannot mutate declared state, lifecycle history, production services, governance, or secret values.
- Central Orchestrator and JKD-001 remain the execution and identity-authority boundaries.

## Required deployment values

The compose deployment requires the following host-side environment variables before rendering, building, or starting the runtime:

- `JASON_OLLAMA_MODEL` — an already-installed local Ollama model approved for bounded Jason reasoning.
- `JASON_OPENBAO_ROLE_ID_HOST_PATH` — host path to the base Jason runtime AppRole RoleID file.
- `JASON_OPENBAO_SECRET_ID_HOST_PATH` — host path to the base Jason runtime AppRole SecretID file.
- `JASON_SES_OPENBAO_ROLE_ID_HOST_PATH` — host path to the AWS SES AppRole RoleID file.
- `JASON_SES_OPENBAO_SECRET_ID_HOST_PATH` — host path to the AWS SES AppRole SecretID file.
- `JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH` — host path to the Microsoft Graph AppRole RoleID file.
- `JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH` — host path to the Microsoft Graph AppRole SecretID file.

The compose file is authoritative for the current required variable set. If this list differs from `compose.yaml`, treat that as documentation drift and correct the documentation before relying on it.

Do not place RoleIDs, SecretIDs, Datto credentials, Microsoft tokens, AWS credentials, signing private keys, or other secret values directly in Compose environment values. The host-side variables above identify protected files; they do not contain the credential values themselves.

For an in-place upgrade of an already running pilot, the current container's mount sources and non-secret `JASON_OLLAMA_MODEL` setting may be inspected and reused as deployment inputs without reading or printing the mounted credential-file contents.

## Conversation contract

OpenClaw POSTs a signed `conversation.turn` JSON envelope to:

`http://jason-runtime:8080/v1/openclaw/teams/conversation`

The envelope may contain authenticated Microsoft transport evidence and human message text. It may not assert Jason principal, organization/client scope, capability, provider, connector, shell command, or agent route.

For a completed request the runtime returns a governed `reply` object on the same HTTP response. OpenClaw is responsible only for delivering `reply.text` to `reply.conversation_id` and preserving the returned handoff/correlation identifiers in its delivery evidence. It must not reinterpret the reply as a new agent instruction or bypass Jason for provider work.

## System Registry query contract

The runtime currently registers the provider-neutral, read-only capabilities:

- `system.registry.search`
- `system.registry.read`
- `system.registry.trace`

They resolve through the normal Central Orchestrator path to the deterministic internal `system_registry` provider. Their authoritative source is the governed production registry plus append-only lifecycle-event history.

These capabilities are operational-state readers only. They do not grant authority to alter topology, repair drift, change lifecycle state, restart services, or expose credential values.

## Operational sequence

1. Validate the feature branch and runtime tests.
2. Confirm the selected local Ollama model is installed.
3. Confirm all required OpenBao AppRole host paths exist without printing their contents.
4. Render `docker compose config` and verify there are no published ports.
5. Preserve a rollback reference to the currently running runtime image before an in-place rebuild.
6. Build the image.
7. Start/recreate only the Jason runtime service and verify `/healthz` from the existing Docker network boundary.
8. Rerun the bounded System Registry physical host verifier after the runtime change.
9. Run governed System Registry search/read/trace production proof through the Central Orchestrator.
10. Capture correlated authority, orchestration, provider, and response evidence before promoting any newly configured System Registry query entity to `verified`.
11. For consequential capabilities such as email, preserve their separate capability-specific approval and proof requirements.

Production deployment remains subject to Jason's normal branch, test, release-validation, PR, governance-review, merge, verification, and audit controls.
