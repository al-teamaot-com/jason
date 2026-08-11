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
    +--> OpenBao ephemeral connector secret resolution
    +--> Datto RMM provider capability
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
- OpenBao AppRole credential files are mounted read-only and used only by the connector secret resolver.
- Datto credentials and access tokens are not exposed to the reasoning layer.
- Ollama receives provider-neutral planning metadata or provider evidence only for bounded structured interpretation. It cannot select providers, invoke connectors, or assert final evidence values.
- Central Orchestrator and JKD-001 remain the execution and identity-authority boundaries.

## Required deployment values

The compose deployment requires these host-side environment variables before rendering or starting it:

- `JASON_OLLAMA_MODEL` - an already-installed local Ollama model approved for bounded Jason reasoning.
- `JASON_OPENBAO_ROLE_ID_HOST_PATH` - host path to the Jason runtime AppRole RoleID file.
- `JASON_OPENBAO_SECRET_ID_HOST_PATH` - host path to the Jason runtime AppRole SecretID file.

Do not place the RoleID, SecretID, Datto credentials, Graph tokens, signing private keys, or other secrets directly in Compose environment values.

## Conversation contract

OpenClaw POSTs a signed `conversation.turn` JSON envelope to:

`http://jason-runtime:8080/v1/openclaw/teams/conversation`

The envelope may contain authenticated Microsoft transport evidence and human message text. It may not assert Jason principal, organization/client scope, capability, provider, connector, shell command, or agent route.

For a completed request the runtime returns a governed `reply` object on the same HTTP response. OpenClaw is responsible only for delivering `reply.text` to `reply.conversation_id` and preserving the returned handoff/correlation identifiers in its delivery evidence. It must not reinterpret the reply as a new agent instruction or bypass Jason for provider work.

## Operational sequence

1. Validate the feature branch and runtime tests.
2. Confirm the selected local Ollama model is installed.
3. Confirm the dedicated OpenBao AppRole credential file paths without printing their contents.
4. Render `docker compose config` and verify there are no published ports.
5. Build the image.
6. Start the runtime and verify `/healthz` from the OpenClaw network.
7. Configure the OpenClaw Teams ingress adapter to forward authenticated turns as signed envelopes and deliver only the governed return-path reply.
8. Run an end-to-end Teams query through the Central Orchestrator and Datto RMM.
9. Capture correlated authority, orchestration, connector, and delivery evidence before declaring the path operational.

Production deployment remains subject to Jason's normal branch, test, release-validation, PR, governance-review, and merge controls.
