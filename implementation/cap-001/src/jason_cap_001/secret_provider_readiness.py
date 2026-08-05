from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


class DeploymentReadinessError(RuntimeError):
    """Raised when a provider deployment record is missing or blocked."""


@dataclass(frozen=True, slots=True)
class DeploymentReadinessResult:
    record_path: Path
    ready: bool
    blocking_fields: tuple[str, ...]


_BLOCKING_MARKERS = ("UNVERIFIED", "NOT IMPLEMENTED", "BLOCKING")
_TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")


def evaluate_deployment_record(record_path: Path) -> DeploymentReadinessResult:
    path = record_path.expanduser().resolve()
    if not path.is_file():
        raise DeploymentReadinessError(
            f"Secret provider deployment record was not found: {path}"
        )

    blocking: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _TABLE_ROW.match(line.strip())
        if not match:
            continue
        field, value, status = (part.strip() for part in match.groups())
        if field.lower() in {"field", "logical name"}:
            continue
        combined = f"{value} {status}".upper()
        if any(marker in combined for marker in _BLOCKING_MARKERS):
            blocking.append(field)

    return DeploymentReadinessResult(
        record_path=path,
        ready=not blocking,
        blocking_fields=tuple(dict.fromkeys(blocking)),
    )


def require_deployment_ready(record_path: Path) -> DeploymentReadinessResult:
    result = evaluate_deployment_record(record_path)
    if not result.ready:
        fields = ", ".join(result.blocking_fields)
        raise DeploymentReadinessError(
            "Secret provider deployment is not ready. Blocking deployment-record "
            f"fields: {fields}. Update {result.record_path} with verified values."
        )
    return result
