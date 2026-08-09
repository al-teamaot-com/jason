from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from connectors.core.contracts import Connector, ConnectorContext, ConnectorRequest, ConnectorResult


@dataclass(frozen=True, slots=True)
class ItGlueLiveReadRequest:
    organization_id: str
    principal_id: str
    correlation_id: str
    entity: str
    entity_id: str | int
    client_id: str | None = None

    def validate(self) -> None:
        for value, label in (
            (self.organization_id, "organization_id"),
            (self.principal_id, "principal_id"),
            (self.correlation_id, "correlation_id"),
            (self.entity, "entity"),
        ):
            if not str(value).strip():
                raise ValueError(f"{label} is required")
        try:
            parsed_id = int(self.entity_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("entity_id must be an integer") from exc
        if parsed_id < 1:
            raise ValueError("entity_id must be positive")


@dataclass(frozen=True, slots=True)
class ItGlueLiveReadSnapshot:
    organization_id: str
    correlation_id: str
    provider: str
    capability: str
    entity: str
    entity_id: str
    data: Mapping[str, Any]
    evidence_ids: tuple[str, ...]
    warnings: tuple[str, ...]


class ItGlueLiveReadService:
    """Execute one bounded observe-only IT Glue entity read through the connector boundary."""

    def __init__(self, connector: Connector) -> None:
        self._connector = connector

    def read(self, request: ItGlueLiveReadRequest) -> ItGlueLiveReadSnapshot:
        request.validate()
        capability = "it_glue.entity.get"
        if capability not in self._connector.capabilities:
            raise PermissionError("IT Glue connector does not expose the governed live-read capability")

        context = ConnectorContext(
            correlation_id=request.correlation_id,
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            capability=capability,
            mode="observe",
        )
        result: ConnectorResult = self._connector.execute(
            ConnectorRequest(
                context=context,
                arguments={"entity": request.entity, "entity_id": int(request.entity_id)},
            )
        )
        if result.provider != "it_glue" or result.capability != capability:
            raise RuntimeError("IT Glue live-read result does not match the requested provider/capability")

        return ItGlueLiveReadSnapshot(
            organization_id=request.organization_id,
            correlation_id=request.correlation_id,
            provider=result.provider,
            capability=result.capability,
            entity=request.entity,
            entity_id=str(int(request.entity_id)),
            data=result.data,
            evidence_ids=result.evidence_ids,
            warnings=result.warnings,
        )
