from __future__ import annotations

import pytest

from connectors.datto_rmm.connector import DattoRmmConnector


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
