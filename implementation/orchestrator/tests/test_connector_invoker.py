from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from connectors.core.contracts import ConnectorRequest, ConnectorResult
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest


@dataclass
class FakeConnector:
    provider_name: str = "datto_rmm"
    capabilities = frozenset({"datto_rmm.device.search"})
    received: ConnectorRequest | None = None

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        self.received = request
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data={"devices": [{"hostname": "AOT-50282", "deviceUid": "dev-1"}]},
        )


@dataclass(frozen=True)
class Resolution:
    capability_name: str = "endpoint.device.search"
    selected_provider_id: str | None = "datto_rmm"


def request() -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="principal-1",
        organization_id="aot",
        client_id="aot",
        capability_name="endpoint.device.search",
        capability_version="1.0",
        requested_mode="observe",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0")),
        arguments={"search": "AOT-50282"},
    )


def test_invoker_preserves_identity_scope_and_maps_canonical_capability() -> None:
    connector = FakeConnector()
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={"datto_rmm": connector},
        provider_capability_map={
            ("datto_rmm", "endpoint.device.search"): "datto_rmm.device.search"
        },
    )

    result = invoker.invoke(request=request(), resolution=Resolution())  # type: ignore[arg-type]

    assert connector.received is not None
    assert connector.received.context.principal_id == "principal-1"
    assert connector.received.context.organization_id == "aot"
    assert connector.received.context.client_id == "aot"
    assert connector.received.context.capability == "datto_rmm.device.search"
    assert result.output["provider"] == "datto_rmm"


def test_invoker_fails_closed_when_provider_mapping_is_missing() -> None:
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={"datto_rmm": FakeConnector()},
        provider_capability_map={},
    )

    with pytest.raises(PermissionError, match="not approved"):
        invoker.invoke(request=request(), resolution=Resolution())  # type: ignore[arg-type]


def test_invoker_fails_closed_when_resolution_selects_unknown_provider() -> None:
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={"datto_rmm": FakeConnector()},
        provider_capability_map={
            ("datto_rmm", "endpoint.device.search"): "datto_rmm.device.search"
        },
    )

    with pytest.raises(LookupError, match="not registered"):
        invoker.invoke(
            request=request(),
            resolution=Resolution(selected_provider_id="other_provider"),  # type: ignore[arg-type]
        )
