from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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
    MetadataFirstResourceInquiryInterpreter,
    ReasonedResourceInquiryInterpreter,
)
from orchestrator.conversation_response import GovernedTeamsConversationResponseRenderer
from orchestrator.event_store import SQLiteOrchestrationEventStore
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.ollama_action_reasoning import OllamaActionIntentReasoner
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
from orchestrator.semantic_mapping_registry import (
    JsonSemanticMappingRegistryLoader,
)
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
from orchestrator.teams_conversation_flow import TeamsConversationFlow
from orchestrator.teams_identity_binding import JasonTeamsIdentityBinder
from orchestrator.teams_identity_binding_sqlite import (
    AuthorityIdentityRecordReader,
    SQLiteMicrosoftIdentityBindingStore,
)
from orchestrator.teams_request_factory import GovernedTeamsOrchestrationRequestFactory

from .cap007 import Cap007EventAudit, Cap007OpenBaoSecretBroker
from .http import RuntimeHttpApplication
from .microsoft_directory import build_microsoft_directory_runtime
from .return_path import OpenClawReturnPathConversationIngress, OpenClawReturnPathTransport


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    authority_db: Path
    bindings_db: Path
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
    semantic_planner_enabled: bool = False
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
            host=os.getenv("JASON_RUNTIME_HOST", "0.0.0.0").strip(),
            port=int(os.getenv("JASON_RUNTIME_PORT", "8080")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.ollama_model:
            raise ValueError("JASON_OLLAMA_MODEL is required")
        if not self.openbao_url or not self.ollama_url:
            raise ValueError("runtime provider service URLs must be non-empty")
        if not self.allowed_machine_identities:
            raise ValueError("at least one allowed OpenClaw machine identity is required")
        if not self.ses_region:
            raise ValueError("JASON_SES_REGION is required")
        if not self.ses_default_sender:
            raise ValueError("JASON_SES_DEFAULT_SENDER is required")
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
    """Compose the semantic planner only when explicitly enabled.

    This helper intentionally performs no execution wiring. The returned planner can
    reason only over governed context snapshots and can only propose provider-neutral
    capability plans.
    """
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
    """Record provider boundary events without credential or response-body logging."""

    events: SQLiteOrchestrationEventStore

    def record(
        self,
        event_type: str,
        context: ConnectorContext,
        details: Mapping[str, Any],
    ) -> None:
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
    """Derive language-normalization vocabulary from governed capability metadata."""

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
            item.strip()
            for item in metadata.get("resource_types", "").split(",")
            if item.strip()
        )
        selector_keys.update(
            item.strip()
            for item in metadata.get("selector_keys", "").split(",")
            if item.strip()
        )
        fact_hints.update(
            item.strip()
            for item in metadata.get("fact_hints", "").split(",")
            if item.strip()
        )
    return (
        tuple(sorted(resource_types)),
        tuple(sorted(selector_keys)),
        tuple(sorted(fact_hints)),
    )



def _deterministic_resource_contracts(
    capabilities: CapabilityRegistryService,
) -> tuple[Mapping[str, Any], ...]:
    """Build deterministic read-language contracts from governed metadata."""

    contracts: list[Mapping[str, Any]] = []

    for capability in capabilities.list_all():
        metadata = capability.metadata

        if metadata.get("provider_neutral", "false").lower() != "true":
            continue
        if metadata.get("read_only", "false").lower() != "true":
            continue

        resource_types = tuple(
            item.strip()
            for item in metadata.get("resource_types", "").split(",")
            if item.strip()
        )
        selector_keys = tuple(
            item.strip()
            for item in metadata.get("selector_keys", "").split(",")
            if item.strip()
        )
        fact_hints = tuple(
            item.strip()
            for item in metadata.get(
                "inquiry_hints",
                metadata.get("fact_hints", ""),
            ).split(",")
            if item.strip()
        )
        collection_fact = metadata.get("collection_fact", "").strip()

        # A zero-selector interpretation is safe only for resource contracts
        # that have a meaningful account/environment-wide read surface.
        #
        # Current metadata convention:
        # management-wide search resources can be queried without a selector;
        # endpoint/device-scoped resources require discovery/identity grounding.
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
                "collection_fact": collection_fact,
                "selector_required": selector_required,
            }
        )

    return tuple(contracts)


def build_runtime_application(settings: RuntimeSettings) -> RuntimeHttpApplication:
    """Compose the production conversational runtime from governed Jason primitives."""

    settings.validate()

    authority_store = SQLiteIdentityAuthorityStore(settings.authority_db)
    approval_repository = SQLiteApprovalRepository(authority_store)
    context_validator = ExecutionContextValidator(contexts=authority_store)

    http_transport = UrlLibJsonHttpTransport()

    microsoft_boundary_db = (
        settings.microsoft_boundary_db
        or settings.authority_db.with_name("client-boundaries.sqlite3")
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
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=now,
    )
    register_system_registry_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=now,
    )
    register_email_send(capabilities=capabilities, providers=providers)

    identity_authority = IdentityAuthorityService(
        identities=SQLiteIdentityRepository(authority_store),
        grants=SQLiteAuthorityGrantRepository(authority_store),
        approvals=approval_repository,
        contexts=authority_store,
        audit=authority_store,
        capability_matcher=GovernedProviderReadAuthorityMatcher(
            capabilities=capabilities,
            providers=providers,
        ),
    )

    semantic_mapping_path = (
        Path(__file__).resolve().parents[4]
        / "config"
        / "semantic_mappings"
        / "approved.json"
    )
    semantic_mapping_registry = JsonSemanticMappingRegistryLoader(
        semantic_mapping_path
    ).load()

    resource_types, selector_keys, fact_hints = _resource_language_contract(capabilities)
    ollama_client = OllamaStructuredJsonClient(
        transport=http_transport,
        model=settings.ollama_model,
        base_url=settings.ollama_url,
    )
    action_intent_resolver = GovernedActionConversationIntentResolver(
        registry=capabilities,
        reasoner=OllamaActionIntentReasoner(ollama_client),
    )
    resource_intent_resolver = GovernedResourceConversationIntentResolver(
        interpreter=MetadataFirstResourceInquiryInterpreter(
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
        ),
        planner=GovernedResourceInquiryPlanner(
            registry=capabilities,
            reasoner=MetadataResourceCapabilityReasoner(
                semantic_mapping_registry=semantic_mapping_registry,
            ),
            semantic_mapping_registry=semantic_mapping_registry,
        ),
    )
    # Prefer read-only resource interpretation before action interpretation. This
    # removes an unnecessary action-model pass from ordinary questions while
    # remaining fail-safe: any resource result is still forced to permission_mode
    # observe and is revalidated against provider-neutral read-only capabilities.
    # If the message is not a resource inquiry, the action resolver gets the same
    # untouched human text and applies its normal governed action contract.
    intent_resolver = ChainedConversationIntentResolver(
        resolvers=(resource_intent_resolver, action_intent_resolver)
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
    flow = TeamsConversationFlow(
        identity_binder=identity_binder,
        intent_resolver=intent_resolver,
        request_factory=GovernedTeamsOrchestrationRequestFactory(
            authority=identity_authority,
            capabilities=capabilities,
            approvals=approval_repository,
        ),
        orchestrator=orchestrator,
        response_renderer=response_renderer,
        transport=return_transport,
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
