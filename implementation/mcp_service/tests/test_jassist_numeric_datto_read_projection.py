"""The MCP read projection must bind both Datto UI ID and API UID."""
from jason_mcp.server import _project_endpoint_read


def test_numeric_datto_device_id_is_separate_from_native_resource_uid():
    ui_id = 1717088
    native_uid = "710e63d6-caca-d830-697a-81250b0a8321"
    result = _project_endpoint_read({
        "provider": "datto_rmm",
        "provider_capability": "datto_rmm.device.get",
        "data": {"id": ui_id, "uid": native_uid,
                 "hostname": "Al-Samsung",
                 "siteUid": "9bb56523-cade-4ffb-bc34-696e788f0f4c"},
    })
    record = result["record"]
    assert record["resource_id"] == native_uid
    assert record["provider_device_id"] == ui_id
    assert record["site_id"] == "9bb56523-cade-4ffb-bc34-696e788f0f4c"
    assert result["raw_provider_evidence_exposed"] is False


def test_projection_does_not_infer_numeric_id_from_uid():
    result = _project_endpoint_read({
        "provider": "datto_rmm",
        "provider_capability": "datto_rmm.device.get",
        "data": {"uid": "710e63d6-caca-d830-697a-81250b0a8321"},
    })
    assert "provider_device_id" not in result["record"]
