from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from connectors.core.contracts import (
    ConnectorRequest,
    ConnectorResult,
    bounded_transport_timeout,
    connector_execution_deadline,
)
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.execution_providers import (
    ExecutionProvider,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest


def test_execution_provider_limit_exposes_governed_maximum_execution_seconds():
    provider = ExecutionProvider(
        provider_id="synthetic-provider",
        display_name="Synthetic Provider",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({"synthetic.resource.read"}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset({"us"}),
        limits=ProviderLimits(maximum_execution_seconds=17),
        features=ProviderFeatures(),
        pricing_profile_id=None,
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="bounded execution contract regression",
            review_interval_days=90,
            last_reviewed_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
            retirement_criteria=("provider retired",),
        ),
        created_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
    )

    assert provider.limits.maximum_execution_seconds == 17


def test_transport_timeout_is_clamped_by_one_logical_connector_deadline():
    with connector_execution_deadline(5):
        first = bounded_transport_timeout(30)
        second = bounded_transport_timeout(30)

    assert 0 < first <= 5
    assert 0 < second <= first


@dataclass
class DeadlineObservingConnector:
    provider_name: str = "synthetic-provider"
    capabilities = frozenset({"synthetic.resource.read"})
    observed_timeout: float | None = None

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        self.observed_timeout = bounded_transport_timeout(90)
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data={"status": "ok"},
        )


@dataclass(frozen=True)
class Resolution:
    capability_name: str = "synthetic.resource.read"
    selected_provider_id: str | None = "synthetic-provider"
    metadata: dict[str, str] | None = None


def _request() -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-bounded",
        correlation_id="corr-bounded",
        principal_id="person-test",
        organization_id="aot",
        client_id="aot",
        capability_name="synthetic.resource.read",
        capability_version="1.0",
        requested_mode="deterministic",
        permission_mode="observe",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0")),
        arguments={"resource_reference": "NODE-77"},
    )


def test_connector_invoker_applies_one_default_deadline_to_the_whole_provider_call():
    connector = DeadlineObservingConnector()
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={"synthetic-provider": connector},
        provider_capability_map={
            ("synthetic-provider", "synthetic.resource.read"): "synthetic.resource.read"
        },
        default_maximum_execution_seconds=7,
    )

    invoker.invoke(request=_request(), resolution=Resolution())  # type: ignore[arg-type]

    assert connector.observed_timeout is not None
    assert 0 < connector.observed_timeout <= 7


def test_provider_declared_deadline_can_only_tighten_the_default_bound():
    connector = DeadlineObservingConnector()
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={"synthetic-provider": connector},
        provider_capability_map={
            ("synthetic-provider", "synthetic.resource.read"): "synthetic.resource.read"
        },
        default_maximum_execution_seconds=30,
    )

    invoker.invoke(
        request=_request(),
        resolution=Resolution(
            metadata={"provider_maximum_execution_seconds": "4"}
        ),  # type: ignore[arg-type]
    )

    assert connector.observed_timeout is not None
    assert 0 < connector.observed_timeout <= 4
