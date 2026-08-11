from __future__ import annotations

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.datto_rmm.auth import DattoRmmAccessToken
from connectors.datto_rmm.connector import DattoRmmConnector
import pytest


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

    def request(self, *, method, url, headers, params=None, json=None, timeout_seconds=30.0):
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


def connector_request(*, arguments, capability="datto_rmm.device.search"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-1",
            principal_id="person-1",
            organization_id="aot",
            client_id=None,
            capability=capability,
            mode="observe",
        ),
        arguments=arguments,
    )


def test_device_search_translates_hostname_without_collapsing_ambiguity() -> None:
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.search",
        {
            "hostname": "AOT-50282",
            "requested_facts": ["last user logged in"],
        },
    )

    assert path == "/api/v2/account/devices"
    assert params == {
        "page": 1,
        "max": 25,
        "hostname": "AOT-50282",
    }


def test_device_search_never_allows_single_result_discovery() -> None:
    _, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.search",
        {"hostname": "SERVER", "max": 1},
    )

    assert params is not None
    assert params["max"] == 2


def test_device_search_accepts_provider_neutral_name_and_site_selectors() -> None:
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.search",
        {
            "name": "SERVER",
            "site": "Customer-B",
            "page": 2,
            "max": 25,
        },
    )

    assert path == "/api/v2/account/devices"
    assert params == {
        "page": 2,
        "max": 25,
        "hostname": "SERVER",
        "siteName": "Customer-B",
    }


def test_device_search_does_not_forward_reasoning_only_arguments() -> None:
    _, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.search",
        {
            "hostname": "AOT-50282",
            "requested_facts": ["last user logged in"],
            "provider": "must-not-cross-provider-boundary",
        },
    )

    assert params is not None
    assert set(params) == {"page", "max", "hostname"}


def test_device_search_normalizes_provider_records_to_canonical_resource_matches() -> None:
    payload = {
        "devices": [
            {
                "uid": "device-uid-1",
                "hostname": "SERVER",
                "siteName": "Customer-A",
                "siteUid": "site-uid-a",
                "lastUser": "CUSTOMERA\\user.one",
            },
            {
                "uid": "device-uid-2",
                "hostname": "SERVER",
                "siteName": "Customer-B",
                "siteUid": "site-uid-b",
                "lastUser": "CUSTOMERB\\user.two",
            },
        ]
    }

    normalized = DattoRmmConnector._normalize_result(
        "datto_rmm.device.search",
        payload,
    )

    assert normalized == {
        "resource_matches": [
            {
                "resource_id": "device-uid-1",
                "hostname": "SERVER",
                "site": "Customer-A",
                "site_id": "site-uid-a",
            },
            {
                "resource_id": "device-uid-2",
                "hostname": "SERVER",
                "site": "Customer-B",
                "site_id": "site-uid-b",
            },
        ],
        "provider_data": payload,
    }


def test_device_search_normalization_fails_closed_without_device_collection() -> None:
    with pytest.raises(ValueError, match="devices collection"):
        DattoRmmConnector._normalize_result(
            "datto_rmm.device.search",
            {"unexpected": []},
        )


def test_hostname_reference_matches_only_delimited_identifier_segment() -> None:
    assert DattoRmmConnector._hostname_reference_matches(
        reference="50282",
        hostname="AOT-50282",
    )
    assert DattoRmmConnector._hostname_reference_matches(
        reference="50282",
        hostname="CUSTOMER-50282-SRV",
    )
    assert not DattoRmmConnector._hostname_reference_matches(
        reference="50282",
        hostname="AOT-150282",
    )


def test_pure_device_discovery_does_not_issue_exact_read(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )
    search_payload = {
        "devices": [
            {
                "uid": "device-uid-1",
                "hostname": "SERVER",
                "siteName": "Customer-A",
            }
        ]
    }
    transport = Transport([search_payload])
    connector = DattoRmmConnector(secrets=Secrets(), transport=transport, audit=Audit())

    result = connector.execute(
        connector_request(arguments={"hostname": "SERVER"})
    )

    assert len(transport.calls) == 1
    assert transport.calls[0]["url"].endswith("/api/v2/account/devices")
    assert result.data["provider_data"] == search_payload
    assert result.data["resource_matches"][0]["resource_id"] == "device-uid-1"


def test_fact_bearing_search_resolves_unique_match_to_exact_device_read(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )
    search_payload = {
        "devices": [
            {
                "uid": "device-uid-1",
                "hostname": "SERVER",
                "siteName": "Customer-A",
                "lastUser": "SUMMARY\\must-not-be-used",
            }
        ]
    }
    exact_payload = {
        "uid": "device-uid-1",
        "hostname": "SERVER",
        "siteName": "Customer-A",
        "lastUser": "CUSTOMERA\\exact.user",
    }
    audit = Audit()
    transport = Transport([search_payload, exact_payload])
    connector = DattoRmmConnector(secrets=Secrets(), transport=transport, audit=audit)

    result = connector.execute(
        connector_request(
            arguments={
                "hostname": "SERVER",
                "requested_facts": ("last user",),
            }
        )
    )

    assert len(transport.calls) == 2
    assert transport.calls[0]["url"].endswith("/api/v2/account/devices")
    assert transport.calls[1]["url"].endswith("/api/v2/device/device-uid-1")
    assert result.capability == "datto_rmm.device.search"
    assert result.data == {
        "resource_matches": [
            {
                "resource_id": "device-uid-1",
                "hostname": "SERVER",
                "site": "Customer-A",
            }
        ],
        "resolved_resource_id": "device-uid-1",
        "provider_data": exact_payload,
    }
    assert [event[0] for event in audit.events] == [
        "connector.requested",
        "connector.completed",
        "connector.requested",
        "connector.completed",
    ]


def test_fact_bearing_fragment_search_falls_back_without_inventing_hostname(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )
    exact_search_payload = {"devices": []}
    account_discovery_payload = {
        "devices": [
            {
                "uid": "device-uid-50282",
                "hostname": "AOT-50282",
                "siteName": "Customer-A",
            },
            {
                "uid": "device-uid-other",
                "hostname": "OTHER-10001",
                "siteName": "Customer-B",
            },
        ]
    }
    exact_payload = {
        "uid": "device-uid-50282",
        "hostname": "AOT-50282",
        "siteName": "Customer-A",
        "lastUser": "CUSTOMERA\\verified.user",
    }
    transport = Transport([exact_search_payload, account_discovery_payload, exact_payload])
    connector = DattoRmmConnector(secrets=Secrets(), transport=transport, audit=Audit())

    result = connector.execute(
        connector_request(
            arguments={
                "hostname": "50282",
                "requested_facts": ("last user",),
            }
        )
    )

    assert len(transport.calls) == 3
    assert transport.calls[0]["params"]["hostname"] == "50282"
    assert "hostname" not in transport.calls[1]["params"]
    assert transport.calls[1]["params"] == {"page": 1, "max": 250}
    assert transport.calls[2]["url"].endswith("/api/v2/device/device-uid-50282")
    assert result.data["resolved_resource_id"] == "device-uid-50282"
    assert result.data["resource_matches"] == [
        {
            "resource_id": "device-uid-50282",
            "hostname": "AOT-50282",
            "site": "Customer-A",
        }
    ]
    assert result.data["provider_data"] == exact_payload


def test_fact_bearing_fragment_search_preserves_ambiguity_across_sites(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )
    exact_search_payload = {"devices": []}
    account_discovery_payload = {
        "devices": [
            {"uid": "device-uid-a", "hostname": "AOT-50282", "siteName": "Customer-A"},
            {"uid": "device-uid-b", "hostname": "LAB-50282", "siteName": "Customer-B"},
        ]
    }
    transport = Transport([exact_search_payload, account_discovery_payload])
    connector = DattoRmmConnector(secrets=Secrets(), transport=transport, audit=Audit())

    result = connector.execute(
        connector_request(
            arguments={
                "hostname": "50282",
                "requested_facts": ("last user",),
            }
        )
    )

    assert len(transport.calls) == 2
    assert [match["resource_id"] for match in result.data["resource_matches"]] == [
        "device-uid-a",
        "device-uid-b",
    ]
    assert result.data["discovery_complete"] is True
    assert "resolved_resource_id" not in result.data


def test_fact_bearing_search_stops_on_ambiguous_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )
    search_payload = {
        "devices": [
            {"uid": "device-uid-1", "hostname": "SERVER", "siteName": "Customer-A"},
            {"uid": "device-uid-2", "hostname": "SERVER", "siteName": "Customer-B"},
        ]
    }
    transport = Transport([search_payload])
    connector = DattoRmmConnector(secrets=Secrets(), transport=transport, audit=Audit())

    result = connector.execute(
        connector_request(
            arguments={
                "hostname": "SERVER",
                "requested_facts": ("last user",),
            }
        )
    )

    assert len(transport.calls) == 1
    assert len(result.data["resource_matches"]) == 2
    assert result.data["provider_data"] == search_payload
    assert "resolved_resource_id" not in result.data


def test_device_read_uses_resource_id_as_durable_device_uid() -> None:
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.get",
        {"resource_id": "device-uid-123"},
    )

    assert path == "/api/v2/device/device-uid-123"
    assert params is None


def test_device_read_requires_durable_identifier() -> None:
    with pytest.raises(ValueError, match="device_uid or resource_id is required"):
        DattoRmmConnector._resolve_operation("datto_rmm.device.get", {})
