"""Apply the Conversation Experience as a reversible runtime composition cutover.

This module deliberately reuses the already-composed governed runtime dependencies rather
than duplicating composition. During migration, the existing Teams flow is built as the
rollback path and this wrapper replaces only the conversational flow object. Identity,
request construction, Central Orchestrator, capability registry, provider execution,
OpenClaw authentication/replay/audit, and return transport remain the same objects.
"""

from __future__ import annotations

import os
from dataclasses import replace

from connectors.core.contracts import ConnectorContext
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from orchestrator.governed_hosted_reasoning import (
    GovernedHostedReasoningClient,
    minimum_evidence_payload,
)
from orchestrator.hosted_reasoning_egress import HostedReasoningEgressClassifier
from orchestrator.hosted_reasoning_registration import (
    OPENAI_CONVERSATION_EVIDENCE_CAPABILITY,
    OPENAI_CONVERSATION_PROVIDER_ID,
)
from orchestrator.openai_reasoning import OpenAIStructuredJsonClient
from orchestrator.teams_request_factory import GovernedTeamsOrchestrationRequestFactory

from .conversation_experience_cutover import (
    ConversationExperienceCutoverSettings,
    select_conversation_experience_flow,
)
from .http import RuntimeHttpApplication
from .return_path import OpenClawReturnPathConversationIngress


def apply_conversation_experience_cutover(
    application: RuntimeHttpApplication,
    *,
    runtime_settings,
    environ: dict[str, str] | None = None,
) -> RuntimeHttpApplication:
    """Replace only the conversation flow when the new experience flag is enabled."""

    env = os.environ if environ is None else environ
    settings = _settings_from_env(runtime_settings=runtime_settings, environ=env)
    if not settings.enabled:
        return application

    outer = application.ingress
    if not isinstance(outer, OpenClawReturnPathConversationIngress):
        raise RuntimeError(
            "Conversation Experience requires the canonical OpenClaw return-path ingress"
        )
    governed = outer.ingress
    fallback_flow = getattr(governed, "flow", None)
    if fallback_flow is None:
        raise RuntimeError(
            "Conversation Experience could not locate the governed conversation flow"
        )

    identity_binder = getattr(fallback_flow, "identity_binder", None)
    request_factory = getattr(fallback_flow, "request_factory", None)
    orchestrator = getattr(fallback_flow, "orchestrator", None)
    transport = getattr(fallback_flow, "transport", None)

    if identity_binder is None or request_factory is None or orchestrator is None or transport is None:
        raise RuntimeError(
            "Conversation Experience rollback flow does not expose canonical governed dependencies"
        )
    if not isinstance(request_factory, GovernedTeamsOrchestrationRequestFactory):
        raise RuntimeError(
            "Conversation Experience requires the canonical governed Teams request factory"
        )
    capabilities = request_factory.capabilities
    if capabilities is None:
        raise RuntimeError(
            "Conversation Experience requires runtime Capability Registry access through the request factory"
        )
    if transport is not outer.transport:
        raise RuntimeError(
            "Conversation Experience requires the existing flow and return path to share one transport"
        )

    (
        hosted_kernel_client,
        hosted_evidence_client,
    ) = _build_hosted_reasoning_clients(
        settings=settings,
        runtime_settings=runtime_settings,
        environ=env,
        governance=application.governance,
    )

    new_flow = select_conversation_experience_flow(
        settings=settings,
        fallback_flow=fallback_flow,
        capabilities=capabilities,
        ollama_url=runtime_settings.ollama_url,
        default_ollama_model=runtime_settings.ollama_model,
        identity_binder=identity_binder,
        request_factory=request_factory,
        orchestrator=orchestrator,
        transport=transport,
        audit=application.governance.orchestration_events,
        hosted_kernel_client=hosted_kernel_client,
        hosted_evidence_client=hosted_evidence_client,
    )

    try:
        new_governed = replace(governed, flow=new_flow)
        new_outer = replace(outer, ingress=new_governed)
        return replace(application, ingress=new_outer)
    except TypeError as error:
        raise RuntimeError(
            "Conversation Experience requires dataclass-based canonical ingress composition"
        ) from error


def _settings_from_env(*, runtime_settings, environ) -> ConversationExperienceCutoverSettings:
    enabled = _bool_env(
        environ,
        "JASON_CONVERSATION_EXPERIENCE_ENABLED",
        default=False,
    )

    # The short-lived generic variable remains a migration alias. When role-specific
    # variables are absent it applies to both roles; new deployments should use the
    # explicit Experience/Work variables so backend cost changes cannot silently alter
    # the conversational quality tier.
    legacy_models = _models_env(
        environ,
        "JASON_CONVERSATION_REASONING_MODELS",
    )
    experience_models = _models_env(
        environ,
        "JASON_CONVERSATION_EXPERIENCE_MODELS",
    ) or legacy_models
    work_models = _models_env(
        environ,
        "JASON_CONVERSATION_WORK_MODELS",
    ) or legacy_models

    timeout = _float_env(
        environ,
        "JASON_CONVERSATION_REASONING_TIMEOUT_SECONDS",
        default=90.0,
    )
    specialized_budget = _int_env(
        environ,
        "JASON_CONVERSATION_MAX_SPECIALIZED_READS_PER_NEED",
        default=8,
    )
    return ConversationExperienceCutoverSettings(
        enabled=enabled,
        context_db=runtime_settings.dynamic_conversation_context_db,
        context_ttl_seconds=runtime_settings.dynamic_conversation_context_ttl_seconds,
        experience_models=experience_models,
        work_models=work_models,
        reasoning_timeout_seconds=timeout,
        max_specialized_reads_per_need=specialized_budget,
    )



def _build_hosted_reasoning_clients(*, settings, runtime_settings, environ, governance):
    """Compose the optional hosted Conversation Kernel proposer.

    Credentials remain behind Jason's existing OpenBao boundary. The hosted
    reasoning client is injected only into the Conversation Kernel proposal stage
    and receives no connector handles or execution authority.

    Hosted execution-policy and data-egress governance are added in the
    constitutional hardening phase before production activation.
    """

    if not _bool_env(
        environ,
        "JASON_CONVERSATION_HOSTED_KERNEL_ENABLED",
        default=False,
    ):
        return None, None

    if governance is None:
        raise RuntimeError(
            "hosted Conversation Kernel requires canonical runtime governance services"
        )

    model = str(
        environ.get(
            "JASON_CONVERSATION_HOSTED_KERNEL_MODEL",
            runtime_settings.conversation_hosted_kernel_model,
        )
    ).strip()

    if not model:
        raise ValueError(
            "JASON_CONVERSATION_HOSTED_KERNEL_MODEL is required when hosted kernel is enabled"
        )

    resolver = OpenBaoSecretResolver(
        base_url=runtime_settings.openbao_url,
        role_id_path=runtime_settings.openai_openbao_role_id_path,
        secret_id_path=runtime_settings.openai_openbao_secret_id_path,
    )

    values = dict(
        resolver.resolve(
            "openai.semantic_intent",
            ConnectorContext(
                correlation_id="runtime-conversation-kernel-bootstrap",
                principal_id="jason-runtime",
                organization_id="aot",
                client_id=None,
                capability="conversation.intent.interpret",
                mode="observe",
            ),
        )
    )

    try:
        api_key = str(values["api_key"]).strip()

        if not api_key:
            raise ValueError(
                "OpenAI Conversation Kernel API key resolved empty"
            )

        raw_client = OpenAIStructuredJsonClient(
            api_key=api_key,
            transport=UrlLibJsonHttpTransport(),
            model=model,
            timeout_seconds=settings.reasoning_timeout_seconds,
            response_format_name="jason_conversation_kernel",
        )

        common = {
            "client": raw_client,
            "policy": governance.policy,
            "cost_estimator": governance.cost_estimator,
            "providers": governance.providers,
            "audit": governance.orchestration_events,
            "usage_ledger": governance.usage_ledger,
            "provider_id": OPENAI_CONVERSATION_PROVIDER_ID,
            "model_id": model,
            "classifier": HostedReasoningEgressClassifier(),
        }

        kernel = GovernedHostedReasoningClient(
            **common,
        )

        evidence = GovernedHostedReasoningClient(
            **common,
            capability=OPENAI_CONVERSATION_EVIDENCE_CAPABILITY,
            payload_projector=minimum_evidence_payload,
        )

        return kernel, evidence
    finally:
        values.clear()

def _models_env(environ, name: str) -> tuple[str, ...]:
    raw = str(environ.get(name, ""))
    if not raw.strip():
        return ()
    return tuple(item.strip() for item in raw.split(","))


def _bool_env(environ, name: str, *, default: bool) -> bool:
    raw = str(environ.get(name, "")).strip().casefold()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _int_env(environ, name: str, *, default: int) -> int:
    raw = str(environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _float_env(environ, name: str, *, default: float) -> float:
    raw = str(environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be numeric") from error
