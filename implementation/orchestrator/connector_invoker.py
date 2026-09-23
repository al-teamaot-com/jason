from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from connectors.core.contracts import (
    Connector,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    connector_execution_deadline,
)
from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationRequest
from .execution_plan import ExecutionPlan, PreparedExecutionPlan
from .service import InvocationResult, InvocationTelemetry


_DEFAULT_EXTERNAL_CONNECTOR_EXECUTION_SECONDS = 30.0
_PROVIDER_EXECUTION_SECONDS_METADATA = "provider_maximum_execution_seconds"


@dataclass(frozen=True, slots=True)
class ProviderPreparedExecution:
    """Provider adapter output used to build a secret-free central execution plan.

    `opaque` may hold the exact prepared transport request (including transient auth
    material) but is never persisted or fingerprinted. `payload`, `parameters`, and
    `symbolic_resolutions` must contain no secrets.
    """

    provider_capability: str
    action_method: str
    resource_type: str
    resource_identifier: str | None
    normalized_path: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    symbolic_resolutions: Mapping[str, Any] = field(default_factory=dict)
    opaque: Any = None


@dataclass(frozen=True, slots=True)
class _ConnectorPreparedEnvelope:
    provider_id: str
    provider_capability: str
    connector: Connector
    provider_prepared: ProviderPreparedExecution


@dataclass(frozen=True, slots=True)
class GovernedConnectorCapabilityInvoker:
    """Invoke an already-selected external connector through orchestration.

    Approved mutations may execute only through the prepare/bind/re-prepare path.
    A mutation connector that does not expose `prepare_governed_execution` and
    `execute_governed_execution` fails closed at the Central Orchestrator boundary.
    """

    connectors: Mapping[str, Connector]
    provider_capability_map: Mapping[tuple[str, str], str]
    default_maximum_execution_seconds: float = _DEFAULT_EXTERNAL_CONNECTOR_EXECUTION_SECONDS

    def __post_init__(self) -> None:
        if self.default_maximum_execution_seconds <= 0:
            raise ValueError("default_maximum_execution_seconds must be positive")

    def _resolved_connector(self, *, request: OrchestrationRequest, resolution: CapabilityResolutionResult):
        provider_id = (resolution.selected_provider_id or "").strip()
        if not provider_id:
            raise PermissionError("resolved external connector provider is required")
        connector = self.connectors.get(provider_id)
        if connector is None:
            raise LookupError(f"resolved connector provider is not registered: {provider_id}")
        provider_capability = self.provider_capability_map.get((provider_id, resolution.capability_name))
        if provider_capability is None:
            raise PermissionError(
                "resolved provider is not approved for canonical capability: "
                f"{resolution.capability_name}"
            )
        if provider_capability not in connector.capabilities:
            raise PermissionError("provider capability mapping is not exposed by the registered connector")
        connector_request = ConnectorRequest(
            context=ConnectorContext(
                correlation_id=request.correlation_id,
                principal_id=request.principal_id,
                organization_id=request.organization_id,
                client_id=request.client_id,
                capability=provider_capability,
                mode=request.permission_mode,
            ),
            arguments=request.arguments,
        )
        return provider_id, provider_capability, connector, connector_request

    def invoke(self, *, request: OrchestrationRequest, resolution: CapabilityResolutionResult) -> InvocationResult:
        provider_id, provider_capability, connector, connector_request = self._resolved_connector(
            request=request, resolution=resolution
        )
        maximum_execution_seconds = self._maximum_execution_seconds(resolution)
        with connector_execution_deadline(maximum_execution_seconds):
            result = connector.execute(connector_request)
        return self._invocation_result(
            result=result, connector=connector, provider_capability=provider_capability
        )

    def prepare_execution_plan(
        self, *, request: OrchestrationRequest, resolution: CapabilityResolutionResult
    ) -> PreparedExecutionPlan:
        provider_id, provider_capability, connector, connector_request = self._resolved_connector(
            request=request, resolution=resolution
        )
        prepare = getattr(connector, "prepare_governed_execution", None)
        execute = getattr(connector, "execute_governed_execution", None)
        if not callable(prepare) or not callable(execute):
            raise PermissionError(
                "resolved mutation connector does not expose governed execution-plan preparation/invocation"
            )
        maximum_execution_seconds = self._maximum_execution_seconds(resolution)
        with connector_execution_deadline(maximum_execution_seconds):
            provider_prepared = prepare(connector_request)
        if not isinstance(provider_prepared, ProviderPreparedExecution):
            raise TypeError("connector returned an invalid governed execution plan")
        if provider_prepared.provider_capability != provider_capability:
            raise PermissionError("prepared provider capability does not match approved provider mapping")
        plan = ExecutionPlan(
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            canonical_capability=resolution.capability_name,
            selected_provider_id=provider_id,
            provider_capability=provider_capability,
            action_method=provider_prepared.action_method,
            resource_type=provider_prepared.resource_type,
            resource_identifier=provider_prepared.resource_identifier,
            normalized_path=provider_prepared.normalized_path,
            normalized_payload=provider_prepared.payload,
            material_parameters=provider_prepared.parameters,
            symbolic_resolutions=provider_prepared.symbolic_resolutions,
        )
        return PreparedExecutionPlan(
            plan=plan,
            opaque=_ConnectorPreparedEnvelope(
                provider_id=provider_id,
                provider_capability=provider_capability,
                connector=connector,
                provider_prepared=provider_prepared,
            ),
        )

    def invoke_execution_plan(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
        prepared: PreparedExecutionPlan,
    ) -> InvocationResult:
        provider_id, provider_capability, connector, _ = self._resolved_connector(
            request=request, resolution=resolution
        )
        envelope = prepared.opaque
        if not isinstance(envelope, _ConnectorPreparedEnvelope):
            raise PermissionError("prepared execution plan is not a connector-bound plan")
        if envelope.connector is not connector:
            raise PermissionError("prepared execution plan connector identity changed")
        if envelope.provider_id != provider_id or envelope.provider_capability != provider_capability:
            raise PermissionError("prepared execution plan provider binding changed")
        execute = getattr(connector, "execute_governed_execution", None)
        if not callable(execute):
            raise PermissionError("resolved mutation connector cannot invoke a governed execution plan")
        maximum_execution_seconds = self._maximum_execution_seconds(resolution)
        with connector_execution_deadline(maximum_execution_seconds):
            result = execute(envelope.provider_prepared)
        return self._invocation_result(
            result=result, connector=connector, provider_capability=provider_capability
        )

    @staticmethod
    def _invocation_result(*, result: ConnectorResult, connector: Connector, provider_capability: str) -> InvocationResult:
        if result.provider != connector.provider_name:
            raise RuntimeError("connector result provider does not match registered connector")
        if result.capability != provider_capability:
            raise RuntimeError("connector result capability does not match approved mapping")
        return InvocationResult(
            output={
                "provider": result.provider,
                "provider_capability": result.capability,
                "data": dict(result.data),
                "evidence_ids": result.evidence_ids,
                "warnings": result.warnings,
            },
            attempts=1,
            telemetry=InvocationTelemetry(
                provider_resources=(f"{result.provider}:{result.capability}",),
                evidence_references=result.evidence_ids,
                hosted_model_used=False,
                hosted_model_input_tokens=0,
                hosted_model_output_tokens=0,
                hosted_model_cost_usd="0",
            ),
        )

    def _maximum_execution_seconds(self, resolution: CapabilityResolutionResult) -> float:
        metadata = getattr(resolution, "metadata", {}) or {}
        declared = metadata.get(_PROVIDER_EXECUTION_SECONDS_METADATA)
        if declared is None:
            return self.default_maximum_execution_seconds
        try:
            value = float(declared)
        except (TypeError, ValueError) as exc:
            raise ValueError("provider maximum execution seconds metadata must be numeric") from exc
        if value <= 0:
            raise ValueError("provider maximum execution seconds metadata must be positive")
        return min(value, self.default_maximum_execution_seconds)
