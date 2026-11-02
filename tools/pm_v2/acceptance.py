from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AcceptanceMatrixError(ValueError):
    pass


def inspect_acceptance_matrix(*, repo: Path, matrix_path: Path) -> dict[str, Any]:
    value = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise AcceptanceMatrixError("unsupported PM V2 acceptance matrix")
    rows = value.get("requirements")
    if not isinstance(rows, list) or not rows:
        raise AcceptanceMatrixError("PM V2 acceptance matrix has no requirements")
    seen = set()
    source_ready = []
    external = []
    for row in rows:
        if not isinstance(row, dict):
            raise AcceptanceMatrixError("acceptance requirement must be an object")
        rid = str(row.get("id") or "")
        if not rid or rid in seen:
            raise AcceptanceMatrixError("acceptance IDs must be unique")
        seen.add(rid)
        evidence = row.get("source_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise AcceptanceMatrixError(f"{rid} lacks source evidence")
        for reference in evidence:
            if not isinstance(reference, str) or ":" not in reference:
                raise AcceptanceMatrixError(f"{rid} has invalid source evidence")
            filename, symbol = reference.split(":", 1)
            path = repo / filename
            if not path.is_file():
                raise AcceptanceMatrixError(f"{rid} source evidence file is missing")
            if symbol not in path.read_text(encoding="utf-8"):
                raise AcceptanceMatrixError(
                    f"{rid} source evidence symbol {symbol} is missing"
                )
        source_ready.append(rid)
        acceptance = str(row.get("external_acceptance") or "").strip()
        if not acceptance:
            raise AcceptanceMatrixError(f"{rid} lacks external acceptance criterion")
        external.append({"id": rid, "criterion": acceptance})
    total = len(rows)
    return {
        "schema_version": "1.0",
        "requirement_count": total,
        "source_implemented_count": len(source_ready),
        "source_implementation_percent": round(100 * len(source_ready) / total, 1),
        "source_ready_ids": source_ready,
        "external_acceptance_criteria": external,
        "note": (
            "Source implementation coverage is not end-to-end acceptance. "
            "External criteria remain pending until independently evidenced."
        ),
    }
