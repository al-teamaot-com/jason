from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FailureCorpusError(ValueError):
    pass


def validate_failure_corpus(*, repo: Path, path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise FailureCorpusError("unsupported V1 failure corpus schema")
    failures = value.get("failures")
    if not isinstance(failures, list) or not failures:
        raise FailureCorpusError("failure corpus must contain failures")

    seen: set[str] = set()
    verified = []
    for entry in failures:
        if not isinstance(entry, dict):
            raise FailureCorpusError("failure entry must be an object")
        identifier = str(entry.get("id") or "")
        if not identifier or identifier in seen:
            raise FailureCorpusError("failure IDs must be non-empty and unique")
        seen.add(identifier)
        for field in ("symptom", "correction", "test_file", "test_symbol"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise FailureCorpusError(f"{identifier} missing {field}")
        test_path = repo / entry["test_file"]
        try:
            relative = test_path.resolve().relative_to(repo.resolve())
        except ValueError as exc:
            raise FailureCorpusError(f"{identifier} test path escapes repository") from exc
        if not test_path.is_file():
            raise FailureCorpusError(f"{identifier} test file is missing")
        source = test_path.read_text(encoding="utf-8")
        if entry["test_symbol"] not in source:
            raise FailureCorpusError(
                f"{identifier} test symbol is not present in {relative.as_posix()}"
            )
        verified.append(identifier)
    return {
        "status": "pass",
        "failure_count": len(verified),
        "verified_ids": sorted(verified),
    }
