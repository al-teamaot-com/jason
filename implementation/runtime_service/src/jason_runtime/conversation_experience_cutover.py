"""Runtime composition and rollback for Jason's first-class Conversation Experience.

The cutover changes only the conversational interpretation/fulfillment/response path.
Identity binding, authority evaluation, capability registry truth, Central Orchestrator,
provider resolution, connectors, approvals, audit, and Teams return transport remain the
same governed runtime objects.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from orchestrator.dynamic_conversation_intent import GroundedConversationIntentBuilder
from orchestrator.investigation_answer import InvestigationAnswerer
from orchestrator.investigation_decision import InvestigationDecisionEngine
from orchestrator.investigation_execution import GovernedInvestigationExecutor
from orchestrator.simple_reasoning_loop import SimpleReasoningLoop
from orchestrator.integration_documentation import (
    LiveIntegrationDocumentationReader,
)
from orchestrator.investigation_teams_flow import InvestigationTeamsConversationFlow
from orchestrator.investigation_turn_router import InvestigationTurnRouter
from pathlib import Path

from connectors.core.http_transport import UrlLibJsonHttpTransport
from orchestrator.conversation_answer import GroundedConversationAnswerer
from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER
from orchestrator.semantic_fact_reasoning import OllamaSemanticFactReasoner
from orchestrator.conversation_evidence_reasoning import (
    ValidatedConversationEvidenceReasoner,
)
from orchestrator.conversation_evidence_support import (
    ConversationEvidenceSupportExtractor,
)
from orchestrator.conversation_evidence_transform import (
    ValidatedConversationEvidenceTransformer,
)

from orchestrator.conversation_resource_intent import ReasonedResourceInquiryInterpreter
from orchestrator.grounded_semantic_resource_interpreter import GroundedSemanticResourceInquiryInterpreter
from orchestrator.ollama_reasoning import OllamaResourceInquiryReasoner
from orchestrator.conversation_experience import ConversationExperienceCoordinator
from orchestrator.conversation_interpretation_quality import ReviewedConversationKernel
from orchestrator.conversation_kernel import (
    ReasoningBackend,
    ValidatedReasoningPool,
)
from orchestrator.conversation_text_quality import ConversationTextQualityGate
from orchestrator.dynamic_conversation_context_store import (
    SQLiteDynamicConversationContextStore,
)
from orchestrator.dynamic_conversation_intent import (
    GroundedConversationIntentBuilder,
)
from orchestrator.evidence_gap_fulfillment import EvidenceGapFulfillmentPlanner
from orchestrator.information_fulfillment import (
    GovernedInitialFulfillmentPlanner,
    RegistryBackedFulfillmentCatalog,
)
from orchestrator.information_need_intent import InformationNeedIntentBuilder
from orchestrator.model_runtime_adapter import (
    ModelRuntimeAdapter,
    ollama_grammar_compatible_schema,
)
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
from orchestrator.progressive_conversation_read import ProgressiveConversationReadEngine
from orchestrator.deterministic_query_evidence import DeterministicOnlyEvidenceLocator
from orchestrator.governed_query import DeterministicGovernedQueryEngine
from orchestrator.governed_query_execution import GovernedQueryExecutionCoordinator
from orchestrator.query_evidence_materialization import GovernedQueryEvidenceMaterializer
from orchestrator.query_source_discovery import (
    GovernedQuerySourceDiscovery,
    RuntimeSemanticQueryUniverseBuilder,
)
from orchestrator.resource_evidence import GovernedResourceEvidenceInterpreter
from orchestrator.semantic_query_planning import UniversalSemanticQueryResolver
from orchestrator.universal_teams_query_flow import UniversalTeamsQueryFlow
from orchestrator.governed_schema_probe import GovernedSchemaProbe
from orchestrator.open_world_discovery import OpenWorldResourceDiscovery
from orchestrator.open_world_enrichment import OpenWorldCatalogEnricher
from orchestrator.open_world_evidence_materialization import OpenWorldEvidenceMaterializer
from orchestrator.open_world_execution import OpenWorldExecutionCoordinator
from orchestrator.open_world_query_planning import OpenWorldQueryPlanner
from orchestrator.open_world_semantic_mapping import OpenWorldSemanticMapper
from orchestrator.open_world_selector_grounding import OpenWorldGroundedSelectorResolver
from orchestrator.open_world_teams_query_flow import OpenWorldTeamsQueryFlow
from orchestrator.permissive_drmm_teams_flow import PermissiveDrmmTeamsFlow
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
    providers,
    ollama_url: str,
    default_ollama_model: str,
    identity_binder,
    request_factory,
    orchestrator,
    transport,
    http_transport: UrlLibJsonHttpTransport | None = None,
    structured_client=None,
    integration_broker=None,
    investigation_client=None,
):
    """Return the existing flow or a fully composed model-independent Teams experience.

    When disabled, the exact fallback flow is returned unchanged. This makes rollback a
    single runtime flag. When enabled, all provider work still crosses the supplied
    Central Orchestrator; this function does not create an alternate execution authority.
    """

    if not settings.enabled:
        return fallback_flow

    default_model = default_ollama_model.strip()
    transport_client = http_transport or UrlLibJsonHttpTransport()

    # Prefer the already-composed runtime reasoning client when no explicit role model
    # override is configured. This preserves the current provider choice (for example,
    # hosted OpenAI) without recomposing credentials, transports, pricing, or schema
    # adapters. Explicit role model lists remain an opt-in Ollama override.
    if settings.experience_models:
        if not ollama_url.strip():
            raise ValueError("Conversation Experience Ollama URL is required")

        experience_pool = _ollama_pool(
            models=settings.experience_models,
            transport=transport_client,
            ollama_url=ollama_url.strip(),
            timeout_seconds=settings.reasoning_timeout_seconds,
            role_prefix="experience",
        )

        if structured_client is not None:
            experience_pool = _combined_pool(
                work_pool=_structured_client_pool(
                    client=structured_client,
                    role_prefix="experience",
                ),
                experience_pool=experience_pool,
            )

    elif structured_client is not None:
        experience_pool = _structured_client_pool(
            client=structured_client,
            role_prefix="experience",
        )

    else:
        if not default_model:
            raise ValueError(
                "Conversation Experience requires a default reasoning model"
            )
        if not ollama_url.strip():
            raise ValueError("Conversation Experience Ollama URL is required")

        experience_pool = _ollama_pool(
            models=(default_model,),
            transport=transport_client,
            ollama_url=ollama_url.strip(),
            timeout_seconds=settings.reasoning_timeout_seconds,
            role_prefix="experience",
        )

    if settings.work_models:
        if not ollama_url.strip():
            raise ValueError("Conversation Experience Ollama URL is required")

        work_pool = _ollama_pool(
            models=settings.work_models,
            transport=transport_client,
            ollama_url=ollama_url.strip(),
            timeout_seconds=settings.reasoning_timeout_seconds,
            role_prefix="work",
        )

        if structured_client is not None:
            work_pool = _combined_pool(
                work_pool=_structured_client_pool(
                    client=structured_client,
                    role_prefix="work",
                ),
                experience_pool=work_pool,
            )

    elif structured_client is not None:
        work_pool = _structured_client_pool(
            client=structured_client,
            role_prefix="work",
        )

    else:
        if not default_model:
            raise ValueError(
                "Conversation Experience requires a default reasoning model"
            )
        if not ollama_url.strip():
            raise ValueError("Conversation Experience Ollama URL is required")

        work_pool = _ollama_pool(
            models=(default_model,),
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

    if os.getenv(
        "JASON_PERMISSIVE_DRMM_BASELINE_ENABLED",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}:
        baseline_reasoning = experience_pool.backends[0].client
        return PermissiveDrmmTeamsFlow(
            identity_binder=identity_binder,
            request_factory=request_factory,
            orchestrator=orchestrator,
            transport=transport,
            catalog=catalog,
            reasoning=baseline_reasoning,
            fallback_flow=fallback_flow,
        )
    intent_builder = InformationNeedIntentBuilder(reasoning=work_pool)
    primary_resources = tuple(
        item
        for item in catalog.list_available()
        if item.role == "primary"
        and item.permission_mode == "observe"
        and item.operation in {"search", "read"}
    )
    grounding_resource_types = tuple(
        sorted(
            {
                resource_type
                for item in primary_resources
                for resource_type in item.resource_types
            }
        )
    )
    grounding_selector_keys = tuple(
        sorted(
            {
                selector_key
                for item in primary_resources
                for selector_key in item.selector_keys
            }
        )
    )

    experience = ConversationExperienceCoordinator(
        kernel=ReviewedConversationKernel(
            proposing=experience_pool,
            reviewing=experience_pool,
            resource_kinds=lambda: _primary_resource_kinds(catalog),
        ),
        fulfillment=GovernedInitialFulfillmentPlanner(catalog=catalog),
        catalog=catalog,
        intent_builder=intent_builder,
        resource_interpreter=GroundedSemanticResourceInquiryInterpreter(
            contracts=_experience_resource_contracts(
                capabilities
            ),
            fallback=ReasonedResourceInquiryInterpreter(
                reasoner=OllamaResourceInquiryReasoner(
                    work_pool.backends[0].client,
                    resource_types=grounding_resource_types,
                    selector_keys=grounding_selector_keys,
                    fact_hints=(),
                ),
                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
                fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
            ),
            fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
            semantic_fact_reasoner=OllamaSemanticFactReasoner(
                work_pool.backends[0].client,
                fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
            ),
            fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
        ),
    )
    # A structurally valid evidence selection may still fail the independent
    # support review. Give the hosted selector one bounded second proposal so
    # deterministic review rejection can recover without introducing a local
    # reasoning fallback. Review itself remains single-attempt.
    evidence_selecting_pool = _retrying_pool(
        work_pool,
        max_attempts=2,
    )
    evidence_reviewing_pool = _retrying_pool(
        experience_pool,
        max_attempts=1,
    )

    evidence_reasoner = ValidatedConversationEvidenceReasoner(
        selecting=evidence_selecting_pool,
        reviewing=evidence_reviewing_pool,
    )

    evidence_transformer = ValidatedConversationEvidenceTransformer(
        planning=evidence_selecting_pool,
        reviewing=evidence_reviewing_pool,
    )

    progressive_reads = ProgressiveConversationReadEngine(
        evidence=ConversationEvidenceSupportExtractor(
            reasoner=evidence_reasoner,
            transformer=evidence_transformer,
        ),
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

    base_flow = TeamsConversationExperienceFlow(
        identity_binder=identity_binder,
        context_store=context_store,
        experience=experience,
        progressive_reads=progressive_reads,
        request_factory=request_factory,
        orchestrator=orchestrator,
        text_quality=text_quality,
        transport=transport,
    )

    investigation_enabled = os.getenv(
        "JASON_INVESTIGATION_LOOP_ENABLED",
        "false",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if investigation_enabled:
        if investigation_client is None:
            raise RuntimeError(
                "Investigation loop requires hosted OpenAI reasoning"
            )

        if integration_broker is None:
            raise RuntimeError(
                "Investigation loop requires Integration Broker"
            )

        investigation_loop = SimpleReasoningLoop(
            decisions=InvestigationDecisionEngine(
                client=investigation_client,
            ),
            execution=GovernedInvestigationExecutor(
                broker=integration_broker,
                grounding=GroundedConversationIntentBuilder(
                    client=investigation_client,
                ),
            ),
            documentation=LiveIntegrationDocumentationReader(
                broker=integration_broker,
            ),
            maximum_reads=int(
                os.getenv(
                    "JASON_INVESTIGATION_MAXIMUM_READS",
                    "4",
                )
            ),
        )

        return InvestigationTeamsConversationFlow(
            fallback=base_flow,
            investigation=investigation_loop,
            answerer=InvestigationAnswerer(
                client=investigation_client,
            ),
            router=InvestigationTurnRouter(
                client=investigation_client,
            ),
        )

    universal_enabled = os.getenv(
        "JASON_UNIVERSAL_QUERY_ENABLED",
        "false",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not universal_enabled:
        return base_flow

    runtime_providers = providers

    if runtime_providers is None:
        resolution_engine = getattr(
            orchestrator,
            "resolution",
            None,
        )

        runtime_providers = getattr(
            resolution_engine,
            "providers",
            None,
        )

    if runtime_providers is None:
        raise RuntimeError(
            "Universal query cutover requires "
            "runtime Execution Provider Registry access"
        )

    query_client = _universal_query_client(
        structured_client
    )

    universe_builder = RuntimeSemanticQueryUniverseBuilder(
        capabilities=capabilities,
        providers=runtime_providers,
    )

    discovery = GovernedQuerySourceDiscovery(
        capabilities=capabilities,
        providers=runtime_providers,
    )

    materializer = GovernedQueryEvidenceMaterializer(
        interpreter=GovernedResourceEvidenceInterpreter(
            reasoner=DeterministicOnlyEvidenceLocator(),
            fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
        )
    )

    # V8.12 replaces the closed-world universal information implementation.
    # The existing universal-query rollout flag remains the production rollout
    # authority, so no container/environment recreation is required.
    if (
        os.getenv(
            "JASON_OPEN_WORLD_QUERY_ENABLED",
            "",
        ).strip().casefold() == "true"
        or os.getenv(
            "JASON_UNIVERSAL_QUERY_ENABLED",
            "",
        ).strip().casefold() == "true"
    ):
        return OpenWorldTeamsQueryFlow(
            fallback=fallback_flow,
            context_store=context_store,
            discovery=OpenWorldResourceDiscovery(
                capabilities=capabilities,
                providers=runtime_providers,
            ),
            enricher=OpenWorldCatalogEnricher(
                probe=GovernedSchemaProbe(),
            ),
            classifier=OpenWorldSemanticMapper(
                client=query_client,
            ),
            selector_grounder=OpenWorldGroundedSelectorResolver(
                builder=GroundedConversationIntentBuilder(
                    client=query_client,
                ),
            ),
            planner=OpenWorldQueryPlanner(
                client=query_client,
            ),
            coordinator=OpenWorldExecutionCoordinator(
                materializer=OpenWorldEvidenceMaterializer(),
                query_engine=DeterministicGovernedQueryEngine(),
            ),
        )

    return UniversalTeamsQueryFlow(
        fallback=base_flow,
        resolver=UniversalSemanticQueryResolver(
            client=query_client
        ),
        universe_builder=universe_builder,
        coordinator=GovernedQueryExecutionCoordinator(
            discovery=discovery,
            intent_builder=intent_builder,
            materializer=materializer,
            query_engine=DeterministicGovernedQueryEngine(),
        ),
    )


def _universal_query_client(
    structured_client,
):
    """Clone the hosted OpenAI structured client onto the lowest-cost model."""

    if structured_client is None:
        raise RuntimeError(
            "Universal query planning requires "
            "the hosted OpenAI structured client"
        )

    from dataclasses import replace

    from orchestrator.model_runtime_adapter import (
        ModelRuntimeAdapter,
    )
    from orchestrator.openai_reasoning import (
        OpenAIStructuredJsonClient,
    )

    if isinstance(
        structured_client,
        ModelRuntimeAdapter,
    ):
        inner = structured_client.client

        if not isinstance(
            inner,
            OpenAIStructuredJsonClient,
        ):
            raise RuntimeError(
                "Universal query planning requires "
                "OpenAI structured reasoning"
            )

        return replace(
            structured_client,
            client=replace(
                inner,
                model="gpt-5-nano",
                response_format_name=(
                    "jason_universal_query"
                ),
            ),
        )

    if isinstance(
        structured_client,
        OpenAIStructuredJsonClient,
    ):
        return replace(
            structured_client,
            model="gpt-5-nano",
            response_format_name=(
                "jason_universal_query"
            ),
        )

    raise RuntimeError(
        "Universal query planning requires "
        "OpenAI structured reasoning"
    )


def _primary_resource_kinds(
    catalog: RegistryBackedFulfillmentCatalog,
) -> tuple[str, ...]:
    """Return runtime-declared structural targets without execution identifiers."""

    return tuple(
        sorted(
            {
                resource_type
                for capability in catalog.list_available()
                if capability.role == "primary"
                for resource_type in capability.resource_types
            }
        )
    )


def _structured_client_pool(
    *,
    client,
    role_prefix: str,
) -> ValidatedReasoningPool:
    """Reuse one already-composed structured runtime client for a reasoning role."""

    model = str(getattr(client, "model", "")).strip() or "current-runtime"
    return ValidatedReasoningPool(
        backends=(
            ReasoningBackend(
                name=f"{role_prefix}:{model}",
                client=client,
            ),
        )
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
                client=ModelRuntimeAdapter(
                    client=OllamaStructuredJsonClient(
                        transport=transport,
                        model=model,
                        base_url=ollama_url,
                        timeout_seconds=timeout_seconds,
                    ),
                    schema_adapter=ollama_grammar_compatible_schema,
                ),
            )
            for model in models
        )
    )



def _retrying_pool(
    pool: ValidatedReasoningPool,
    *,
    max_attempts: int,
) -> ValidatedReasoningPool:
    """Reuse the same configured semantic backends with bounded retries."""

    return ValidatedReasoningPool(
        backends=tuple(
            ReasoningBackend(
                name=backend.name,
                client=backend.client,
                max_attempts=max_attempts,
            )
            for backend in pool.backends
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


def _experience_resource_contracts(
    capabilities: CapabilityRegistryService,
) -> tuple[Mapping[str, Any], ...]:
    contracts: list[Mapping[str, Any]] = []
    for capability in capabilities.list_all():
        metadata = capability.metadata
        if metadata.get("provider_neutral", "false").lower() != "true":
            continue
        if metadata.get("read_only", "false").lower() != "true":
            continue
        resource_types = tuple(
            item.strip() for item in metadata.get("resource_types", "").split(",") if item.strip()
        )
        selector_keys = tuple(
            item.strip() for item in metadata.get("selector_keys", "").split(",") if item.strip()
        )
        fact_hints = tuple(
            item.strip()
            for item in metadata.get("inquiry_hints", metadata.get("fact_hints", "")).split(",")
            if item.strip()
        )
        collection_fact = metadata.get("collection_fact", "").strip()
        canonical_facts = tuple(
            item.strip() for item in metadata.get("canonical_facts", "").split(",") if item.strip()
        )
        declared_selector_required = str(
            metadata.get(
                "selector_required",
                "",
            )
        ).strip().casefold()

        if declared_selector_required in {
            "true",
            "false",
        }:
            selector_required = (
                declared_selector_required
                == "true"
            )
        else:
            selector_required = any(
                item in resource_types
                for item in (
                    "endpoint",
                    "endpoint_alert",
                    "endpoint_audit",
                    "endpoint_software",
                )
            )
        contracts.append(
            {
                "capability_name": capability.capability_name,
                "resource_types": resource_types,
                "selector_keys": selector_keys,
                "fact_hints": fact_hints,
                "canonical_facts": canonical_facts,
                "collection_fact": collection_fact,
                "selector_required": selector_required,
            }
        )
    return tuple(contracts)
