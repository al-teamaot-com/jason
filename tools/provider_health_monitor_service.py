#!/usr/bin/env python3
"""Independent provider-health aggregator.

Consumes sanitized provider probe receipts produced by provider-specific read-only
checks. It performs no provider writes and has no PMV3 dependency.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from isolated_service_common import atomic_json, load_json, now_iso
except ModuleNotFoundError:
    from tools.isolated_service_common import atomic_json, load_json, now_iso

HEALTHY = {"ok", "healthy", "pass", "passed", "succeeded", "available"}
DEGRADED = {"degraded", "warning", "partial"}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def evaluate(receipts: Iterable[dict[str, Any]], *, max_age_seconds: int = 900, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    providers: list[dict[str, Any]] = []
    overall = "healthy"
    for receipt in receipts:
        name = str(receipt.get("provider") or "").strip()
        status = str(receipt.get("status") or "unknown").lower()
        observed = str(receipt.get("observed_at") or "")
        if not name or not observed:
            normalized = "unknown"
            age = None
        else:
            try:
                age = max(0, int((current - _parse_time(observed)).total_seconds()))
            except ValueError:
                age = None
            if age is None or age > max_age_seconds:
                normalized = "stale"
            elif status in HEALTHY:
                normalized = "healthy"
            elif status in DEGRADED:
                normalized = "degraded"
            else:
                normalized = "unhealthy"
        if normalized in {"unhealthy", "unknown"}:
            overall = "unhealthy"
        elif normalized in {"degraded", "stale"} and overall == "healthy":
            overall = "degraded"
        providers.append({
            "provider": name or "unknown",
            "health": normalized,
            "source_status": status,
            "age_seconds": age,
            "source": str(receipt.get("source") or ""),
        })
    return {"status": overall, "providers": providers}


def run(inputs: list[Path], output: Path, max_age_seconds: int = 900) -> dict[str, Any]:
    receipts = [load_json(path) for path in inputs]
    result = {
        "schema_version": "1.0",
        "service": "provider_health_monitor",
        "observed_at": now_iso(),
        "max_age_seconds": max_age_seconds,
        **evaluate(receipts, max_age_seconds=max_age_seconds),
    }
    atomic_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-age-seconds", type=int, default=900)
    args = parser.parse_args()
    result = run(args.input, args.output, args.max_age_seconds)
    print(result["status"])
    return 0 if result["status"] == "healthy" else 2


if __name__ == "__main__":
    raise SystemExit(main())
