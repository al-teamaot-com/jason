#!/usr/bin/env python3
"""Independent immutable test/evidence index builder."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from isolated_service_common import atomic_json, load_json, now_iso, sha256_file
except ModuleNotFoundError:
    from tools.isolated_service_common import atomic_json, load_json, now_iso, sha256_file


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def collect(inputs: list[Path], output: Path, *, candidate_sha: str, max_age_seconds: int = 86400, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    reusable = True
    for path in inputs:
        payload = load_json(path)
        observed = str(payload.get("observed_at") or "")
        try:
            age = max(0, int((current - _parse(observed)).total_seconds()))
        except ValueError:
            age = None
        source_sha = str(payload.get("candidate_sha") or payload.get("source_sha") or "")
        status = str(payload.get("status") or "unknown").lower()
        valid = age is not None and age <= max_age_seconds and source_sha == candidate_sha and status in {"pass", "passed", "success", "succeeded", "healthy", "ok"}
        reusable = reusable and valid
        records.append({
            "path": str(path),
            "sha256": sha256_file(path),
            "status": status,
            "source_sha": source_sha,
            "age_seconds": age,
            "reusable": valid,
        })
    result = {
        "schema_version": "1.0",
        "service": "test_evidence_collection",
        "observed_at": now_iso(),
        "candidate_sha": candidate_sha,
        "max_age_seconds": max_age_seconds,
        "status": "reusable" if records and reusable else "refresh_required",
        "records": records,
    }
    atomic_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--max-age-seconds", type=int, default=86400)
    args = parser.parse_args()
    result = collect(args.input, args.output, candidate_sha=args.candidate_sha, max_age_seconds=args.max_age_seconds)
    print(result["status"])
    return 0 if result["status"] == "reusable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
