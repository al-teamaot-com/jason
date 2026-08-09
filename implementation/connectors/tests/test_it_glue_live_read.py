from __future__ import annotations

import pytest

from connectors.core.contracts import ConnectorRequest, ConnectorResult
from connectors.it_glue.live_read import ItGlueLiveReadRequest, ItGlueLiveReadService


class RecordingConnector:
    provider_name = "it_glue"
    capabilities = frozenset({"it_glue.entity.get"})

    def __init__(self) -> None:
        self.requests: list[ConnectorRequest] = []

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        self.requests.append(request)
        return ConnectorResult(
            capability=request.context.capability,
            provider="it_glue",
            data={"data": {"id": str(request.arguments["entity_id"]), "type": "configurations"}},
            evidence_ids=("evidence:it-glue:1",),
        )


def test_live_read_is_bounded_observe_only_and_tenant_scoped() -> None:
    connector = RecordingConnector()
    service = ItGlueLiveReadService(connector)

    snapshot = service.read(
        ItGlueLiveReadRequest(
            organization_id="org-208",
            principal_id="jason-operator",
            correlation_id="corr-live-itg-001",
            client_id="client-208",
            entity="Configurations",
            entity_id="42",
        )
    )

    sent = connector.requests[0]
    assert sent.context.organization_id == "org-208"
    assert sent.context.client_id == "client-208"
    assert sent.context.mode == "observe"
    assert sent.context.capability == "it_glue.entity.get"
    assert sent.arguments == {"entity": "Configurations", "entity_id": 42}
    assert snapshot.entity_id == "42"
    assert snapshot.evidence_ids == ("evidence:it-glue:1",)


def test_live_read_rejects_invalid_entity_id_before_provider_call() -> None:
    connector = RecordingConnector()
    service = ItGlueLiveReadService(connector)

    with pytest.raises(ValueError, match="entity_id"):
        service.read(
            ItGlueLiveReadRequest(
                organization_id="org-208",
                principal_id="jason-operator",
                correlation_id="corr-live-itg-002",
                entity="Configurations",
                entity_id="not-an-id",
            )
        )

    assert connector.requests == []


def test_live_read_rejects_connector_without_registered_capability() -> None:
    connector = RecordingConnector()
    connector.capabilities = frozenset()
    service = ItGlueLiveReadService(connector)

    with pytest.raises(PermissionError, match="governed live-read capability"):
        service.read(
            ItGlueLiveReadRequest(
                organization_id="org-208",
                principal_id="jason-operator",
                correlation_id="corr-live-itg-003",
                entity="Configurations",
                entity_id=42,
            )
        )

    assert connector.requests == []


def test_live_read_rejects_mismatched_provider_result() -> None:
    class BadConnector(RecordingConnector):
        def execute(self, request: ConnectorRequest) -> ConnectorResult:
            self.requests.append(request)
            return ConnectorResult(
                capability=request.context.capability,
                provider="datto_rmm",
                data={},
            )

    with pytest.raises(RuntimeError, match="provider/capability"):
        ItGlueLiveReadService(BadConnector()).read(
            ItGlueLiveReadRequest(
                organization_id="org-208",
                principal_id="jason-operator",
                correlation_id="corr-live-itg-004",
                entity="Configurations",
                entity_id=42,
            )
        )
