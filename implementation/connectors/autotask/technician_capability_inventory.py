"""Provider-neutral technician operation gap inventory for Autotask.

Discovery is evidence only. Neither live metadata nor UI observations grant
permission to execute, register capabilities, or construct provider requests.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import re
from typing import Any

from .operations import AUTOTASK_OPERATIONS

_SAFE_ENTITY = re.compile(r"[A-Z][A-Za-z0-9]{1,79}\Z")
_ACTIONS = frozenset({"GET", "POST", "PATCH", "DELETE"})


@dataclass(frozen=True)
class CapabilityGap:
    source: str
    operation: str
    method: str
    path: str
    status: str
    reason: str


def discover_gaps(
    provider_operations: list[Mapping[str, Any]],
    *,
    technician_ui_operations: list[Mapping[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Compare trusted observations to the registered provider operation catalog.

    Inputs must be independently authenticated and collected from approved
    sources. No operation is executed or promoted by this function.
    """
    registered = {
        (definition.method.upper(), definition.path_template.rstrip("/").lower())
        for definition in AUTOTASK_OPERATIONS.values()
    }
    observations: list[tuple[str, Mapping[str, Any]]] = [
        ("provider_api", item) for item in provider_operations
    ]
    observations.extend(
        ("technician_ui", item)
        for item in (technician_ui_operations or [])
    )
    findings: dict[tuple[str, str, str], CapabilityGap] = {}
    for source, item in observations:
        if not isinstance(item, Mapping):
            raise ValueError("operation observation must be an object")
        method, path, name = (item.get(key) for key in ("method", "path", "operation"))
        if not all(isinstance(v, str) for v in (method, path, name)):
            raise ValueError("operation requires string method, path, and operation")
        method = method.strip().upper()
        path = path.strip().rstrip("/")
        name = name.strip()
        if method not in _ACTIONS or not name or len(name) > 160:
            raise ValueError("invalid operation")
        if not path.startswith("/V1.0/") or len(path) > 250 or any(
            c in path for c in ("?", "#", "\\", "://")
        ):
            raise ValueError("untrusted provider path")
        entity = path.split("/")[2]
        if not _SAFE_ENTITY.fullmatch(entity):
            raise ValueError("invalid entity path")
        # UI-only actions can have no REST representation. They are included
        # as documented UI observations but are NOT executable.
        registered_match = (method, path.lower()) in registered
        status = "registered_provider_route" if registered_match else "candidate_requires_review"
        reason = (
            "Registered route; runtime capability and requester authority still required"
            if registered_match
            else "No registered matching provider route; verify technician eligibility, API support, semantics and governance"
        )
        key = (source, method, path.lower())
        findings[key] = CapabilityGap(source, name, method, path, status, reason)
    return [asdict(v) for _, v in sorted(findings.items())]
