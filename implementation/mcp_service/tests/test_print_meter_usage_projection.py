from __future__ import annotations

from jason_mcp import server


def _output(count: int):
    return {
        "provider": "kyocera_kfs",
        "provider_capability": "print.meter.usage.search",
        "data": {
            "record_count": count,
            "fleet_devices_in_inventory": count,
            "selected_device_count": count,
            "records": [
                {
                    "device_id": f"device-{index}",
                    "serial_number": f"SERIAL-{index}",
                    "total_impressions": index,
                    "api_key": "must-not-leak",
                }
                for index in range(count)
            ],
        },
        "warnings": [],
    }


def test_print_usage_projection_preserves_full_governed_fleet_over_100():
    result = server._project_print_meter_usage_search(_output(436))
    records = result["data"]["records"]
    assert len(records) == 436
    assert result["data"]["record_count"] == 436
    assert result["data"]["selected_device_count"] == 436
    assert records[435]["serial_number"] == "SERIAL-435"
    assert records[0]["api_key"] == "[redacted]"
    assert "records_bounded" not in result["data"]


def test_print_usage_projection_remains_bounded_to_source_contract():
    result = server._project_print_meter_usage_search(_output(1005))
    assert len(result["data"]["records"]) == 1000
    assert result["data"]["records_bounded"] is True
    assert result["data"]["records_available"] == 1005


def test_generic_safe_projection_still_bounds_unrelated_lists_to_100():
    projected = server._safe({"items": list(range(150))})
    assert len(projected["items"]) == 101
    assert projected["items"][-1] == "[collection-bounded]"


def test_execute_read_capability_preserves_projected_full_fleet(monkeypatch):
    evidence = server._project_print_meter_usage_search(_output(436))

    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda name: True)
    monkeypatch.setattr(
        server,
        "_governed_read",
        lambda **kwargs: {
            "status": "succeeded",
            "stage": "completed",
            "capability": "print.meter.usage.search",
            "provider": "kyocera_kfs",
            "reason_codes": [],
            "error_code": None,
            "correlation_id": "corr-test",
            "evidence": evidence,
        },
    )

    result = server.execute_read_capability(
        capability="print.meter.usage.search",
        arguments={"limit": 1000},
    )

    records = result["evidence"]["data"]["records"]
    assert len(records) == 436
    assert records[-1]["serial_number"] == "SERIAL-435"
    assert records[0]["api_key"] == "[redacted]"


def test_execute_read_capability_still_rebounds_unrelated_dynamic_lists(monkeypatch):
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda name: True)
    monkeypatch.setattr(
        server,
        "_governed_read",
        lambda **kwargs: {
            "status": "succeeded",
            "stage": "completed",
            "capability": "example.dynamic.search",
            "provider": "example",
            "reason_codes": [],
            "error_code": None,
            "correlation_id": "corr-test",
            "evidence": {"data": {"records": list(range(150))}},
        },
    )

    result = server.execute_read_capability(
        capability="example.dynamic.search",
        arguments={},
    )
    assert len(result["evidence"]["data"]["records"]) == 100
