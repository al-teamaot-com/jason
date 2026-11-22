"""Deterministic, governed KFS ranking and complete period fleet listing.

Consumes existing authorized usage records; does not query providers, infer missing
meter counts or customer names, grant authority, export files, or change billing.
"""
from __future__ import annotations

from typing import Any, Mapping

_METRICS = {
    "total": "total_impressions",
    "black_white": "black_white_impressions",
    "color": "color_impressions",
}
_MODES = frozenset({"rank", "list"})


def _fleet_record(item: Mapping[str, Any], *, metric: str, valid: bool) -> dict[str, Any]:
    mapping_verified = item.get("customer_mapping_status") == "verified"
    result = {
        "device_id": str(item["device_id"]),
        "serial_number": str(item.get("serial_number") or ""),
        "equipment_id": str(item.get("equipment_id") or ""),
        "model_name": str(item.get("model_name") or ""),
        "customer_name": str(item.get("customer_name") or "") if mapping_verified else "",
        "customer_mapping_status": item.get("customer_mapping_status") or "not_found",
        "customer_mapping_source": item.get("customer_mapping_source") or "none",
        "management_status": item.get("management_status"),
        "usage_status": "verified" if valid else "exception",
        "total_impressions": item.get("total_impressions") if valid else None,
        "black_white_impressions": item.get("black_white_impressions") if valid else None,
        "color_impressions": item.get("color_impressions") if valid else None,
        "metric_value": item.get(_METRICS[metric]) if valid else None,
        "boundary_start_at": item.get("boundary_start_at"),
        "boundary_end_at": item.get("boundary_end_at"),
        "exception_reasons": [] if valid else list(item.get("warnings") or ())[:24],
    }
    if not valid and not result["exception_reasons"]:
        result["exception_reasons"] = ["Usage evidence did not reconcile"]
    return result


def rank_fleet_usage(
    source: Mapping[str, Any], *, metric: str = "total",
    top_n: int = 5, report_mode: str = "rank", managed_only: bool = True,
) -> dict[str, Any]:
    if metric not in _METRICS:
        raise ValueError("metric must be total, black_white, or color")
    if report_mode not in _MODES:
        raise ValueError("report_mode must be rank or list")
    if type(top_n) is not int or not 1 <= top_n <= 50:
        raise ValueError("top_n must be an integer between 1 and 50")
    if type(managed_only) is not bool:
        raise ValueError("managed_only must be a Boolean")

    records = source.get("records")
    if not isinstance(records, list):
        raise ValueError("governed usage source has no records")
    expected = source.get("selected_device_count")
    if (
        not source.get("inventory_coverage_verified")
        or type(expected) is not int
        or expected < 0 or expected > 1000
        or len(records) != expected
        or any("truncat" in str(w).casefold() for w in source.get("warnings", ()))
    ):
        raise ValueError("fleet inventory coverage is incomplete; report refused")

    seen: set[str] = set()
    verified: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    complete: list[dict[str, Any]] = []
    missing_customers = 0
    excluded_unmanaged = 0
    for item in records:
        if not isinstance(item, Mapping):
            raise ValueError("invalid governed device record")
        device_id = str(item.get("device_id") or "").strip()
        if not device_id or device_id in seen:
            raise ValueError("fleet device identifiers are missing or duplicated")
        seen.add(device_id)
        management_status = item.get("management_status")
        if type(management_status) is not int:
            raise ValueError("KFS management_status is unavailable; billing-safe listing refused")
        if managed_only and management_status != 1:
            excluded_unmanaged += 1
            continue
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
            and type(value) is int and value >= 0
        )
        row = _fleet_record(item, metric=metric, valid=valid)
        complete.append(row)
        if valid:
            verified.append(row)
        else:
            exceptions.append({
                "device_id": device_id,
                "serial_number": row["serial_number"],
                "warnings": row["exception_reasons"],
            })

    field = _METRICS[metric]
    verified.sort(key=lambda row: (-row[field], row["serial_number"], row["device_id"]))
    ranked: list[dict[str, Any]] = []
    if report_mode == "rank":
        for position, item in enumerate(verified[:top_n], 1):
            ranked.append({"rank": position, **item})

    output = {
        "period_start": source.get("period_start"),
        "period_end": source.get("period_end"),
        "report_mode": report_mode,
        "metric": metric,
        "fleet_devices_reported": source.get("fleet_devices_reported"),
        "fleet_devices_in_inventory": source.get("fleet_devices_in_inventory"),
        "full_inventory_device_count": expected,
        "selected_device_count": len(complete),
        "managed_only": managed_only,
        "unmanaged_excluded_count": excluded_unmanaged,
        "inventory_coverage_verified": True,
        "usage_verified_count": len(verified),
        "usage_exception_count": len(exceptions),
        "customer_mapping_missing_count": missing_customers,
        "exceptions": exceptions,
        "ranked_devices": ranked,
        "inventory_run_id": next(
            (item.get("inventory_run_id") for item in records if item.get("inventory_run_id")), ""
        ),
    }
    if report_mode == "list":
        # Return every selected managed device exactly once, including
        # missing-boundary devices; never count unmanaged as billable.
        complete.sort(key=lambda row: (
            (row["customer_name"] or "").casefold(),
            row["serial_number"], row["device_id"],
        ))
        output["listed_devices"] = complete
        output["returned_row_count"] = len(complete)
    return output
