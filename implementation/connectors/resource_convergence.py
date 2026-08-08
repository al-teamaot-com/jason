from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from connectors.core.contracts import Connector, ConnectorContext, ConnectorRequest, ConnectorResult
from connectors.core.relationships import (
    ProviderRelationshipEvidence,
    ResourceRef,
    VerificationState,
)
from connectors.core.resource_gateway import ResourceOperation, ResourceQuery, ResourceRegistry
from connectors.kaseya_resource_catalog import build_kaseya_resource_registry
from connectors.provider_resource_adapters import (
    ConnectorInvocation,
    translate_datto_rmm_resource,
    translate_it_glue_resource,
)


@dataclass(frozen=True, slots=True)
class PlannedProviderRead:
    query: ResourceQuery
    invocation: ConnectorInvocation


@dataclass(frozen=True, slots=True)
class ConfigurationDeviceConvergencePlan:
    organization_id: str
    configuration_id: str
    search_hint: str
    reads: tuple[PlannedProviderRead, PlannedProviderRead]


@dataclass(frozen=True, slots=True)
class IdentityEvidence:
    provider: str
    resource_type: str
    external_id: str
    organization_id: str
    attributes: Mapping[str, str]
    source_authority: str = "governed-provider-read"


class ResourceConvergenceError(ValueError):
    pass


def _translate(query: ResourceQuery) -> ConnectorInvocation:
    if query.provider == "it_glue":
        return translate_it_glue_resource(query)
    if query.provider == "datto_rmm":
        return translate_datto_rmm_resource(query)
    raise ResourceConvergenceError(f"Unsupported convergence provider: {query.provider}")


def build_configuration_device_plan(
    *,
    organization_id: str,
    configuration_id: str,
    search_hint: str,
    registry: ResourceRegistry | None = None,
) -> ConfigurationDeviceConvergencePlan:
    if not organization_id.strip():
        raise ResourceConvergenceError("organization_id is required")
    if not configuration_id.strip():
        raise ResourceConvergenceError("configuration_id is required")
    if not search_hint.strip():
        raise ResourceConvergenceError("search_hint is required for the first bounded Datto lookup")

    registry = registry or build_kaseya_resource_registry()

    it_glue_query = ResourceQuery(
        provider="it_glue",
        resource_type="entity",
        operation=ResourceOperation.GET,
        organization_id=organization_id,
        resource_id=configuration_id,
        filters={"entity": "Configurations"},
    )
    datto_query = ResourceQuery(
        provider="datto_rmm",
        resource_type="device",
        operation=ResourceOperation.QUERY,
        organization_id=organization_id,
        filters={"search": search_hint},
        page_size=100,
    )

    registry.authorize(it_glue_query)
    registry.authorize(datto_query)

    return ConfigurationDeviceConvergencePlan(
        organization_id=organization_id,
        configuration_id=configuration_id,
        search_hint=search_hint,
        reads=(
            PlannedProviderRead(it_glue_query, _translate(it_glue_query)),
            PlannedProviderRead(datto_query, _translate(datto_query)),
        ),
    )


class GovernedResourceExecutor:
    """Execute approved resource reads through existing connector boundaries.

    This class contains no provider credentials and performs no provider-to-provider
    calls. Each provider read remains an independent connector invocation under the
    same organization, principal, client, and correlation context.
    """

    def __init__(
        self,
        connectors: Mapping[str, Connector],
        registry: ResourceRegistry | None = None,
    ) -> None:
        self._connectors = dict(connectors)
        self._registry = registry or build_kaseya_resource_registry()

    def execute(self, query: ResourceQuery, context: ConnectorContext) -> ConnectorResult:
        self._registry.authorize(query)
        if not query.organization_id or query.organization_id != context.organization_id:
            raise ResourceConvergenceError(
                "Resource query organization must exactly match active connector context"
            )

        invocation = _translate(query)
        connector = self._connectors.get(query.provider)
        if connector is None:
            raise ResourceConvergenceError(f"Connector is not registered: {query.provider}")

        request = ConnectorRequest(
            context=ConnectorContext(
                correlation_id=context.correlation_id,
                principal_id=context.principal_id,
                organization_id=context.organization_id,
                client_id=context.client_id,
                capability=invocation.capability,
                mode="observe",
            ),
            arguments=invocation.arguments,
        )
        return connector.execute(request)


def build_configuration_device_relationship_evidence(
    *,
    configuration: IdentityEvidence,
    device: IdentityEvidence,
    matched_attributes: tuple[str, ...],
    confidence: float,
    verification: VerificationState = VerificationState.CORROBORATED,
) -> ProviderRelationshipEvidence:
    if configuration.provider != "it_glue" or configuration.resource_type != "configuration":
        raise ResourceConvergenceError("configuration evidence must identify an IT Glue configuration")
    if device.provider != "datto_rmm" or device.resource_type != "device":
        raise ResourceConvergenceError("device evidence must identify a Datto RMM device")
    if configuration.organization_id != device.organization_id:
        raise ResourceConvergenceError("Cross-organization device correlation is denied")
    if not matched_attributes:
        raise ResourceConvergenceError("At least one governed matching attribute is required")

    for attribute in matched_attributes:
        left = configuration.attributes.get(attribute, "").strip().casefold()
        right = device.attributes.get(attribute, "").strip().casefold()
        if not left or left != right:
            raise ResourceConvergenceError(
                f"Matching attribute is absent or inconsistent: {attribute}"
            )

    return ProviderRelationshipEvidence(
        provider="jason_resource_convergence",
        source=ResourceRef(
            provider="it_glue",
            resource_type="configuration",
            external_id=configuration.external_id,
            organization_id=configuration.organization_id,
        ),
        target=ResourceRef(
            provider="datto_rmm",
            resource_type="device",
            external_id=device.external_id,
            organization_id=device.organization_id,
        ),
        provider_relationship="governed_identity_corroboration",
        canonical_relationship="represents",
        verification=verification,
        confidence=confidence,
        observed_at=datetime.now(timezone.utc),
        source_authority=(
            f"central-orchestrator:{configuration.source_authority}+{device.source_authority}"
        ),
        metadata={"matched_attributes": ",".join(matched_attributes)},
    )
