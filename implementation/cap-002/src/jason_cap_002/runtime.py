from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from connectors.autotask.live_read import GovernedAutotaskLiveRead
from connectors.core.contracts import Connector
from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
    InMemoryCapabilityRegistry,
)
from kernel.execution_policy import (
    CostEstimator,
    ExecutionMode,
    ExecutionPolicyEngine,
    InMemoryPricingRegistry,
    PriceConfidence,
    PricingEntry,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from kernel.resolution import GovernedCapabilityResolutionEngine
from orchestrator import (
    CapabilityInvokerRegistry,
    CentralOrchestrator,
    SQLiteOrchestrationEventStore,
)

from .local_llm import OllamaTicketAnalyzer
from .service import TicketIntelligenceInvoker


CAPABILITY_NAME = "support.ticket.analyze"
CAPABILITY_VERSION = "1.0"
PROVIDER_ID = "jason.local-ticket-intelligence"
MODEL_ID = "qwen3:1.7b"


@dataclass(slots=True)
class TicketIntelligenceRuntime:
    orchestrator: CentralOrchestrator
    event_store: SQLiteOrchestrationEventStore

    def close(self) -> None:
        self.event_store.close()


def build_ticket_intelligence_runtime(
    *,
    autotask_connector: Connector,
    event_store_path: Path,
    repository_root: Path,
    model: str = MODEL_ID,
) -> TicketIntelligenceRuntime:
    now = datetime.now(timezone.utc)

    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    capabilities.register(
        CapabilityDefinition(
            capability_name=CAPABILITY_NAME,
            version=CAPABILITY_VERSION,
            display_name="Local Ticket Intelligence",
            lifecycle_status=CapabilityLifecycle.PILOT,
            business_purpose=(
                "Analyze one authorized Autotask ticket locally and produce a "
                "read-only technician briefing."
            ),
            owner_service="central-orchestrator",
            architectural_capability_ids=frozenset({"JAC-002"}),
            risk_level=CapabilityRisk.LOW,
            data_classifications=frozenset({"internal"}),
            permitted_execution_modes=frozenset({ExecutionMode.LOCAL_AI.value}),
            input_schema_reference="CAP-002/ticket-intelligence-request-v1",
            output_schema_reference="CAP-002/ticket-briefing-v1",
            invoking_roles=frozenset({"technician", "administrator"}),
            approval=CapabilityApproval(required=False),
            evidence=CapabilityEvidence(
                required=True,
                requirements=(
                    "canonical Autotask live-read evidence",
                    "derived briefing artifact",
                    "ticket-intelligence evidence",
                ),
                verification_requirements=(
                    "no provider-side change",
                    "local processing only",
                    "raw ticket content excluded from evidence",
                ),
            ),
            dependencies=frozenset({"autotask.ticket.search"}),
            idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
            idempotency_key_required=False,
            timeout_seconds=120,
            maximum_attempts=1,
            failure_behavior="fail_closed",
            tenant_isolation_required=True,
            client_isolation_required=False,
            stewardship=CapabilityStewardship(
                steward="Jason Architecture Authority",
                business_justification=(
                    "Reduce technician triage time while keeping ticket data and "
                    "inference on the Jason host."
                ),
                review_interval_days=90,
                retirement_criteria=(
                    "A governed replacement capability supersedes CAP-002.",
                ),
                operational_owner="AOT Infrastructure Owner",
                approval_owner="Jason Architecture Authority",
                authoritative_change_sources=("Project Jason repository",),
            ),
            created_at=now,
            metadata={"pilot": "true", "local_processing": "required"},
        )
    )

    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    providers.register(
        ExecutionProvider(
            provider_id=PROVIDER_ID,
            display_name="Jason Local Ollama Ticket Intelligence",
            provider_type=ProviderType.LOCAL_AI,
            lifecycle_status=ProviderLifecycle.AVAILABLE,
            health_status=ProviderHealth.HEALTHY,
            approval_status=ProviderApproval.PILOT,
            execution_modes=frozenset({ExecutionMode.LOCAL_AI.value}),
            capabilities=frozenset({CAPABILITY_NAME}),
            supported_classifications=frozenset({"internal"}),
            regions=frozenset({"local"}),
            limits=ProviderLimits(
                maximum_context_tokens=40960,
                maximum_concurrent_executions=1,
                maximum_execution_seconds=120,
            ),
            features=ProviderFeatures(structured_output=True),
            pricing_profile_id="local-zero-cost",
            stewardship=ProviderStewardship(
                technology_steward="Technology Steward",
                business_justification=(
                    "Provide private local inference for governed MSP analysis."
                ),
                review_interval_days=30,
                last_reviewed_at=now,
                retirement_criteria=(
                    "Ollama is replaced by a governed local inference runtime.",
                ),
                operational_owner="AOT Infrastructure Owner",
                approval_owner="Jason Architecture Authority",
                vendor_change_sources=("Ollama release notes",),
            ),
            created_at=now,
            metadata={"model_id": model, "runtime": "ollama"},
        )
    )

    pricing = InMemoryPricingRegistry(
        entries=(
            PricingEntry(
                provider_id=PROVIDER_ID,
                model_id=model,
                execution_mode=ExecutionMode.LOCAL_AI,
                input_cost_per_million_tokens=Decimal("0"),
                output_cost_per_million_tokens=Decimal("0"),
                pricing_version="local-zero-cost-v1",
                confidence=PriceConfidence.HIGH,
            ),
        )
    )
    policy = ExecutionPolicyEngine(
        cost_estimator=CostEstimator(pricing)
    )
    resolution = GovernedCapabilityResolutionEngine(
        capabilities=capabilities,
        providers=providers,
        policy=policy,
    )

    invokers = CapabilityInvokerRegistry()
    invokers.register(
        CAPABILITY_NAME,
        TicketIntelligenceInvoker(
            autotask=GovernedAutotaskLiveRead(autotask_connector),
            analyzer=OllamaTicketAnalyzer(model=model),
            repository_root=repository_root,
        ),
    )

    event_store_path.parent.mkdir(parents=True, exist_ok=True)
    event_store = SQLiteOrchestrationEventStore(event_store_path)
    orchestrator = CentralOrchestrator(
        resolution=resolution,
        invoker=invokers,
        audit=event_store,
    )
    return TicketIntelligenceRuntime(
        orchestrator=orchestrator,
        event_store=event_store,
    )
