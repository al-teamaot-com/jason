"""Full-fleet KFS report projection never silently truncates after 100 devices."""
from __future__ import annotations

import pytest

from jason_mcp import server


def _output(count: int):
    return {
        "provider": "kyocera_kfs",
        "provider_capability": "print.fleet.usage.rank",
        "data": {
            "report_mode": "list",
            "inventory_coverage_verified": True,
            "selected_device_count": count,
            "returned_row_count": count,
            "listed_devices": [
                {
                    "device_id": f"device-{n}",
                    "serial_number": f"SERIAL-{n}",
                    "total_impressions": n,
                    "api_key": "must-not-leak",
                }
                for n in range(count)
            ],
            "ranked_devices": [],
            "exceptions": [
                {"serial_number": f"SERIAL-{n}", "warnings": ["No meter"]}
                for n in range(105)
            ],
        },
        "warnings": [],
    }


def test_projected_complete_fleet_preserves_435_and_all_exceptions():
    r = server._project_print_fleet_usage_report(_output(435))
    data = r["data"]
    assert data["inventory_coverage_verified"]
    assert data["returned_row_count"] == 435
    assert len(data["listed_devices"]) == 435
    assert data["listed_devices"][-1]["serial_number"] == "SERIAL-434"
    assert data["listed_devices"][0]["api_key"] == "[redacted]"
    assert len(data["exceptions"]) == 105


def test_fleet_projection_rejects_out_of_contract_collection_size():
    with pytest.raises(ValueError, match="source bounds"):
        server._project_print_fleet_usage_report(_output(1001))


def test_execute_read_mcp_returns_complete_fleet_without_second_truncation(monkeypatch):
    projected = server._project_print_fleet_usage_report(_output(435))
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda name: True)
    monkeypatch.setattr(
        server, "_governed_read",
        lambda **kwargs: {
            "status": "succeeded",
            "stage": "completed",
            "capability": "print.fleet.usage.rank",
            "provider": "kyocera_kfs",
            "reason_codes": ["capability_completed"],
            "error_code": None,
            "correlation_id": "corr-test",
            "evidence": projected,
        },
    )
    result = server.execute_read_capability(
        capability="print.fleet.usage.rank",
        arguments={"month": "2026-10", "report_mode": "list"},
    )
    records = result["evidence"]["data"]["listed_devices"]
    assert len(records) == 435
    assert records[-1]["serial_number"] == "SERIAL-434"
    assert records[0]["api_key"] == "[redacted]"
