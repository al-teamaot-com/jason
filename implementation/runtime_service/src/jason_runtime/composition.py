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
from orchestrator.conversation_resource_intent import (
    GovernedResourceConversationIntentResolver,
    ReasonedResourceInquiryInterpreter,
)
from orchestrator.event_store import SQLiteOrchestrationEventStore
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.ollama_reasoning import (
    OllamaResourceCapabilityReasoner,
    OllamaResourceEvidenceReasoner,
    OllamaResourceInquiryReasoner,
    OllamaStructuredJsonClient,
)
from orchestrator.resource_capability_catalog import (
    DATTO_RMM_PROVIDER,
    ENDPOINT_DEVICE_READ,
    ENDPOINT_DEVICE_SEARCH,
    register_endpoint_resource_foundation,
)
from orchestrator.resource_evidence import (
    GovernedResourceEvidenceInterpreter,
    GovernedTeamsResourceResponseRenderer,
)
from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner
from orchestrator.service import CentralOrchestrator
from orchestrator.teams_conversation_flow import TeamsConversationFlow
from orchestrator.teams_identity_binding import JasonTeamsIdentityBinder
from orchestrator.teams_identity_binding_sqlite import (
    AuthorityIdentityRecordReader,
    SQLiteMicrosoftIdentityBindingStore,
)
from orchestrator.teams_request_factory import GovernedTeamsOrchestrationRequestFactory

from .cap007 import Cap007OpenBaoSecretBroker
from .http import RuntimeHttpApplication
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
            allowed_machine_identities=allowed,
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


def build_runtime_application(settings: RuntimeSettings) -> RuntimeHttpApplication:
    """Compose the production conversational runtime from governed Jason primitives."""

    settings.validate()

    authority_store = SQLiteIdentityAuthorityStore(settings.authority_db)
    identity_authority = IdentityAuthorityService(
        identities=SQLiteIdentityRepository(authority_store),
        grants=SQLiteAuthorityGrantRepository(authority_store),
        approvals=SQLiteApprovalRepository(authority_store),
        contexts=authority_store,
        audit=authority_store,
    )
    context_validator = ExecutionContextValidator(contexts=authority_store)

    bindings = SQLiteMicrosoftIdentityBindingStore(settings.bindings_db)
    identity_binder = JasonTeamsIdentityBinder(
        bindings=bindings,
        identities=AuthorityIdentityRecordReader(authority_store),
    )

    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )
    register_email_send(capabilities=capabilities, providers=providers)

    http_transport = UrlLibJsonHttpTransport()
    ollama_client = OllamaStructuredJsonClient(
        transport=http_transport,
        model=settings.ollama_model,
        base_url=settings.ollama_url,
    )
    intent_resolver = GovernedResourceConversationIntentResolver(
        interpreter=ReasonedResourceInquiryInterpreter(
            reasoner=OllamaResourceInquiryReasoner(ollama_client)
        ),
        planner=GovernedResourceInquiryPlanner(
            registry=capabilities,
            reasoner=OllamaResourceCapabilityReasoner(ollama_client),
        ),
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
        },
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
        audit=orchestration_events,
    )

    invokers = CapabilityInvokerRegistry()
    invokers.register(ENDPOINT_DEVICE_SEARCH, datto_invoker)
    invokers.register(ENDPOINT_DEVICE_READ, datto_invoker)
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

    response_renderer = GovernedTeamsResourceResponseRenderer(
        interpreter=GovernedResourceEvidenceInterpreter(
            reasoner=OllamaResourceEvidenceReasoner(ollama_client)
        )
    )
    return_transport = OpenClawReturnPathTransport()
    flow = TeamsConversationFlow(
        identity_binder=identity_binder,
        intent_resolver=intent_resolver,
        request_factory=GovernedTeamsOrchestrationRequestFactory(authority=identity_authority),
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
