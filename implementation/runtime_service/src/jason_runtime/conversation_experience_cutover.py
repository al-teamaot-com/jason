"""Runtime composition and rollback for Jason's first-class Conversation Experience.

The cutover changes only the conversational interpretation/fulfillment/response path.
Identity binding, authority evaluation, capability registry truth, Central Orchestrator,
provider resolution, connectors, approvals, audit, and Teams return transport remain the
same governed runtime objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from connectors.core.http_transport import UrlLibJsonHttpTransport
from orchestrator.conversation_answer import GroundedConversationAnswerer
from orchestrator.conversation_evidence_reasoning import (
    ValidatedConversationEvidenceReasoner,
)
from orchestrator.conversation_evidence_support import (
    ConversationEvidenceSupportExtractor,
)
from orchestrator.conversation_experience import ConversationExperienceCoordinator
from orchestrator.conversation_kernel import (
    ConversationKernel,
    ReasoningBackend,
    ValidatedReasoningPool,
)
from orchestrator.conversation_text_quality import ConversationTextQualityGate
from orchestrator.dynamic_conversation_context_store import (
    SQLiteDynamicConversationContextStore,
)
from orchestrator.evidence_gap_fulfillment import EvidenceGapFulfillmentPlanner
from orchestrator.information_fulfillment import (
    GovernedInitialFulfillmentPlanner,
    RegistryBackedFulfillmentCatalog,
)
from orchestrator.information_need_intent import InformationNeedIntentBuilder
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
from orchestrator.progressive_conversation_read import ProgressiveConversationReadEngine
from orchestrator.teams_conversation_experience import TeamsConversationExperienceFlow


@dataclass(frozen=True, slots=True)
class ConversationExperienceCutoverSettings:
    """Runtime-owned rollout, model-role, cost, and latency controls.

    ``experience_models`` protect the human interaction: interpretation, quality review,
    and final wording. ``work_models`` perform cheaper backend search/selection work.
    Changing backend work models therefore does not require changing the model tier used
    to preserve the Teams experience. Either role may still use a list ordered from lower
    cost to stronger fallback.
    """

    enabled: bool = False
    context_db: Path = Path(
        "/var/lib/jason/openclaw/dynamic-conversation-context.sqlite3"
    )
    context_ttl_seconds: int = 3600
    experience_models: tuple[str, ...] = ()
    work_models: tuple[str, ...] = ()
    reasoning_timeout_seconds: float = 90.0
    max_specialized_reads_per_need: int = 8

    def __post_init__(self) -> None:
        if self.context_ttl_seconds < 60 or self.context_ttl_seconds > 86400:
            raise ValueError(
                "Conversation Experience context ttl must be between 60 and 86400 seconds"
            )
        _validate_models("experience", self.experience_models)
        _validate_models("work", self.work_models)
        if self.reasoning_timeout_seconds < 15 or self.reasoning_timeout_seconds > 300:
            raise ValueError(
                "Conversation Experience reasoning timeout must be between 15 and 300 seconds"
            )
        if self.max_specialized_reads_per_need < 0 or self.max_specialized_reads_per_need > 32:
            raise ValueError(
                "Conversation Experience specialized read budget must be between 0 and 32"
            )


def select_conversation_experience_flow(
    *,
    settings: ConversationExperienceCutoverSettings,
    fallback_flow,
    capabilities,
    ollama_url: str,
    default_ollama_model: str,
    identity_binder,
    request_factory,
    orchestrator,
    transport,
    http_transport: UrlLibJsonHttpTransport | None = None,
):
    """Return the existing flow or a fully composed model-independent Teams experience.

    When disabled, the exact fallback flow is returned unchanged. This makes rollback a
    single runtime flag. When enabled, all provider work still crosses the supplied
    Central Orchestrator; this function does not create an alternate execution authority.
    """

    if not settings.enabled:
        return fallback_flow

    default_model = default_ollama_model.strip()
    if not default_model:
        raise ValueError("Conversation Experience requires a default reasoning model")
    if not ollama_url.strip():
        raise ValueError("Conversation Experience Ollama URL is required")

    experience_models = settings.experience_models or (default_model,)
    work_models = settings.work_models or (default_model,)
    transport_client = http_transport or UrlLibJsonHttpTransport()

    experience_pool = _ollama_pool(
        models=experience_models,
        transport=transport_client,
        ollama_url=ollama_url.strip(),
        timeout_seconds=settings.reasoning_timeout_seconds,
        role_prefix="experience",
    )
    work_pool = _ollama_pool(
        models=work_models,
        transport=transport_client,
        ollama_url=ollama_url.strip(),
        timeout_seconds=settings.reasoning_timeout_seconds,
        role_prefix="work",
    )
    drafting_pool = _combined_pool(
        work_pool=work_pool,
        experience_pool=experience_pool,
    )

    context_store = SQLiteDynamicConversationContextStore(
        settings.context_db,
        ttl_seconds=settings.context_ttl_seconds,
    )
    catalog = RegistryBackedFulfillmentCatalog(registry=capabilities)
    intent_builder = InformationNeedIntentBuilder(reasoning=work_pool)
    experience = ConversationExperienceCoordinator(
        kernel=ConversationKernel(reasoning=experience_pool),
        fulfillment=GovernedInitialFulfillmentPlanner(catalog=catalog),
        catalog=catalog,
        intent_builder=intent_builder,
    )
    evidence_reasoner = ValidatedConversationEvidenceReasoner(
        selecting=work_pool,
        reviewing=experience_pool,
    )
    progressive_reads = ProgressiveConversationReadEngine(
        evidence=ConversationEvidenceSupportExtractor(reasoner=evidence_reasoner),
        gaps=EvidenceGapFulfillmentPlanner(
            catalog=catalog,
            reasoning=work_pool,
        ),
        catalog=catalog,
        intent_builder=intent_builder,
        answerer=GroundedConversationAnswerer(
            drafting=drafting_pool,
            reviewing=experience_pool,
        ),
        max_specialized_reads_per_need=settings.max_specialized_reads_per_need,
    )
    text_quality = ConversationTextQualityGate(
        rewriting=drafting_pool,
        reviewing=experience_pool,
    )

    return TeamsConversationExperienceFlow(
        identity_binder=identity_binder,
        context_store=context_store,
        experience=experience,
        progressive_reads=progressive_reads,
        request_factory=request_factory,
        orchestrator=orchestrator,
        text_quality=text_quality,
        transport=transport,
    )


def _ollama_pool(
    *,
    models: tuple[str, ...],
    transport: UrlLibJsonHttpTransport,
    ollama_url: str,
    timeout_seconds: float,
    role_prefix: str,
) -> ValidatedReasoningPool:
    return ValidatedReasoningPool(
        backends=tuple(
            ReasoningBackend(
                name=f"{role_prefix}:{model}",
                client=OllamaStructuredJsonClient(
                    transport=transport,
                    model=model,
                    base_url=ollama_url,
                    timeout_seconds=timeout_seconds,
                ),
            )
            for model in models
        )
    )


def _combined_pool(
    *,
    work_pool: ValidatedReasoningPool,
    experience_pool: ValidatedReasoningPool,
) -> ValidatedReasoningPool:
    backends: list[ReasoningBackend] = []
    seen_clients: set[tuple[str, str]] = set()
    for backend in (*work_pool.backends, *experience_pool.backends):
        model = str(getattr(backend.client, "model", "")).strip()
        base_url = str(getattr(backend.client, "base_url", "")).strip()
        key = (base_url, model)
        if key in seen_clients:
            continue
        seen_clients.add(key)
        backends.append(backend)
    return ValidatedReasoningPool(backends=tuple(backends))


def _validate_models(role: str, models: tuple[str, ...]) -> None:
    cleaned = tuple(model.strip() for model in models if model.strip())
    if cleaned != models:
        raise ValueError(
            f"Conversation Experience {role} models must be non-empty normalized names"
        )
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(
            f"Conversation Experience {role} models must be unique"
        )
