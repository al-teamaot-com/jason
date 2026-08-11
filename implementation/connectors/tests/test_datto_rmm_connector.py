from __future__ import annotations

import pytest

from connectors.datto_rmm.connector import DattoRmmConnector


def test_device_search_translates_hostname_to_datto_hostname_filter() -> None:
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
        "max": 1,
        "hostname": "AOT-50282",
    }


def test_device_search_accepts_provider_neutral_name_selector() -> None:
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.search",
        {
            "name": "AOT-50282",
            "page": 2,
            "max": 25,
        },
    )

    assert path == "/api/v2/account/devices"
    assert params == {
        "page": 2,
        "max": 25,
        "hostname": "AOT-50282",
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
