"""Deterministic, provider-neutral ranking of a complete governed KFS usage set.

This consumes existing KFS history facts; it never queries providers or grants authority.
"""
from __future__ import annotations

from typing import Any, Mapping

_METRICS = {
    "total": "total_impressions",
    "black_white": "black_white_impressions",
    "color": "color_impressions",
}


def rank_fleet_usage(source: Mapping[str, Any], *, metric: str = "total", top_n: int = 5) -> dict[str, Any]:
    if metric not in _METRICS:
        raise ValueError("metric must be total, black_white, or color")
    if type(top_n) is not int or not 1 <= top_n <= 50:
        raise ValueError("top_n must be an integer between 1 and 50")

    records = source.get("records")
    if not isinstance(records, list):
        raise ValueError("governed usage source has no records")
    expected = source.get("selected_device_count")
    if (
        not source.get("inventory_coverage_verified")
        or not isinstance(expected, int)
        or len(records) != expected
        or any("truncat" in str(w).casefold() for w in source.get("warnings", ()))
    ):
        raise ValueError("fleet inventory coverage is incomplete; ranking refused")

    seen: set[str] = set()
    verified: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    missing_customers = 0
    for item in records:
        if not isinstance(item, Mapping):
            raise ValueError("invalid governed device record")
        device_id = str(item.get("device_id") or "").strip()
        if not device_id or device_id in seen:
            raise ValueError("fleet device identifiers are missing or duplicated")
        seen.add(device_id)
        if item.get("customer_mapping_status") != "verified":
            missing_customers += 1
        value = item.get(_METRICS[metric])
        total = item.get("total_impressions")
        bw = item.get("black_white_impressions")
        color = item.get("color_impressions")
        valid = (
            item.get("usage_status") == "verified"
            and all(type(x) is int and x >= 0 for x in (total, bw, color))
            and bw + color == total
            and type(value) is int
            and value >= 0
        )
        if not valid:
            exceptions.append({
                "device_id": device_id,
                "serial_number": item.get("serial_number") or "",
                "warnings": list(item.get("warnings") or ()),
            })
            continue
        verified.append(dict(item))

    field = _METRICS[metric]
    verified.sort(key=lambda item: (-item[field], str(item.get("serial_number") or ""), item["device_id"]))
    ranked = []
    for position, item in enumerate(verified[:top_n], 1):
        ranked.append({
            "rank": position,
            "device_id": item["device_id"],
            "serial_number": item.get("serial_number") or "",
            "equipment_id": item.get("equipment_id") or "",
            "model_name": item.get("model_name") or "",
            "customer_name": item.get("customer_name") or "",
            "customer_mapping_status": item.get("customer_mapping_status") or "not_found",
            "black_white_impressions": item["black_white_impressions"],
            "color_impressions": item["color_impressions"],
            "total_impressions": item["total_impressions"],
            "metric_value": item[field],
            "boundary_start_at": item.get("boundary_start_at"),
            "boundary_end_at": item.get("boundary_end_at"),
        })
    return {
        "period_start": source.get("period_start"),
        "period_end": source.get("period_end"),
        "metric": metric,
        "fleet_devices_reported": source.get("fleet_devices_reported"),
        "fleet_devices_in_inventory": source.get("fleet_devices_in_inventory"),
        "selected_device_count": expected,
        "inventory_coverage_verified": True,
        "usage_verified_count": len(verified),
        "usage_exception_count": len(exceptions),
        "customer_mapping_missing_count": missing_customers,
        "exceptions": exceptions,
        "ranked_devices": ranked,
        "inventory_run_id": next((item.get("inventory_run_id") for item in records if item.get("inventory_run_id")), ""),
    }
