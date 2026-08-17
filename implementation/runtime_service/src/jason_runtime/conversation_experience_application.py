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
    raw_models = str(environ.get("JASON_CONVERSATION_REASONING_MODELS", ""))
    models = tuple(
        dict.fromkeys(
            item.strip()
            for item in raw_models.split(",")
            if item.strip()
        )
    )
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
        reasoning_models=models,
        reasoning_timeout_seconds=timeout,
        max_specialized_reads_per_need=specialized_budget,
    )


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
