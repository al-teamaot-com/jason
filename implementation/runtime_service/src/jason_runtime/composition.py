from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from usage_ledger.ledger import SQLiteUsageLedger

from connectors.core.contracts import ConnectorContext
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.connector import DattoRmmConnector
from jason_cap_007.kernel_registration import register_email_send
from jason_cap_007.service import CAPABILITY_NAME as EMAIL_CAPABILITY_NAME
from jason_cap_007.service import EmailSendPolicy, GovernedEmailSendInvoker
from jason_cap_007.ses import AwsSesConfig, AwsSesTransport
from jason_openclaw.conversation_ingress import GovernedOpenClawTeamsConversationIngress
from jason_openclaw.key_registry import FileBackedTrustedKeyRegistry
from jason_openclaw.runtime import SQLiteReplayStore
from jason_openclaw.security_audit import SQLiteIngressSecurityAudit
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_policy import CostEstimator, ExecutionPolicyEngine, InMemoryPricingRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from kernel.identity_authority import (
    ExecutionContextValidator,
    IdentityAuthorityService,
    SQLiteApprovalRepository,
    SQLiteAuthorityGrantRepository,
    SQLiteIdentityAuthorityStore,
    SQLiteIdentityRepository,
)
from kernel.resolution import GovernedCapabilityResolutionEngine
from orchestrator.authority import JKD001OrchestrationContextEnforcer
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.conversation_action_intent import (
    ChainedConversationIntentResolver,
    GovernedActionConversationIntentResolver,
)
from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
from orchestrator.conversation_resource_intent import (
    GovernedResourceConversationIntentResolver,
    ReasonedResourceInquiryInterpreter,
)
from orchestrator.governed_semantic_coverage import GovernedSemanticCoverageIntentResolver
from orchestrator.grounded_semantic_resource_interpreter import (
    GroundedSemanticResourceInquiryInterpreter,
)
from orchestrator.conversation_response import GovernedTeamsConversationResponseRenderer
from orchestrator.event_store import SQLiteOrchestrationEventStore
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.ollama_action_reasoning import OllamaActionIntentReasoner
from orchestrator.openai_semantic_intent_translation import (
    OpenAISemanticIntentTranslator,
)
from orchestrator.openai_reasoning import OpenAIStructuredJsonClient
from orchestrator.ollama_semantic_intent_planning import OllamaSemanticIntentPlanningReasoner
from orchestrator.planning_context_reader import GovernedPlanningContextReaderAdapter
from orchestrator.planning_context_views import GovernedPlanningContextCatalog
from orchestrator.semantic_intent_planning_loop import (
    BoundedSemanticIntentPlanningLoop,
    IntentPlanningBudget,
)
from orchestrator.ollama_reasoning import (
    OllamaResourceEvidenceReasoner,
    OllamaResourceInquiryReasoner,
    OllamaStructuredJsonClient,
)
from orchestrator.resource_capability_catalog import (
    DATTO_RMM_PROVIDER,
    ENDPOINT_ALERT_SEARCH,
    ENDPOINT_ALERT_HISTORY_SEARCH,
    ENDPOINT_AUDIT_READ,
    ENDPOINT_DEVICE_READ,
    ENDPOINT_DEVICE_SEARCH,
    ENDPOINT_SOFTWARE_SEARCH,
    MANAGEMENT_ALERT_SEARCH,
    MANAGEMENT_SITE_SEARCH,
    register_endpoint_resource_foundation,
)
from orchestrator.resource_evidence import (
    GovernedResourceEvidenceInterpreter,
    GovernedTeamsResourceResponseRenderer,
)
from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner
from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER
from orchestrator.semantic_fact_reasoning import OllamaSemanticFactReasoner
from orchestrator.semantic_mapping_registry import JsonSemanticMappingRegistryLoader
from orchestrator.provider_read_authority import GovernedProviderReadAuthorityMatcher
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
from orchestrator.service import CentralOrchestrator
from orchestrator.system_registry_resource import (
    GovernedSystemRegistryCapabilityInvoker,
    SYSTEM_REGISTRY_READ,
    SYSTEM_REGISTRY_SEARCH,
    SYSTEM_REGISTRY_TRACE,
    load_production_system_registry,
    register_system_registry_resource_foundation,
)
from orchestrator.teams_conversation_continuation import (
    SQLiteTeamsConversationContinuationStore,
)
from orchestrator.teams_conversation_flow import TeamsConversationFlow
from orchestrator.teams_identity_binding import JasonTeamsIdentityBinder
from orchestrator.teams_identity_binding_sqlite import (
    AuthorityIdentityRecordReader,
    SQLiteMicrosoftIdentityBindingStore,
)
from orchestrator.teams_request_factory import GovernedTeamsOrchestrationRequestFactory

from .cap007 import Cap007EventAudit, Cap007OpenBaoSecretBroker
from .dynamic_conversation_cutover import (
    DynamicConversationCutoverSettings,
    select_teams_conversation_flow,
)
from .http import RuntimeHttpApplication
from .microsoft_directory import build_microsoft_directory_runtime
from .return_path import OpenClawReturnPathConversationIngress, OpenClawReturnPathTransport


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    authority_db: Path
    bindings_db: Path
    continuation_db: Path
    replay_db: Path
    security_audit_db: Path
    orchestration_events_db: Path
    trusted_keys_registry: Path
    openbao_url: str
    openbao_role_id_path: Path
    openbao_secret_id_path: Path
    ollama_url: str
    ollama_model: str
    allowed_machine_identities: frozenset[str]
    model_usage_db: Path = Path("/var/lib/jason/openclaw/model-usage.sqlite3")
    semantic_planner_enabled: bool = False
    hosted_semantics_enabled: bool = False
    hosted_conversation_enabled: bool = False
    openai_semantic_model: str = "gpt-5.4-mini"
    openai_conversation_model: str = "gpt-5.4-mini"
    openai_pricing_model: str = "gpt-5.4-mini"
    openai_input_cost_per_million_tokens: Decimal = Decimal("0.75")
    openai_cached_input_cost_per_million_tokens: Decimal = Decimal("0.075")
    openai_output_cost_per_million_tokens: Decimal = Decimal("4.50")
    openai_openbao_role_id_path: Path = Path(
        "/run/jason-secrets/openbao/openai/role_id"
    )
    openai_openbao_secret_id_path: Path = Path(
        "/run/jason-secrets/openbao/openai/secret_id"
    )
    microsoft_boundary_db: Path | None = None
    microsoft_openbao_role_id_path: Path = Path(
        "/run/jason-secrets/openbao/microsoft-graph/role_id"
    )
    microsoft_openbao_secret_id_path: Path = Path(
        "/run/jason-secrets/openbao/microsoft-graph/secret_id"
    )
    ses_openbao_role_id_path: Path = Path("/run/jason-secrets/openbao/aws-ses/role_id")
    ses_openbao_secret_id_path: Path = Path("/run/jason-secrets/openbao/aws-ses/secret_id")
    ses_region: str = "us-east-1"
    ses_default_sender: str = "jason@teamaot.com"
    dynamic_conversation_enabled: bool = False
    dynamic_conversation_context_db: Path = Path(
        "/var/lib/jason/openclaw/dynamic-conversation-context.sqlite3"
    )
    dynamic_conversation_context_ttl_seconds: int = 3600
    host: str = "0.0.0.0"
    port: int = 8080

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        allowed = frozenset(
            item.strip()
            for item in os.getenv(
                "JASON_ALLOWED_OPENCLAW_MACHINE_IDENTITIES",
                "svc-openclaw-gateway",
            ).split(",")
            if item.strip()
        )
        settings = cls(
            authority_db=Path(os.getenv("JASON_AUTHORITY_DB", "/var/lib/jason/authority/authority.sqlite3")),
            bindings_db=Path(
                os.getenv(
                    "JASON_TEAMS_IDENTITY_BINDINGS_DB",
                    "/var/lib/jason/openclaw/teams-identity-bindings.sqlite3",
                )
            ),
            continuation_db=Path(
                os.getenv(
                    "JASON_TEAMS_CONTINUATION_DB",
                    "/var/lib/jason/openclaw/teams-conversation-continuation.sqlite3",
                )
            ),
            replay_db=Path(os.getenv("JASON_REPLAY_DB", "/var/lib/jason/openclaw/replay.sqlite3")),
            security_audit_db=Path(
                os.getenv(
                    "JASON_SECURITY_AUDIT_DB",
                    "/var/lib/jason/openclaw/security-audit.sqlite3",
                )
            ),
            orchestration_events_db=Path(
                os.getenv(
                    "JASON_ORCHESTRATION_EVENTS_DB",
                    "/var/lib/jason/openclaw/orchestration-events.sqlite3",
                )
            ),
            model_usage_db=Path(
                os.getenv(
                    "JASON_MODEL_USAGE_DB",
                    "/var/lib/jason/openclaw/model-usage.sqlite3",
                )
            ),
            trusted_keys_registry=Path(
                os.getenv(
                    "JASON_TRUSTED_KEYS_REGISTRY",
                    "/var/lib/jason/openclaw/trusted-keys/registry.json",
                )
            ),
            openbao_url=os.getenv("JASON_OPENBAO_URL", "http://openbao:8200").strip(),
            openbao_role_id_path=Path(
                os.getenv("JASON_OPENBAO_ROLE_ID_PATH", "/run/jason-secrets/openbao/role_id")
            ),
            openbao_secret_id_path=Path(
                os.getenv("JASON_OPENBAO_SECRET_ID_PATH", "/run/jason-secrets/openbao/secret_id")
            ),
            ollama_url=os.getenv("JASON_OLLAMA_URL", "http://jason-ollama:11434").strip(),
            ollama_model=os.getenv("JASON_OLLAMA_MODEL", "").strip(),
            semantic_planner_enabled=os.getenv(
                "JASON_SEMANTIC_PLANNER_ENABLED", "false"
            ).strip().casefold() in {"1", "true", "yes", "on"},
            hosted_semantics_enabled=os.getenv(
                "JASON_HOSTED_SEMANTICS_ENABLED", "false"
            ).strip().casefold() in {"1", "true", "yes", "on"},
            hosted_conversation_enabled=os.getenv(
                "JASON_HOSTED_CONVERSATION_ENABLED", "false"
            ).strip().casefold() in {"1", "true", "yes", "on"},
            openai_semantic_model=os.getenv(
                "JASON_OPENAI_SEMANTIC_MODEL", "gpt-5.4-mini"
            ).strip(),
            openai_conversation_model=os.getenv(
                "JASON_OPENAI_CONVERSATION_MODEL", "gpt-5.4-mini"
            ).strip(),
            openai_pricing_model=os.getenv(
                "JASON_OPENAI_PRICING_MODEL", "gpt-5.4-mini"
            ).strip(),
            openai_input_cost_per_million_tokens=Decimal(
                os.getenv("JASON_OPENAI_INPUT_COST_PER_MILLION", "0.75")
            ),
            openai_cached_input_cost_per_million_tokens=Decimal(
                os.getenv("JASON_OPENAI_CACHED_INPUT_COST_PER_MILLION", "0.075")
            ),
            openai_output_cost_per_million_tokens=Decimal(
                os.getenv("JASON_OPENAI_OUTPUT_COST_PER_MILLION", "4.50")
            ),
            openai_openbao_role_id_path=Path(
                os.getenv(
                    "JASON_OPENAI_OPENBAO_ROLE_ID_PATH",
                    "/run/jason-secrets/openbao/openai/role_id",
                )
            ),
            openai_openbao_secret_id_path=Path(
                os.getenv(
                    "JASON_OPENAI_OPENBAO_SECRET_ID_PATH",
                    "/run/jason-secrets/openbao/openai/secret_id",
                )
            ),
            allowed_machine_identities=allowed,
            microsoft_boundary_db=Path(
                os.getenv(
                    "JASON_MICROSOFT_BOUNDARY_DB",
                    "/var/lib/jason/authority/client-boundaries.sqlite3",
                )
            ),
            microsoft_openbao_role_id_path=Path(
                os.getenv(
                    "JASON_MICROSOFT_OPENBAO_ROLE_ID_PATH",
                    "/run/jason-secrets/openbao/microsoft-graph/role_id",
                )
            ),
            microsoft_openbao_secret_id_path=Path(
                os.getenv(
                    "JASON_MICROSOFT_OPENBAO_SECRET_ID_PATH",
                    "/run/jason-secrets/openbao/microsoft-graph/secret_id",
                )
            ),
            ses_openbao_role_id_path=Path(
                os.getenv(
                    "JASON_SES_OPENBAO_ROLE_ID_PATH",
                    "/run/jason-secrets/openbao/aws-ses/role_id",
                )
            ),
            ses_openbao_secret_id_path=Path(
                os.getenv(
                    "JASON_SES_OPENBAO_SECRET_ID_PATH",
                    "/run/jason-secrets/openbao/aws-ses/secret_id",
                )
            ),
            ses_region=os.getenv("JASON_SES_REGION", "us-east-1").strip(),
            ses_default_sender=os.getenv(
                "JASON_SES_DEFAULT_SENDER", "jason@teamaot.com"
            ).strip(),
            dynamic_conversation_enabled=os.getenv(
                "JASON_DYNAMIC_CONVERSATION_ENABLED", "false"
            ).strip().casefold() in {"1", "true", "yes", "on"},
            dynamic_conversation_context_db=Path(
                os.getenv(
                    "JASON_DYNAMIC_CONVERSATION_CONTEXT_DB",
                    "/var/lib/jason/openclaw/dynamic-conversation-context.sqlite3",
                )
            ),
            dynamic_conversation_context_ttl_seconds=int(
                os.getenv("JASON_DYNAMIC_CONVERSATION_CONTEXT_TTL_SECONDS", "3600")
            ),
            host=os.getenv("JASON_RUNTIME_HOST", "0.0.0.0").strip(),
            port=int(os.getenv("JASON_RUNTIME_PORT", "8080")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.ollama_model:
            raise ValueError("JASON_OLLAMA_MODEL is required")
        if self.hosted_semantics_enabled and not self.openai_semantic_model:
            raise ValueError(
                "JASON_OPENAI_SEMANTIC_MODEL is required when hosted semantics are enabled"
            )
        if self.hosted_conversation_enabled and not self.openai_conversation_model:
            raise ValueError(
                "JASON_OPENAI_CONVERSATION_MODEL is required when hosted conversation is enabled"
            )
        if self.hosted_conversation_enabled and not self.dynamic_conversation_enabled:
            raise ValueError(
                "hosted conversation requires JASON_DYNAMIC_CONVERSATION_ENABLED=true"
            )
        hosted_models = {
            model
            for enabled, model in (
                (self.hosted_semantics_enabled, self.openai_semantic_model),
                (self.hosted_conversation_enabled, self.openai_conversation_model),
            )
            if enabled
        }
        if hosted_models and hosted_models != {self.openai_pricing_model}:
            raise ValueError(
                "OpenAI pricing model must match every enabled hosted model"
            )
        if any(
            value < 0
            for value in (
                self.openai_input_cost_per_million_tokens,
                self.openai_cached_input_cost_per_million_tokens,
                self.openai_output_cost_per_million_tokens,
            )
        ):
            raise ValueError("OpenAI token pricing values must be non-negative")
        if not self.openbao_url or not self.ollama_url:
            raise ValueError("runtime provider service URLs must be non-empty")
        if not self.allowed_machine_identities:
            raise ValueError("at least one allowed OpenClaw machine identity is required")
        if not self.ses_region:
            raise ValueError("JASON_SES_REGION is required")
        if not self.ses_default_sender:
            raise ValueError("JASON_SES_DEFAULT_SENDER is required")
        if self.dynamic_conversation_context_ttl_seconds < 60 or self.dynamic_conversation_context_ttl_seconds > 86400:
            raise ValueError(
                "dynamic conversation context ttl must be between 60 and 86400 seconds"
            )
        if not str(self.dynamic_conversation_context_db).strip():
            raise ValueError("dynamic conversation context db path is required")
        if not self.host:
            raise ValueError("runtime host is required")
        if not (0 < self.port < 65536):
            raise ValueError("runtime port is invalid")


def build_disabled_semantic_intent_planner(
    *,
    settings: RuntimeSettings,
    client: OllamaStructuredJsonClient,
    context_catalog: GovernedPlanningContextCatalog,
) -> BoundedSemanticIntentPlanningLoop | None:
    """Compose the semantic planner only when explicitly enabled."""
    if not settings.semantic_planner_enabled:
        return None
    reasoner = OllamaSemanticIntentPlanningReasoner(client=client)
    reader = GovernedPlanningContextReaderAdapter(catalog=context_catalog)
    return BoundedSemanticIntentPlanningLoop(
        reasoner=reasoner,
        context_reader=reader,
        budget=IntentPlanningBudget(max_iterations=6, max_context_requests=6),
    )


@dataclass(frozen=True, slots=True)
class ConnectorEventAudit:
    events: SQLiteOrchestrationEventStore

    def record(self, event_type: str, context: ConnectorContext, details: Mapping[str, Any]) -> None:
        stage = "invoking" if event_type.endswith("requested") else "completed"
        self.events.append(
            event_type,
            {
                "execution_id": f"connector:{context.correlation_id}",
                "correlation_id": context.correlation_id,
                "organization_id": context.organization_id,
                "principal_id": context.principal_id,
                "capability_name": context.capability,
                "stage": stage,
                "client_id": context.client_id,
                "permission_mode": context.mode,
                "details": dict(details),
            },
        )


def _resource_language_contract(
    capabilities: CapabilityRegistryService,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    resource_types: set[str] = set()
    selector_keys: set[str] = set()
    fact_hints: set[str] = set()
    for capability in capabilities.list_all():
        metadata = capability.metadata
        if metadata.get("provider_neutral", "false").lower() != "true":
            continue
        if metadata.get("read_only", "false").lower() != "true":
            continue
        resource_types.update(
            item.strip() for item in metadata.get("resource_types", "").split(",") if item.strip()
        )
        selector_keys.update(
            item.strip() for item in metadata.get("selector_keys", "").split(",") if item.strip()
        )
        fact_hints.update(
            item.strip() for item in metadata.get("fact_hints", "").split(",") if item.strip()
        )
    return tuple(sorted(resource_types)), tuple(sorted(selector_keys)), tuple(sorted(fact_hints))


def _deterministic_resource_contracts(
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
        selector_required = any(
            item in resource_types
            for item in ("endpoint", "endpoint_alert", "endpoint_audit", "endpoint_software")
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


def build_runtime_application(settings: RuntimeSettings) -> RuntimeHttpApplication:
    settings.validate()

    authority_store = SQLiteIdentityAuthorityStore(settings.authority_db)
    approval_repository = SQLiteApprovalRepository(authority_store)
    context_validator = ExecutionContextValidator(contexts=authority_store)
    http_transport = UrlLibJsonHttpTransport()

    microsoft_boundary_db = settings.microsoft_boundary_db or settings.authority_db.with_name(
        "client-boundaries.sqlite3"
    )
    microsoft_directory = build_microsoft_directory_runtime(
        boundary_db=microsoft_boundary_db,
        openbao_url=settings.openbao_url,
        role_id_path=settings.microsoft_openbao_role_id_path,
        secret_id_path=settings.microsoft_openbao_secret_id_path,
        transport=http_transport,
    )

    bindings = SQLiteMicrosoftIdentityBindingStore(settings.bindings_db)
    identity_binder = JasonTeamsIdentityBinder(
        bindings=bindings,
        identities=AuthorityIdentityRecordReader(authority_store),
        directory=microsoft_directory.directory,
    )

    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    now = datetime.now(timezone.utc)
    register_endpoint_resource_foundation(capabilities=capabilities, providers=providers, now=now)
    register_system_registry_resource_foundation(capabilities=capabilities, providers=providers, now=now)
    register_email_send(capabilities=capabilities, providers=providers)

    identity_authority = IdentityAuthorityService(
        identities=SQLiteIdentityRepository(authority_store),
        grants=SQLiteAuthorityGrantRepository(authority_store),
        approvals=approval_repository,
        contexts=authority_store,
        audit=authority_store,
        capability_matcher=GovernedProviderReadAuthorityMatcher(
            capabilities=capabilities, providers=providers
        ),
    )

    ollama_client = OllamaStructuredJsonClient(
        transport=http_transport,
        model=settings.ollama_model,
        base_url=settings.ollama_url,
    )

    model_usage_ledger = None
    openai_api_key = None
    if settings.hosted_semantics_enabled or settings.hosted_conversation_enabled:
        model_usage_ledger = SQLiteUsageLedger(settings.model_usage_db)
        semantic_secret_resolver = OpenBaoSecretResolver(
            base_url=settings.openbao_url,
            role_id_path=settings.openai_openbao_role_id_path,
            secret_id_path=settings.openai_openbao_secret_id_path,
        )
        semantic_secret_values = dict(
            semantic_secret_resolver.resolve(
                "openai.semantic_intent",
                ConnectorContext(
                    correlation_id="runtime-openai-bootstrap",
                    principal_id="jason-runtime",
                    organization_id="aot",
                    client_id=None,
                    capability="conversation.reason",
                    mode="observe",
                ),
            )
        )
        try:
            openai_api_key = str(semantic_secret_values["api_key"]).strip()
            if not openai_api_key:
                raise ValueError("OpenAI API key resolved empty")
        finally:
            semantic_secret_values.clear()

    hosted_conversation_client = None
    if settings.hosted_conversation_enabled:
        if openai_api_key is None or model_usage_ledger is None:
            raise RuntimeError("hosted conversation dependencies were not composed")
        hosted_conversation_client = OpenAIStructuredJsonClient(
            api_key=openai_api_key,
            transport=http_transport,
            model=settings.openai_conversation_model,
            usage_ledger=model_usage_ledger,
            input_cost_per_million_tokens=settings.openai_input_cost_per_million_tokens,
            cached_input_cost_per_million_tokens=settings.openai_cached_input_cost_per_million_tokens,
            output_cost_per_million_tokens=settings.openai_output_cost_per_million_tokens,
        )

    intent_resolver = None
    if not settings.dynamic_conversation_enabled:
        semantic_mapping_path = (
            Path(__file__).resolve().parents[4]
            / "config"
            / "semantic_mappings"
            / "approved.json"
        )
        semantic_mapping_registry = JsonSemanticMappingRegistryLoader(semantic_mapping_path).load()

        resource_types, selector_keys, fact_hints = _resource_language_contract(capabilities)
        action_intent_resolver = GovernedActionConversationIntentResolver(
            registry=capabilities,
            reasoner=OllamaActionIntentReasoner(ollama_client),
        )

        hosted_semantic_translator = None
        if settings.hosted_semantics_enabled:
            if openai_api_key is None or model_usage_ledger is None:
                raise RuntimeError("hosted semantic dependencies were not composed")
            hosted_semantic_translator = OpenAISemanticIntentTranslator(
                api_key=openai_api_key,
                transport=http_transport,
                model=settings.openai_semantic_model,
                usage_ledger=model_usage_ledger,
                input_cost_per_million_tokens=settings.openai_input_cost_per_million_tokens,
                cached_input_cost_per_million_tokens=settings.openai_cached_input_cost_per_million_tokens,
                output_cost_per_million_tokens=settings.openai_output_cost_per_million_tokens,
            )

        resource_intent_resolver = GovernedResourceConversationIntentResolver(
            interpreter=GroundedSemanticResourceInquiryInterpreter(
                contracts=_deterministic_resource_contracts(capabilities),
                fallback=ReasonedResourceInquiryInterpreter(
                    reasoner=OllamaResourceInquiryReasoner(
                        ollama_client,
                        resource_types=resource_types,
                        selector_keys=selector_keys,
                        fact_hints=fact_hints,
                    ),
                    fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
                    fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
                ),
                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
                semantic_intent_translator=hosted_semantic_translator,
                semantic_fact_reasoner=OllamaSemanticFactReasoner(
                    ollama_client,
                    fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
                ),
                fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
            ),
            planner=GovernedResourceInquiryPlanner(
                registry=capabilities,
                reasoner=MetadataResourceCapabilityReasoner(
                    semantic_mapping_registry=semantic_mapping_registry,
                ),
                semantic_mapping_registry=semantic_mapping_registry,
            ),
        )
        governed_resource_intent_resolver = GovernedSemanticCoverageIntentResolver(
            delegate=resource_intent_resolver,
            capabilities=capabilities,
            fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
            semantic_mapping_registry=semantic_mapping_registry,
        )
        intent_resolver = ChainedConversationIntentResolver(
            resolvers=(governed_resource_intent_resolver, action_intent_resolver)
        )

    orchestration_events = SQLiteOrchestrationEventStore(settings.orchestration_events_db)
    openbao = OpenBaoSecretResolver(
        base_url=settings.openbao_url,
        role_id_path=settings.openbao_role_id_path,
        secret_id_path=settings.openbao_secret_id_path,
    )
    datto = DattoRmmConnector(
        secrets=openbao,
        transport=http_transport,
        audit=ConnectorEventAudit(orchestration_events),
    )
    datto_invoker = GovernedConnectorCapabilityInvoker(
        connectors={DATTO_RMM_PROVIDER: datto},
        provider_capability_map={
            (DATTO_RMM_PROVIDER, ENDPOINT_DEVICE_SEARCH): "datto_rmm.device.search",
            (DATTO_RMM_PROVIDER, ENDPOINT_DEVICE_READ): "datto_rmm.device.get",
            (DATTO_RMM_PROVIDER, ENDPOINT_ALERT_SEARCH): "datto_rmm.device.alerts.open",
            (DATTO_RMM_PROVIDER, ENDPOINT_ALERT_HISTORY_SEARCH): "datto_rmm.device.alerts.resolved",
            (DATTO_RMM_PROVIDER, ENDPOINT_AUDIT_READ): "datto_rmm.device.audit.get",
            (DATTO_RMM_PROVIDER, ENDPOINT_SOFTWARE_SEARCH): "datto_rmm.device.software.list",
            (DATTO_RMM_PROVIDER, MANAGEMENT_ALERT_SEARCH): "datto_rmm.account.alerts.open",
            (DATTO_RMM_PROVIDER, MANAGEMENT_SITE_SEARCH): "datto_rmm.site.search",
        },
    )
    system_registry_invoker = GovernedSystemRegistryCapabilityInvoker(
        registry=load_production_system_registry()
    )

    email_secret_broker = Cap007OpenBaoSecretBroker.build(
        base_url=settings.openbao_url,
        role_id_path=settings.ses_openbao_role_id_path,
        secret_id_path=settings.ses_openbao_secret_id_path,
    )
    email_invoker = GovernedEmailSendInvoker(
        secrets=email_secret_broker,
        transport=AwsSesTransport(config=AwsSesConfig(region_name=settings.ses_region)),
        policy=EmailSendPolicy(
            default_sender=settings.ses_default_sender,
            allowed_senders=(settings.ses_default_sender,),
            allow_bcc=False,
            max_recipients=25,
        ),
        audit=Cap007EventAudit(orchestration_events),
    )

    invokers = CapabilityInvokerRegistry()
    invokers.register(ENDPOINT_DEVICE_SEARCH, datto_invoker)
    invokers.register(ENDPOINT_DEVICE_READ, datto_invoker)
    invokers.register(ENDPOINT_ALERT_SEARCH, datto_invoker)
    invokers.register(ENDPOINT_ALERT_HISTORY_SEARCH, datto_invoker)
    invokers.register(ENDPOINT_AUDIT_READ, datto_invoker)
    invokers.register(ENDPOINT_SOFTWARE_SEARCH, datto_invoker)
    invokers.register(MANAGEMENT_ALERT_SEARCH, datto_invoker)
    invokers.register(MANAGEMENT_SITE_SEARCH, datto_invoker)
    invokers.register(SYSTEM_REGISTRY_SEARCH, system_registry_invoker)
    invokers.register(SYSTEM_REGISTRY_READ, system_registry_invoker)
    invokers.register(SYSTEM_REGISTRY_TRACE, system_registry_invoker)
    invokers.register(EMAIL_CAPABILITY_NAME, email_invoker)

    policy = ExecutionPolicyEngine(cost_estimator=CostEstimator(InMemoryPricingRegistry()))
    resolution = GovernedCapabilityResolutionEngine(
        capabilities=capabilities,
        providers=providers,
        policy=policy,
    )
    orchestrator = CentralOrchestrator(
        resolution=resolution,
        invoker=invokers,
        audit=orchestration_events,
        authority_context=JKD001OrchestrationContextEnforcer(context_validator),
        require_authority_context=True,
    )

    resource_response_renderer = GovernedTeamsResourceResponseRenderer(
        interpreter=GovernedResourceEvidenceInterpreter(
            reasoner=OllamaResourceEvidenceReasoner(
                ollama_client,
                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
            ),
            fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
        )
    )
    response_renderer = GovernedTeamsConversationResponseRenderer(
        resource_renderer=resource_response_renderer
    )
    return_transport = OpenClawReturnPathTransport()
    continuation_store = SQLiteTeamsConversationContinuationStore(
        settings.continuation_db,
        ttl_seconds=1200,
    )
    request_factory = GovernedTeamsOrchestrationRequestFactory(
        authority=identity_authority,
        capabilities=capabilities,
        approvals=approval_repository,
    )

    legacy_flow = None
    if not settings.dynamic_conversation_enabled:
        if intent_resolver is None:
            raise RuntimeError("legacy conversation resolver was not composed")
        legacy_flow = TeamsConversationFlow(
            identity_binder=identity_binder,
            intent_resolver=intent_resolver,
            request_factory=request_factory,
            orchestrator=orchestrator,
            response_renderer=response_renderer,
            transport=return_transport,
            continuation_store=continuation_store,
        )

    flow = select_teams_conversation_flow(
        settings=DynamicConversationCutoverSettings(
            enabled=settings.dynamic_conversation_enabled,
            context_db=settings.dynamic_conversation_context_db,
            context_ttl_seconds=settings.dynamic_conversation_context_ttl_seconds,
        ),
        legacy_flow=legacy_flow,
        capabilities=capabilities,
        structured_client=hosted_conversation_client or ollama_client,
        identity_binder=identity_binder,
        request_factory=request_factory,
        orchestrator=orchestrator,
        response_renderer=response_renderer,
        transport=return_transport,
        continuation_store=continuation_store,
    )

    trusted_keys = FileBackedTrustedKeyRegistry(settings.trusted_keys_registry)
    governed_ingress = GovernedOpenClawTeamsConversationIngress(
        authenticator=trusted_keys.build_authenticator(),
        replay=SQLiteReplayStore(settings.replay_db),
        audit=SQLiteIngressSecurityAudit(settings.security_audit_db),
        flow=flow,
        allowed_machine_identities=settings.allowed_machine_identities,
    )
    return RuntimeHttpApplication(
        ingress=OpenClawReturnPathConversationIngress(
            ingress=governed_ingress,
            transport=return_transport,
        )
    )
