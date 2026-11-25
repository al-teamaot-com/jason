"""KFS DeviceList remains truthfully paginated after safe MCP collection bounds."""
from __future__ import annotations

from jason_mcp import server


def _response(*, offset=0, count=100, matched=443, complete=True, next_offset=None):
    return {
        "status": "succeeded",
        "stage": "completed",
        "capability": "print.device.search",
        "provider": "kyocera_kfs",
        "reason_codes": ["capability_completed"],
        "error_code": None,
        "correlation_id": "corr-kfs-test",
        "evidence": {
            "provider": "kyocera_kfs",
            "provider_capability": "kyocera_kfs.device.search",
            "data": {
                "offset": offset,
                "limit": 1000,
                "matched_count": matched,
                "searched_count": matched,
                "complete": complete,
                "next_offset": next_offset,
                "devices": [
                    {
                        "deviceId": f"dev-{offset+n}",
                        "attributes": {
                            "serialNumber": f"SER{offset+n:06d}",
                            "managementStatus": 1 if n % 2 else 2,
                        },
                    }
                    for n in range(count)
                ],
            },
        },
    }


def test_bounded_first_page_does_not_claim_443_complete():
    projected = server._repair_kfs_device_projection_pagination(
        _response()["evidence"],
    )
    data = projected["data"]
    assert len(data["devices"]) == 100
    assert data["complete"] is False
    assert data["next_offset"] == 100
    assert data["projection_bounded"] is True
    assert data["returned_device_count"] == 100
    assert data["matched_count"] == 443


def test_bounded_middle_page_reports_correct_continuation():
    data = server._repair_kfs_device_projection_pagination(
        _response(offset=200)["evidence"],
    )["data"]
    assert data["next_offset"] == 300
    assert data["complete"] is False


def test_legitimate_last_page_stays_complete_without_fabrication():
    data = server._repair_kfs_device_projection_pagination(
        _response(offset=400, count=43)["evidence"],
    )["data"]
    assert data["complete"] is True
    assert data["next_offset"] is None
    assert data["matched_count"] == 443
    assert "projection_bounded" not in data


def test_proper_provider_page_is_not_rewritten():
    data = server._repair_kfs_device_projection_pagination(
        _response(complete=False, next_offset=100)["evidence"],
    )["data"]
    assert data["complete"] is False
    assert data["next_offset"] == 100
    assert "projection_bounded" not in data


def test_missing_coverage_metadata_does_not_invent_next_offset():
    original = _response()["evidence"]
    original["data"].pop("matched_count")
    projected = server._repair_kfs_device_projection_pagination(original)
    assert projected is original


def test_live_mcp_method_repairs_projection_without_adding_devices(monkeypatch):
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda name: True)
    monkeypatch.setattr(server, "_governed_read", lambda **kw: _response())
    result = server.execute_read_capability(
        capability="print.device.search",
        arguments={"limit": 1000, "offset": 0},
    )
    data = result["evidence"]["data"]
    assert result["status"] == "succeeded"
    assert len(data["devices"]) == 100
    assert data["complete"] is False
    assert data["next_offset"] == 100
    assert data["matched_count"] == 443
