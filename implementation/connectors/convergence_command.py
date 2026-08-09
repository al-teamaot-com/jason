from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from connectors.convergence_projectors import (
    project_datto_rmm_device,
    project_it_glue_configuration,
)
from connectors.core.contracts import Connector
from connectors.live_convergence import (
    LiveConfigurationDeviceConvergenceRequest,
    LiveConfigurationDeviceConvergenceService,
    LiveConvergenceObservation,
)
from connectors.resource_convergence import GovernedResourceExecutor


@dataclass(frozen=True, slots=True)
class OperationalConvergenceCommand:
    organization_id: str
    principal_id: str
    correlation_id: str
    configuration_id: str
    search_hint: str
    matched_attributes: tuple[str, ...]
    confidence: float = 1.0
    client_id: str | None = None
    candidate_limit: int = 1


class OperationalConvergenceRunner:
    """Single bounded operator-facing entry point for IT Glue -> Datto observation.

    The runner wires only existing governed components. It does not grant authority,
    promote evidence, mutate provider resources, or bypass connector secret/audit
    boundaries.
    """

    def __init__(self, connectors: Mapping[str, Connector]) -> None:
        expected = {"it_glue", "datto_rmm"}
        missing = expected - set(connectors)
        if missing:
            raise ValueError(f"required convergence connectors are missing: {sorted(missing)}")
        executor = GovernedResourceExecutor(
            {"it_glue": connectors["it_glue"], "datto_rmm": connectors["datto_rmm"]}
        )
        self._service = LiveConfigurationDeviceConvergenceService(
            executor=executor,
            it_glue_projector=project_it_glue_configuration,
            datto_projector=project_datto_rmm_device,
        )

    def run(self, command: OperationalConvergenceCommand) -> LiveConvergenceObservation:
        request = LiveConfigurationDeviceConvergenceRequest(
            organization_id=command.organization_id,
            principal_id=command.principal_id,
            correlation_id=command.correlation_id,
            configuration_id=command.configuration_id,
            search_hint=command.search_hint,
            matched_attributes=command.matched_attributes,
            confidence=command.confidence,
            client_id=command.client_id,
            candidate_limit=command.candidate_limit,
        )
        return self._service.observe(request)
