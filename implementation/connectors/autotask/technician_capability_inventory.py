"""Evidence-only comparison of Autotask provider routes and technician UI features.

Neither observed metadata nor UI operation names register or authorize new
capabilities. Provider paths are *catalog evidence*, never executable input.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import re
from typing import Any

from .operations import AUTOTASK_OPERATIONS

_PROVIDER_PATH = re.compile(
    r"/V1[.]0/[A-Z][A-Za-z0-9]{1,79}(?:/[A-Za-z0-9_{}-]+)*\Z"
)
_FEATURE_ID = re.compile(r"[a-z][a-z0-9_.-]{2,120}\Z")
_ACTIONS = frozenset({"GET", "POST", "PATCH", "DELETE"})


@dataclass(frozen=True)
class CapabilityGap:
    source: str
    operation: str
    method: str
    path: str
    status: str
    reason: str
    feature_id: str = ""


def discover_gaps(
    provider_operations: list[Mapping[str, Any]],
    *,
    technician_ui_operations: list[Mapping[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Compare reviewed observations to exact *registered provider route* names.

    UI features have no implied REST path; even a UI observation containing an
    API-like path is never accepted as proof of a registered API capability.
    """
    registered = {
        (definition.method.upper(), definition.path_template.rstrip("/").casefold())
        for definition in AUTOTASK_OPERATIONS.values()
    }
    observations = [("provider_api", item) for item in provider_operations]
    observations.extend(("technician_ui", x) for x in (technician_ui_operations or []))
    findings: dict[tuple[str, str, str], CapabilityGap] = {}
    if len(observations) > 1000:
        raise ValueError("capability inventory exceeds review bound")
    for source, item in observations:
        if not isinstance(item, Mapping):
            raise ValueError("operation observation must be an object")
        name = item.get("operation")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
            raise ValueError("operation name required")
        name = name.strip()
        feature_id = item.get("feature_id", "")
        if source == "technician_ui" and feature_id:
            # UI-only actions have a durable semantic ID and no invented API URL.
            surface = item.get("surface")
            if (not isinstance(feature_id, str)
                    or not _FEATURE_ID.fullmatch(feature_id)
                    or not isinstance(surface, str)
                    or not _FEATURE_ID.fullmatch(surface)):
                raise ValueError("UI feature identity/surface invalid")
            method, path = "UI", ""
            registered_match = False
            status = "candidate_requires_review"
            reason = "Technician UI feature: verify permission, semantics and supported API or governed UI adapter"
            evidence_key = feature_id
        else:
            method, path = item.get("method"), item.get("path")
            if not isinstance(method, str) or not isinstance(path, str):
                raise ValueError("operation requires method and path")
            method = method.strip().upper()
            path = path.strip().rstrip("/")
            if method not in _ACTIONS or not _PROVIDER_PATH.fullmatch(path):
                raise ValueError("untrusted provider operation")
            # A documented UI gesture can never *authorize* a provider route.
            registered_match = (
                source == "provider_api" and (method, path.casefold()) in registered
            )
            status = (
                "registered_provider_route" if registered_match
                else "candidate_requires_review"
            )
            reason = (
                "Registered route; runtime capability, requester scope and provider authority still required"
                if registered_match
                else "No proven executable route: verify provider semantics, technician scope and governance"
            )
            evidence_key = path.casefold()
        key = (source, method, evidence_key)
        if key in findings:
            raise ValueError("duplicate/conflicting operation observation")
        findings[key] = CapabilityGap(
            source=source,
            operation=name,
            method=method,
            path=path,
            status=status,
            reason=reason,
            feature_id=feature_id if isinstance(feature_id, str) else "",
        )
    return [asdict(v) for _, v in sorted(findings.items())]
