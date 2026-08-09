from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from connectors.core.contracts import ConnectorContext, ConnectorResult
from connectors.core.relationships import ProviderRelationshipEvidence, VerificationState
from connectors.resource_convergence import (
    ConfigurationDeviceConvergencePlan,
    GovernedResourceExecutor,
    IdentityEvidence,
    ResourceConvergenceError,
    build_configuration_device_plan,
    build_relationship_evidence,
)


IdentityProjector = Callable[[ConnectorResult, str], IdentityEvidence]


@dataclass(frozen=True, slots=True)
class LiveConfigurationDeviceConvergenceRequest:
    organization_id: str
    principal_id: str
    correlation_id: str
    configuration_id: str
    search_hint: str
    matched_attributes: tuple[str, ...]
    confidence: float
    client_id: str | None = None
    candidate_limit: int = 5

    def validate(self) -> None:
        for value, label in (
            (self.organization_id, "organization_id"),
            (self.principal_id, "principal_id"),
            (self.correlation_id, "correlation_id"),
            (self.configuration_id, "configuration_id"),
            (self.search_hint, "search_hint"),
        ):
            if not value.strip():
                raise ValueError(f"{label} is required")
        if not self.matched_attributes:
            raise ValueError("matched_attributes is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 1 <= self.candidate_limit <= 5:
            raise ValueError("candidate_limit must be between 1 and 5")


@dataclass(frozen=True, slots=True)
class LiveConvergenceObservation:
    provider_results: Mapping[str, ConnectorResult]
    evidence: ProviderRelationshipEvidence


class LiveConfigurationDeviceConvergenceService:
    """Run bounded IT Glue + Datto reads and produce relationship evidence only.

    Projection of provider payloads into IdentityEvidence is injected so provider
    schema parsing remains separate from orchestration. The service never promotes
    evidence into canonical truth and grants no identity or execution authority.
    """

    def __init__(
        self,
        *,
        executor: GovernedResourceExecutor,
        it_glue_projector: IdentityProjector,
        datto_projector: IdentityProjector,
    ) -> None:
        self._executor = executor
        self._it_glue_projector = it_glue_projector
        self._datto_projector = datto_projector

    def observe(self, request: LiveConfigurationDeviceConvergenceRequest) -> LiveConvergenceObservation:
        request.validate()
        plan = build_configuration_device_plan(
            organization_id=request.organization_id,
            configuration_id=request.configuration_id,
            search_hint=request.search_hint,
            candidate_limit=request.candidate_limit,
        )
        return self._execute_plan(plan, request)

    def _execute_plan(
        self,
        plan: ConfigurationDeviceConvergencePlan,
        request: LiveConfigurationDeviceConvergenceRequest,
    ) -> LiveConvergenceObservation:
        context = ConnectorContext(
            correlation_id=request.correlation_id,
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            capability="resource.convergence.observe",
            mode="observe",
        )
        results: dict[str, ConnectorResult] = {}
        for read in plan.reads:
            result = self._executor.execute(read.query, context)
            if result.provider != read.query.provider:
                raise ResourceConvergenceError("provider result does not match planned governed read")
            results[read.query.provider] = result

        if set(results) != {"it_glue", "datto_rmm"}:
            raise ResourceConvergenceError("live convergence did not produce both governed provider observations")

        configuration = self._it_glue_projector(results["it_glue"], request.organization_id)
        device = self._datto_projector(results["datto_rmm"], request.organization_id)
        if configuration.provider != "it_glue" or configuration.resource_type != "configuration":
            raise ResourceConvergenceError("IT Glue projector returned an invalid identity boundary")
        if device.provider != "datto_rmm" or device.resource_type != "device":
            raise ResourceConvergenceError("Datto projector returned an invalid identity boundary")
        if configuration.organization_id != request.organization_id or device.organization_id != request.organization_id:
            raise PermissionError("projected provider evidence organization mismatch")

        evidence = build_relationship_evidence(
            source=configuration,
            target=device,
            matched_attributes=request.matched_attributes,
            canonical_relationship="represents",
            provider_relationship="live_configuration_device_corroboration",
            confidence=request.confidence,
            verification=VerificationState.CORROBORATED,
        )
        return LiveConvergenceObservation(provider_results=results, evidence=evidence)
