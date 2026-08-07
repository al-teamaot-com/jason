from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

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

from .context import AutotaskBusinessContextReader
from .local_llm import OllamaBusinessContextAnalyzer
from .service import AutotaskBusinessContextInvoker


CAPABILITY_NAME = "autotask.business.context"
CAPABILITY_VERSION = "1.0"
PROVIDER_ID = "jason.local-autotask-business-context"
MODEL_ID = "qwen3:1.7b"


@dataclass(slots=True)
class AutotaskBusinessContextRuntime:
    orchestrator: CentralOrchestrator
    event_store: SQLiteOrchestrationEventStore

    def close(self) -> None:
        self.event_store.close()


def build_autotask_business_context_runtime(
    *,
    autotask_connector: Connector,
    event_store_path: Path,
    repository_root: Path,
    model: str = MODEL_ID,
) -> AutotaskBusinessContextRuntime:
    now = datetime.now(timezone.utc)

    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    capabilities.register(
        CapabilityDefinition(
            capability_name=CAPABILITY_NAME,
            version=CAPABILITY_VERSION,
            display_name="Autotask Business Context",
            lifecycle_status=CapabilityLifecycle.PILOT,
            business_purpose=(
                "Assemble bounded read-only Autotask company context and produce "
                "a local operational briefing without requiring provider IDs."
            ),
            owner_service="central-orchestrator",
            architectural_capability_ids=frozenset({"JAC-003"}),
            risk_level=CapabilityRisk.LOW,
            data_classifications=frozenset({"internal"}),
            permitted_execution_modes=frozenset({ExecutionMode.LOCAL_AI.value}),
            input_schema_reference="CAP-003/autotask-business-context-request-v1",
            output_schema_reference="CAP-003/autotask-business-briefing-v1",
            invoking_roles=frozenset({"technician", "administrator"}),
            approval=CapabilityApproval(required=False),
            evidence=CapabilityEvidence(
                required=True,
                requirements=(
                    "bounded Autotask company context",
                    "derived local business briefing",
                    "business-context evidence",
                ),
                verification_requirements=(
                    "no provider-side change",
                    "local processing only",
                    "raw provider content excluded from evidence",
                    "provider identifiers derived by Jason",
                ),
            ),
            dependencies=frozenset(
                {
                    "autotask.company.search",
                    "autotask.contact.search",
                    "autotask.configuration_item.search",
                    "autotask.ticket.search",
                    "autotask.contract.search",
                    "autotask.project.search",
                }
            ),
            idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
            idempotency_key_required=False,
            timeout_seconds=180,
            maximum_attempts=1,
            failure_behavior="fail_closed",
            tenant_isolation_required=True,
            client_isolation_required=False,
            stewardship=CapabilityStewardship(
                steward="Jason Architecture Authority",
                business_justification=(
                    "Give AOT governed operational context from Autotask as a business "
                    "resource rather than limiting Jason to ticket-number workflows."
                ),
                review_interval_days=90,
                retirement_criteria=(
                    "A governed replacement supersedes CAP-003.",
                ),
                operational_owner="AOT Infrastructure Owner",
                approval_owner="Jason Architecture Authority",
                authoritative_change_sources=("Project Jason repository",),
            ),
            created_at=now,
            metadata={
                "pilot": "true",
                "local_processing": "required",
                "cap_002_convergence": "required",
            },
        )
    )

    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    providers.register(
        ExecutionProvider(
            provider_id=PROVIDER_ID,
            display_name="Jason Local Autotask Business Context",
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
                maximum_execution_seconds=180,
            ),
            features=ProviderFeatures(structured_output=True),
            pricing_profile_id="local-zero-cost",
            stewardship=ProviderStewardship(
                technology_steward="Technology Steward",
                business_justification=(
                    "Provide private local reasoning over governed Autotask business data."
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
    resolution = GovernedCapabilityResolutionEngine(
        capabilities=capabilities,
        providers=providers,
        policy=ExecutionPolicyEngine(cost_estimator=CostEstimator(pricing)),
    )

    invokers = CapabilityInvokerRegistry()
    invokers.register(
        CAPABILITY_NAME,
        AutotaskBusinessContextInvoker(
            reader=AutotaskBusinessContextReader(autotask_connector),
            analyzer=OllamaBusinessContextAnalyzer(model=model),
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
    return AutotaskBusinessContextRuntime(
        orchestrator=orchestrator,
        event_store=event_store,
    )
