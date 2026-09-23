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
        "page": 0,
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
    transport = Transport(
        [
            exact_search_payload,
            account_discovery_payload,
            {"devices": []},
            exact_payload,
        ]
    )
    connector = DattoRmmConnector(secrets=Secrets(), transport=transport, audit=Audit())

    result = connector.execute(
        connector_request(
            arguments={
                "hostname": "50282",
                "requested_facts": ("last user",),
            }
        )
    )

    assert len(transport.calls) == 4
    assert transport.calls[0]["params"]["hostname"] == "50282"
    assert "hostname" not in transport.calls[1]["params"]
    assert transport.calls[1]["params"] == {"page": 0, "max": 250}
    assert transport.calls[2]["params"] == {"page": 1, "max": 250}
    assert transport.calls[3]["url"].endswith("/api/v2/device/device-uid-50282")
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
    transport = Transport(
        [
            exact_search_payload,
            account_discovery_payload,
            {"devices": []},
        ]
    )
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

def test_read_surface_operations_translate_to_confirmed_get_endpoints() -> None:
    cases = (
        (
            "datto_rmm.device.alerts.open",
            {"resource_id": "dev-1"},
            "/api/v2/device/dev-1/alerts/open",
        ),
        (
            "datto_rmm.device.alerts.resolved",
            {"resource_id": "dev-1"},
            "/api/v2/device/dev-1/alerts/resolved",
        ),
        (
            "datto_rmm.device.audit.get",
            {"resource_id": "dev-1"},
            "/api/v2/audit/device/dev-1",
        ),
        (
            "datto_rmm.device.software.list",
            {"resource_id": "dev-1"},
            "/api/v2/audit/device/dev-1/software",
        ),
        (
            "datto_rmm.device.patches.list",
            {"resource_id": "dev-1"},
            "/api/v2/device/dev-1/patches",
        ),
        (
            "datto_rmm.account.alerts.open",
            {},
            "/api/v2/account/alerts/open",
        ),
        (
            "datto_rmm.site.search",
            {},
            "/api/v2/account/sites",
        ),
    )

    for capability, arguments, expected_path in cases:
        path, _ = DattoRmmConnector._resolve_operation(capability, arguments)
        assert path == expected_path


def test_device_scoped_read_surface_requires_durable_identity() -> None:
    for capability in (
        "datto_rmm.device.alerts.open",
        "datto_rmm.device.alerts.resolved",
        "datto_rmm.device.audit.get",
        "datto_rmm.device.software.list",
        "datto_rmm.device.patches.list",
    ):
        try:
            DattoRmmConnector._resolve_operation(capability, {})
        except ValueError as exc:
            assert "resource_id" in str(exc)
        else:
            raise AssertionError(f"{capability} accepted a missing resource identity")


def test_datto_connector_exposes_confirmed_read_surface() -> None:
    expected = {
        "datto_rmm.device.get",
        "datto_rmm.device.search",
        "datto_rmm.device.alerts.open",
        "datto_rmm.device.alerts.resolved",
        "datto_rmm.device.audit.get",
        "datto_rmm.device.software.list",
        "datto_rmm.device.patches.list",
        "datto_rmm.account.alerts.open",
        "datto_rmm.site.search",
    }
    assert expected <= DattoRmmConnector.capabilities

def test_device_scoped_read_capabilities_are_declared_for_generic_resolution() -> None:
    assert {
        "datto_rmm.device.alerts.open",
        "datto_rmm.device.alerts.resolved",
        "datto_rmm.device.audit.get",
        "datto_rmm.device.software.list",
        "datto_rmm.device.patches.list",
    } <= DattoRmmConnector.device_scoped_read_capabilities


def test_durable_device_identity_detection_accepts_provider_identity_only() -> None:
    assert DattoRmmConnector._durable_device_identity_present(
        {"resource_id": "dev-1"}
    )
    assert DattoRmmConnector._durable_device_identity_present(
        {"device_uid": "dev-1"}
    )
    assert not DattoRmmConnector._durable_device_identity_present(
        {"hostname": "AOT-50282"}
    )


def test_software_inventory_uses_bounded_default_page_size() -> None:
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.software.list",
        {"resource_id": "device-1"},
    )

    assert path == "/api/v2/audit/device/device-1/software"
    assert params["page"] == 1
    assert params["max"] == 50


def test_software_inventory_caps_requested_page_size() -> None:
    _, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.software.list",
        {
            "resource_id": "device-1",
            "max": 500,
        },
    )

    assert params["max"] == 50


def test_site_search_can_represent_provider_page_zero() -> None:
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.site.search",
        {
            "page": 0,
            "max": 25,
        },
    )

    assert path == "/api/v2/account/sites"
    assert params["page"] == 0
    assert params["max"] == 25


def test_user_identity_matching_normalizes_domain_spacing_and_case():
    assert DattoRmmConnector._user_identity_matches(
        reference="Lindsey Collins",
        provider_identity="AzureAD\\LindseyCollins",
    )
    assert DattoRmmConnector._user_identity_matches(
        reference="al davis",
        provider_identity="AZUREAD\\AlDavis",
    )
    assert not DattoRmmConnector._user_identity_matches(
        reference="Lindsey Collins",
        provider_identity="AzureAD\\LindseyCole",
    )


def test_fact_bearing_user_relationship_discovery_preserves_provider_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )
    account_payload = {
        "devices": [
            {
                "uid": "device-lindsey",
                "hostname": "AOT-50001",
                "siteName": "AOT",
                "lastUser": "AzureAD\\LindseyCollins",
            },
            {
                "uid": "device-other",
                "hostname": "AOT-50002",
                "siteName": "AOT",
                "lastUser": "AzureAD\\OtherUser",
            },
        ]
    }
    exact_payload = {
        "uid": "device-lindsey",
        "hostname": "AOT-50001",
        "siteName": "AOT",
        "lastUser": "AzureAD\\LindseyCollins",
    }
    transport = Transport([account_payload, {"devices": []}, exact_payload])
    connector = DattoRmmConnector(secrets=Secrets(), transport=transport, audit=Audit())
    result = connector.execute(
        connector_request(
            arguments={
                "user_identity": "Lindsey Collins",
                "requested_facts": ("hostname",),
            }
        )
    )
    assert len(transport.calls) == 3
    assert transport.calls[0]["params"]["page"] == 0
    assert transport.calls[1]["params"]["page"] == 1
    assert "hostname" not in transport.calls[0]["params"]
    assert result.data["resolved_resource_id"] == "device-lindsey"
    assert result.data["resource_matches"] == [
        {"resource_id": "device-lindsey", "hostname": "AOT-50001", "site": "AOT"}
    ]
    assert result.data["provider_data"] == exact_payload


def test_site_search_completes_provider_collection_by_default(monkeypatch) -> None:
    """A provider-capped 10/45 site response must not become false complete evidence."""

    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )

    total = 45
    responses = []

    for page in range(5):
        first_index = page * 10
        count = min(10, total - first_index)
        final_page = first_index + count >= total

        responses.append(
            {
                "pageDetails": {
                    "count": count,
                    "totalCount": total,
                    "nextPageUrl": (
                        None
                        if final_page
                        else (
                            "https://provider.example/api/v2/account/sites"
                            f"?max=10&page={page + 1}"
                        )
                    ),
                    "prevPageUrl": (
                        None
                        if page == 0
                        else (
                            "https://provider.example/api/v2/account/sites"
                            f"?max=10&page={page - 1}"
                        )
                    ),
                },
                "sites": [
                    {
                        "uid": f"site-{index}",
                        "name": f"Site {index}",
                    }
                    for index in range(
                        first_index + 1,
                        first_index + count + 1,
                    )
                ],
            }
        )

    audit = Audit()
    transport = Transport(responses)

    connector = DattoRmmConnector(
        secrets=Secrets(),
        transport=transport,
        audit=audit,
    )

    result = connector.execute(
        connector_request(
            arguments={},
            capability="datto_rmm.site.search",
        )
    )

    assert len(transport.calls) == 5

    assert [
        call["params"]["page"]
        for call in transport.calls
    ] == [0, 1, 2, 3, 4]

    assert len(result.data["sites"]) == 45
    assert result.data["pageDetails"]["count"] == 45
    assert result.data["pageDetails"]["totalCount"] == 45
    assert result.data["pageDetails"]["nextPageUrl"] is None
    assert result.data["discovery_complete"] is True

    adaptation_events = [
        details
        for event_type, details in audit.events
        if event_type == "connector.adaptation_observed"
    ]

    assert len(adaptation_events) == 1
    assert adaptation_events[0]["pages_aggregated"] == 5
    assert adaptation_events[0]["final_count"] == 45
    assert adaptation_events[0]["complete"] is True


def test_sosserver2024_exact_hostname_site_resolves_known_uid_beyond_page_two(
    monkeypatch,
) -> None:
    """Regression for the Star of the Sea production discovery failure."""

    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )

    target_uid = "52b4f1ad-d834-4c79-4955-8434101ccb7a"
    responses = [
        {"devices": []},
        {
            "devices": [
                {
                    "uid": "page-zero-device",
                    "hostname": "OTHER-0",
                    "siteName": "Other Site",
                }
            ]
        },
        {
            "devices": [
                {
                    "uid": "page-one-device",
                    "hostname": "OTHER-1",
                    "siteName": "Other Site",
                }
            ]
        },
        {
            "devices": [
                {
                    "uid": target_uid,
                    "hostname": "SOSServer2024",
                    "siteName": "Star of the Sea Catholic Church",
                    "siteUid": "star-of-the-sea",
                }
            ]
        },
        {"devices": []},
    ]

    transport = Transport(responses)
    connector = DattoRmmConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(
        connector_request(
            arguments={
                "hostname": "sosserver2024",
                "site": "Star of the Sea Catholic Church",
            }
        )
    )

    assert result.data["discovery_complete"] is True
    assert result.data["resolved_resource_id"] == target_uid
    assert result.data["resource_matches"] == [
        {
            "resource_id": target_uid,
            "hostname": "SOSServer2024",
            "site": "Star of the Sea Catholic Church",
            "site_id": "star-of-the-sea",
        }
    ]
    assert [
        call["params"]["page"]
        for call in transport.calls[1:]
    ] == [0, 1, 2, 3]


def test_hostname_discovery_continues_past_provider_page_two(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )

    transport = Transport(
        [
            {"devices": []},
            {"devices": [{"uid": "d0", "hostname": "OTHER-0"}]},
            {"devices": [{"uid": "d1", "hostname": "OTHER-1"}]},
            {"devices": [{"uid": "d2", "hostname": "OTHER-2"}]},
            {
                "devices": [
                    {
                        "uid": "target-beyond-two",
                        "hostname": "BEYOND-PAGE-TWO",
                        "siteName": "Customer-Z",
                    }
                ]
            },
            {"devices": []},
        ]
    )
    connector = DattoRmmConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(
        connector_request(
            arguments={"hostname": "BEYOND-PAGE-TWO"}
        )
    )

    assert result.data["discovery_complete"] is True
    assert result.data["resolved_resource_id"] == "target-beyond-two"
    assert [
        call["params"]["page"]
        for call in transport.calls[1:]
    ] == [0, 1, 2, 3, 4]


def test_genuine_not_found_requires_provider_exhaustion(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )

    transport = Transport(
        [
            {"devices": []},
            {"devices": [{"uid": "d0", "hostname": "OTHER-0"}]},
            {"devices": [{"uid": "d1", "hostname": "OTHER-1"}]},
            {"devices": []},
        ]
    )
    connector = DattoRmmConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(
        connector_request(arguments={"hostname": "DOES-NOT-EXIST"})
    )

    assert result.data["resource_matches"] == []
    assert result.data["discovery_complete"] is True
    assert "incomplete_reason" not in result.data


def test_incomplete_device_enumeration_never_becomes_definitive_not_found(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )

    transport = Transport(
        [
            {"devices": []},
            {"devices": [{"uid": "d0", "hostname": "OTHER-0"}]},
            {"devices": [{"uid": "d1", "hostname": "OTHER-1"}]},
        ]
    )
    connector = DattoRmmConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )
    connector.fallback_discovery_max_pages = 2

    result = connector.execute(
        connector_request(arguments={"hostname": "UNKNOWN-ENDPOINT"})
    )

    assert result.data["resource_matches"] == []
    assert result.data["discovery_complete"] is False
    assert result.data["incomplete_reason"] == "page_limit_reached"


def test_exact_hostname_matching_is_case_insensitive_and_preferred() -> None:
    matches = [
        {
            "resource_id": "exact",
            "hostname": "SOSServer2024",
            "site": "Star of the Sea Catholic Church",
        },
        {
            "resource_id": "fragment",
            "hostname": "LAB-SOSServer2024-OLD",
            "site": "Star of the Sea Catholic Church",
        },
    ]

    exact = DattoRmmConnector._exact_hostname_site_matches(
        matches=matches,
        hostname_reference="sosserver2024",
        site_reference="star of the sea catholic church",
    )

    assert [item["resource_id"] for item in exact] == ["exact"]


def test_site_disambiguates_identical_exact_hostnames(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )

    search_payload = {
        "devices": [
            {
                "uid": "site-a-device",
                "hostname": "SHARED-SERVER",
                "siteName": "Customer A",
            },
            {
                "uid": "site-b-device",
                "hostname": "shared-server",
                "siteName": "Customer B",
            },
        ]
    }
    transport = Transport([search_payload])
    connector = DattoRmmConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(
        connector_request(
            arguments={
                "hostname": "SHARED-SERVER",
                "site": "customer b",
            }
        )
    )

    assert result.data["resolved_resource_id"] == "site-b-device"
    assert result.data["resource_matches"] == [
        {
            "resource_id": "site-b-device",
            "hostname": "shared-server",
            "site": "Customer B",
        }
    ]

def test_site_only_device_search_enumerates_complete_account_before_filtering(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )
    responses = [
        {"devices":[{"uid":"atomic-1","hostname":"A1","siteName":"Atomic","siteUid":"atomic-site"},{"uid":"other-1","hostname":"O1","siteName":"Other","siteUid":"other-site"}]},
        {"devices":[{"uid":"atomic-2","hostname":"A2","siteName":"Atomic","siteUid":"atomic-site"}]},
        {"devices":[]},
    ]
    transport=Transport(responses)
    connector=DattoRmmConnector(secrets=Secrets(),transport=transport,audit=Audit())
    result=connector.execute(connector_request(arguments={"site":"Atomic"}))
    assert result.data["discovery_complete"] is True
    assert [x["resource_id"] for x in result.data["resource_matches"]] == ["atomic-1","atomic-2"]
    assert [c["params"]["page"] for c in transport.calls] == [0,1,2]
    assert all(c["params"]["max"] == connector.fallback_discovery_page_size for c in transport.calls)


def test_device_patch_read_uses_bounded_full_device_collection() -> None:
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.patches.list",
        {"resource_id": "device-1"},
    )

    assert path == "/api/v2/device/device-1/patches"
    assert params == {"page": 0, "max": 250}

    _, filtered = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.patches.list",
        {"resource_id": "device-1", "install_status": "approved pending"},
    )
    assert filtered["installStatus"] == "APPROVED_PENDING"


def test_device_patch_read_rejects_unknown_install_status() -> None:
    with pytest.raises(ValueError, match="install_status"):
        DattoRmmConnector._resolve_operation(
            "datto_rmm.device.patches.list",
            {"resource_id": "device-1", "install_status": "maybe"},
        )


def test_device_patch_filter_matches_exact_kb_and_preserves_ambiguity() -> None:
    payload = {
        "pageDetails": {"totalCount": 3, "count": 3, "nextPageUrl": None},
        "patches": [
            {"title": "2026-08 Security Update (KB5121003)", "installStatus": "APPROVED_PENDING"},
            {"title": "Different update", "kb": "5121004", "installStatus": "NOT_APPROVED"},
            {"title": "Duplicate metadata KB5121003", "installStatus": "INSTALLED"},
        ],
    }

    filtered = DattoRmmConnector._filter_device_patch_result(
        payload=payload,
        arguments={"kb": "KB5121003"},
    )

    assert filtered["match_count"] == 2
    assert filtered["exact_selector_match"] is False
    assert filtered["ambiguous"] is True
    assert len(filtered["patches"]) == 2

    single = DattoRmmConnector._filter_device_patch_result(
        payload={**payload, "patches": payload["patches"][:2]},
        arguments={"kb": "KB5121003"},
    )
    assert single["match_count"] == 1
    assert single["exact_selector_match"] is True
