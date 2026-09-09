from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from connectors.core.contracts import (
    Connector,
    ConnectorContext,
    ConnectorRequest,
    connector_execution_deadline,
)
from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationRequest
from .service import InvocationResult


_DEFAULT_EXTERNAL_CONNECTOR_EXECUTION_SECONDS = 30.0
_PROVIDER_EXECUTION_SECONDS_METADATA = "provider_maximum_execution_seconds"


@dataclass(frozen=True, slots=True)
class GovernedConnectorCapabilityInvoker:
    """Invoke an already-selected external connector through orchestration.

    Provider selection is owned by governed capability resolution. This adapter only
    permits the resolved provider to execute the requested canonical capability and
    preserves Jason identity/client scope and authority mode in the connector context.
    Execution strategy and authority permission are intentionally separate concepts.

    One governed deadline covers the whole logical connector invocation, including
    any bounded discovery and follow-up reads performed by the connector. Individual
    HTTP timeouts therefore cannot multiply into an unbounded conversational stall.
    """

    connectors: Mapping[str, Connector]
    provider_capability_map: Mapping[tuple[str, str], str]
    default_maximum_execution_seconds: float = _DEFAULT_EXTERNAL_CONNECTOR_EXECUTION_SECONDS

    def __post_init__(self) -> None:
        if self.default_maximum_execution_seconds <= 0:
            raise ValueError("default_maximum_execution_seconds must be positive")

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        provider_id = (resolution.selected_provider_id or "").strip()
        if not provider_id:
            raise PermissionError("resolved external connector provider is required")

        connector = self.connectors.get(provider_id)
        if connector is None:
            raise LookupError(f"resolved connector provider is not registered: {provider_id}")

        provider_capability = self.provider_capability_map.get(
            (provider_id, resolution.capability_name)
        )
        if provider_capability is None:
            raise PermissionError(
                "resolved provider is not approved for canonical capability: "
                f"{resolution.capability_name}"
            )
        if provider_capability not in connector.capabilities:
            raise PermissionError(
                "provider capability mapping is not exposed by the registered connector"
            )

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
        maximum_execution_seconds = self._maximum_execution_seconds(resolution)
        with connector_execution_deadline(maximum_execution_seconds):
            result = connector.execute(connector_request)
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
        )

    def _maximum_execution_seconds(
        self,
        resolution: CapabilityResolutionResult,
    ) -> float:
        metadata = getattr(resolution, "metadata", {}) or {}
        declared = metadata.get(_PROVIDER_EXECUTION_SECONDS_METADATA)
        if declared is None:
            return self.default_maximum_execution_seconds
        try:
            value = float(declared)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "provider maximum execution seconds metadata must be numeric"
            ) from exc
        if value <= 0:
            raise ValueError(
                "provider maximum execution seconds metadata must be positive"
            )
        return min(value, self.default_maximum_execution_seconds)
