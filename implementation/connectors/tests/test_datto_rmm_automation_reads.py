from __future__ import annotations

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.datto_rmm.auth import DattoRmmAccessToken
from connectors.datto_rmm.automation_reads import DattoRmmAutomationReadConnector


class Secrets:
    def resolve(self, logical_secret, context):
        assert logical_secret == "datto_rmm.readonly"
        return {
            "api_url": "https://example.invalid",
            "api_key": "durable-key",
            "api_secret": "durable-secret",
        }


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(
        self,
        *,
        method,
        url,
        headers,
        params=None,
        json=None,
        timeout_seconds=30.0,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": dict(params or {}),
                "json": json,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.responses.pop(0)


def request(*, capability: str, arguments):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-automation-1",
            principal_id="person-1",
            organization_id="aot",
            client_id=None,
            capability=capability,
            mode="observe",
        ),
        arguments=arguments,
    )


def patch_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )


def test_component_search_completes_catalog_and_filters_human_name(monkeypatch) -> None:
    patch_token(monkeypatch)
    responses = [
        {
            "pageDetails": {
                "count": 2,
                "totalCount": 3,
                "prevPageUrl": None,
                "nextPageUrl": (
                    "https://provider.example/api/v2/account/components"
                    "?max=2&page=1"
                ),
            },
            "components": [
                {
                    "uid": "component-1",
                    "name": "Inventory - Read Only",
                    "description": "Collect inventory evidence",
                    "categoryCode": "Scripts",
                    "credentialsRequired": False,
                    "variables": [],
                },
                {
                    "uid": "component-2",
                    "name": "Diagnostics - Network Read Only",
                    "description": "Collect bounded network diagnostics",
                    "categoryCode": "Scripts",
                    "credentialsRequired": False,
                    "variables": [
                        {
                            "name": "IncludeRoutes",
                            "type": "Boolean",
                            "direction": True,
                            "description": "Include route table metadata",
                            "defaultVal": "sensitive-default-must-not-be-released",
                        }
                    ],
                },
            ],
        },
        {
            "pageDetails": {
                "count": 1,
                "totalCount": 3,
                "prevPageUrl": (
                    "https://provider.example/api/v2/account/components"
                    "?max=2&page=0"
                ),
                "nextPageUrl": None,
            },
            "components": [
                {
                    "uid": "component-3",
                    "name": "Diagnostics - Service Read Only",
                    "description": "Collect service state",
                    "categoryCode": "Scripts",
                    "credentialsRequired": False,
                    "variables": [],
                }
            ],
        },
        {
            "pageDetails": {
                "count": 0,
                "totalCount": 3,
                "prevPageUrl": (
                    "https://provider.example/api/v2/account/components"
                    "?max=2&page=1"
                ),
                "nextPageUrl": None,
            },
            "components": [],
        },
    ]
    audit = Audit()
    transport = Transport(responses)
    connector = DattoRmmAutomationReadConnector(
        secrets=Secrets(),
        transport=transport,
        audit=audit,
    )

    result = connector.execute(
        request(
            capability="datto_rmm.component.search",
            arguments={"name": "diagnostics", "max": 2},
        )
    )

    assert [call["method"] for call in transport.calls] == ["GET", "GET", "GET"]
    assert all(
        call["url"].endswith("/api/v2/account/components")
        for call in transport.calls
    )
    assert [call["params"]["page"] for call in transport.calls] == [0, 1, 2]
    assert [call["params"]["max"] for call in transport.calls] == [2, 2, 2]
    assert result.data["discovery_complete"] is True
    assert result.data["match_count"] == 2
    assert [match["name"] for match in result.data["resource_matches"]] == [
        "Diagnostics - Network Read Only",
        "Diagnostics - Service Read Only",
    ]
    assert result.data["resource_matches"][0]["resource_id"] == "component-2"
    assert result.data["resource_matches"][0]["variables"] == [
        {
            "name": "IncludeRoutes",
            "type": "Boolean",
            "description": "Include route table metadata",
            "direction": True,
        }
    ]
    assert "defaultVal" not in str(result.data)
    adaptation = [
        details
        for event_type, details in audit.events
        if event_type == "connector.adaptation_observed"
    ]
    assert len(adaptation) == 1
    assert adaptation[0]["pages_aggregated"] == 3
    assert adaptation[0]["final_count"] == 3
    assert adaptation[0]["complete"] is True


def test_component_search_rejects_later_start_page() -> None:
    connector = DattoRmmAutomationReadConnector(
        secrets=Secrets(),
        transport=Transport([]),
        audit=Audit(),
    )

    with pytest.raises(ValueError, match="must begin at provider page 0"):
        connector.execute(
            request(
                capability="datto_rmm.component.search",
                arguments={"page": 1},
            )
        )


def test_component_search_fails_closed_without_component_collection(monkeypatch) -> None:
    patch_token(monkeypatch)
    connector = DattoRmmAutomationReadConnector(
        secrets=Secrets(),
        transport=Transport([{"pageDetails": {"count": 0, "totalCount": 0}}]),
        audit=Audit(),
    )

    with pytest.raises(ValueError, match="components collection"):
        connector.execute(
            request(
                capability="datto_rmm.component.search",
                arguments={},
            )
        )


def test_component_search_fails_closed_when_provider_identity_is_missing(monkeypatch) -> None:
    patch_token(monkeypatch)
    connector = DattoRmmAutomationReadConnector(
        secrets=Secrets(),
        transport=Transport(
            [
                {
                    "pageDetails": {
                        "count": 1,
                        "totalCount": 1,
                        "prevPageUrl": None,
                        "nextPageUrl": None,
                    },
                    "components": [{"name": "Unaddressable Component"}],
                }
            ]
        ),
        audit=Audit(),
    )

    with pytest.raises(ValueError, match="lacks durable uid"):
        connector.execute(
            request(
                capability="datto_rmm.component.search",
                arguments={},
            )
        )


def test_job_read_uses_exact_get_and_returns_bounded_status(monkeypatch) -> None:
    patch_token(monkeypatch)
    transport = Transport(
        [
            {
                "id": 123,
                "uid": "job-uid-1",
                "name": "API Quick Job",
                "status": "active",
                "dateCreated": "2026-09-14T16:00:00Z",
                "unexpectedProviderField": "must-not-be-released",
            }
        ]
    )
    connector = DattoRmmAutomationReadConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(
        request(
            capability="datto_rmm.job.read",
            arguments={"resource_id": "job-uid-1"},
        )
    )

    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["url"].endswith("/api/v2/job/job-uid-1")
    assert transport.calls[0]["params"] == {}
    assert result.data == {
        "job": {
            "resource_id": "job-uid-1",
            "status": "active",
            "name": "API Quick Job",
            "date_created": "2026-09-14T16:00:00Z",
        },
        "discovery_complete": True,
    }


def test_job_read_requires_durable_identity() -> None:
    with pytest.raises(ValueError, match="job_uid or resource_id is required"):
        DattoRmmAutomationReadConnector._resolve_operation(
            "datto_rmm.job.read",
            {},
        )


def test_job_read_fails_closed_on_identity_mismatch(monkeypatch) -> None:
    patch_token(monkeypatch)
    connector = DattoRmmAutomationReadConnector(
        secrets=Secrets(),
        transport=Transport(
            [
                {
                    "uid": "different-job",
                    "status": "completed",
                }
            ]
        ),
        audit=Audit(),
    )

    with pytest.raises(ValueError, match="identity does not match"):
        connector.execute(
            request(
                capability="datto_rmm.job.read",
                arguments={"job_uid": "expected-job"},
            )
        )


def test_automation_read_connector_exposes_no_write_capability() -> None:
    assert DattoRmmAutomationReadConnector.capabilities == frozenset(
        {
            "datto_rmm.component.search",
            "datto_rmm.job.read",
            "datto_rmm.job.output.read",
        }
    )
    assert all(
        not capability.endswith(".run")
        and "execute" not in capability
        for capability in DattoRmmAutomationReadConnector.capabilities
    )