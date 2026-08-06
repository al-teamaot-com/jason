from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


class RecoveryReadinessError(RuntimeError):
    """Raised when stateful infrastructure lacks verified recovery evidence."""


@dataclass(frozen=True, slots=True)
class RecoveryReadinessResult:
    record_path: Path
    ready: bool
    blocking_fields: tuple[str, ...]


_BLOCKING_MARKERS = (
    "UNVERIFIED",
    "NOT IMPLEMENTED",
    "NOT TESTED",
    "BLOCKING",
    "MISSING",
    "UNKNOWN",
)
_TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")
_REQUIRED_FIELDS = (
    "Component",
    "Initialization status",
    "Seal or recovery method",
    "Share count",
    "Recovery threshold",
    "Custody assignments",
    "Protected custody reference",
    "Bootstrap credential disposition",
    "Operational owner",
    "Escalation contact",
    "Last successful recovery test",
    "Recovery evidence reference",
)


def evaluate_recovery_record(record_path: Path) -> RecoveryReadinessResult:
    path = record_path.expanduser().resolve()
    if not path.is_file():
        raise RecoveryReadinessError(
            f"Stateful infrastructure recovery record was not found: {path}"
        )

    rows: dict[str, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _TABLE_ROW.match(line.strip())
        if not match:
            continue
        field, value, status = (part.strip() for part in match.groups())
        if field.lower() == "field":
            continue
        rows[field] = (value, status)

    blocking: list[str] = []
    for field in _REQUIRED_FIELDS:
        value, status = rows.get(field, ("MISSING", "BLOCKING"))
        combined = f"{value} {status}".upper()
        if not value.strip() or any(marker in combined for marker in _BLOCKING_MARKERS):
            blocking.append(field)

    return RecoveryReadinessResult(
        record_path=path,
        ready=not blocking,
        blocking_fields=tuple(blocking),
    )


def require_recovery_ready(record_path: Path) -> RecoveryReadinessResult:
    result = evaluate_recovery_record(record_path)
    if not result.ready:
        fields = ", ".join(result.blocking_fields)
        raise RecoveryReadinessError(
            "Stateful infrastructure recovery is not ready. Blocking recovery-record "
            f"fields: {fields}. Update {result.record_path} with verified non-secret evidence."
        )
    return result
