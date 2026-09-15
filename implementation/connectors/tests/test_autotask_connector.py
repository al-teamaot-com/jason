from __future__ import annotations

from typing import Any, Mapping

import pytest

from connectors.autotask.connector import AutotaskConnector
from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)


class FakeSecrets:
    def resolve(
        self,
        logical_name: str,
        context: ConnectorContext,
    ) -> Mapping[str, str]:
        assert logical_name == "autotask.readonly"

        return {
            "username": "api-user@example.invalid",
            "secret": "synthetic-secret",
            "integration_code": "synthetic-integration-code",
        }


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, Any]]] = []

    def record(
        self,
        event_type: str,
        context: ConnectorContext,
        details: Mapping[str, Any],
    ) -> None:
        self.events.append((event_type, details))


class FakeTransport:
    def __init__(self, zone_url: str | None) -> None:
        self.zone_url = zone_url
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": params,
                "json": json,
                "timeout_seconds": timeout_seconds,
            }
        )

        if url.endswith("/v1.0/zoneInformation"):
            if self.zone_url is None:
                return {"zoneName": "Unknown"}

            return {
                "zoneName": "America East",
                "url": self.zone_url,
                "webUrl": "https://ww3.autotask.net/",
                "ci": 12345,
            }

        return {
            "item": {
                "id": 12345,
                "title": "Synthetic ticket",
            }
        }


class PaginatedFakeTransport(FakeTransport):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        if url.endswith("/v1.0/zoneInformation"):
            return super().request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json,
                timeout_seconds=timeout_seconds,
            )

        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": params,
                "json": json,
                "timeout_seconds": timeout_seconds,
            }
        )

        if url.endswith("/V1.0/Tickets/query"):
            return {
                "items": [{"id": 101, "ticketNumber": "T-PAGE-1"}],
                "pageDetails": {
                    "nextPageUrl": (
                        "https://webservices3.autotask.net/"
                        "atservicesrest/V1.0/Tickets/query?page=2"
                    ),
                },
            }

        if url.endswith("/V1.0/Tickets/query?page=2"):
            return {
                "items": [{"id": 102, "ticketNumber": "T-PAGE-2"}],
                "pageDetails": {
                    "nextPageUrl": (
                        "https://webservices3.autotask.net/"
                        "atservicesrest/V1.0/Tickets/query?page=3"
                    ),
                },
            }

        if url.endswith("/V1.0/Tickets/query?page=3"):
            return {
                "items": [{"id": 103, "ticketNumber": "T-PAGE-3"}],
                "pageDetails": {},
            }

        raise AssertionError(f"unexpected transport URL: {url}")


def _request() -> ConnectorRequest:
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-1",
            principal_id="user-1",
            organization_id="team-aot",
            client_id=None,
            capability="autotask.ticket.get",
            mode="observe",
        ),
        arguments={"ticket_id": 12345},
    )


def _search_request() -> ConnectorRequest:
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-pagination",
            principal_id="user-1",
            organization_id="team-aot",
            client_id=None,
            capability="autotask.ticket.search",
            mode="observe",
        ),
        arguments={
            "search": (
                '{"MaxRecords":3,"filter":'
                '[{"field":"id","op":"exist"}]}'
            ),
        },
    )


def test_discovers_zone_before_authenticated_ticket_request() -> None:
    transport = FakeTransport(
        "https://webservices3.autotask.net/atservicesrest/"
    )
    audit = FakeAudit()

    connector = AutotaskConnector(
        secrets=FakeSecrets(),
        transport=transport,
        audit=audit,
    )

    result = connector.execute(_request())

    assert result.data["item"]["id"] == 12345
    assert len(transport.requests) == 2

    zone_request = transport.requests[0]
    assert zone_request["method"] == "GET"
    assert zone_request["url"] == (
        "https://webservices.autotask.net/"
        "atservicesrest/v1.0/zoneInformation"
    )
    assert zone_request["params"] == {
        "user": "api-user@example.invalid"
    }
    assert "Secret" not in zone_request["headers"]
    assert "ApiIntegrationCode" not in zone_request["headers"]

    ticket_request = transport.requests[1]
    assert ticket_request["url"] == (
        "https://webservices3.autotask.net/"
        "atservicesrest/V1.0/Tickets/12345"
    )
    assert ticket_request["headers"]["UserName"] == (
        "api-user@example.invalid"
    )
    assert ticket_request["headers"]["Secret"] == (
        "synthetic-secret"
    )


def test_invalid_zone_response_fails_before_ticket_request() -> None:
    transport = FakeTransport(None)

    connector = AutotaskConnector(
        secrets=FakeSecrets(),
        transport=transport,
        audit=FakeAudit(),
    )

    with pytest.raises(
        ConnectorConfigurationError,
        match="zone discovery",
    ):
        connector.execute(_request())

    assert len(transport.requests) == 1


def test_ticket_search_follows_third_page_within_requested_bound() -> None:
    transport = PaginatedFakeTransport(
        "https://webservices3.autotask.net/atservicesrest/"
    )
    audit = FakeAudit()

    connector = AutotaskConnector(
        secrets=FakeSecrets(),
        transport=transport,
        audit=audit,
    )

    result = connector.execute(_search_request())

    assert [item["id"] for item in result.data["items"]] == [
        101,
        102,
        103,
    ]
    assert result.data["items"][2]["ticketNumber"] == "T-PAGE-3"
    assert result.data["jasonPagination"] == {
        "pagesFetched": 3,
        "itemCount": 3,
        "requestedMaxRecords": 3,
        "requestedLimitSatisfied": True,
    }
    assert len(transport.requests) == 4
    assert transport.requests[2]["params"] is None
    assert transport.requests[3]["params"] is None
    assert audit.events[-1][0] == "connector.completed"
    assert audit.events[-1][1]["provider_pages_examined"] == 3
