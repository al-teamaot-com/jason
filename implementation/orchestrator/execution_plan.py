from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping
from urllib.parse import urlsplit


_FORBIDDEN_SECRET_KEYS = {
    "authorization", "proxy-authorization", "secret", "password", "passwd",
    "access_token", "refresh_token", "api_key", "apikey", "client_secret",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _reject_secret_material(value: Any, *, path: str = "") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().casefold().replace("-", "_")
            child_path = f"{path}.{raw_key}" if path else str(raw_key)
            if key in _FORBIDDEN_SECRET_KEYS:
                raise ValueError(f"execution plan must not contain secret material: {child_path}")
            _reject_secret_material(child, path=child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret_material(child, path=f"{path}[{index}]")


def normalize_provider_relative_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        raise ValueError("execution plan provider-relative path is required")
    parsed = urlsplit(text)
    if parsed.scheme or parsed.netloc:
        raise ValueError("execution plan path must be provider-relative and must not contain a hostname")
    normalized = "/" + parsed.path.lstrip("/")
    if parsed.query:
        raise ValueError("material query parameters must be carried separately from normalized_path")
    return normalized


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Secret-free concrete provider mutation authorized by governance.

    Dynamic provider hostnames, authentication headers, correlation identifiers and
    transport-only volatility are intentionally absent. Provider adapters must place
    all authority-relevant mutation material in these fields before authorization.
    """

    principal_id: str
    organization_id: str
    client_id: str | None
    canonical_capability: str
    selected_provider_id: str
    provider_capability: str
    action_method: str
    resource_type: str
    resource_identifier: str | None
    normalized_path: str
    normalized_payload: Mapping[str, Any] = field(default_factory=dict)
    material_parameters: Mapping[str, Any] = field(default_factory=dict)
    symbolic_resolutions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = {
            "principal_id": self.principal_id,
            "organization_id": self.organization_id,
            "canonical_capability": self.canonical_capability,
            "selected_provider_id": self.selected_provider_id,
            "provider_capability": self.provider_capability,
            "action_method": self.action_method,
            "resource_type": self.resource_type,
            "normalized_path": self.normalized_path,
        }
        missing = sorted(name for name, value in required.items() if not str(value or "").strip())
        if missing:
            raise ValueError("execution plan fields are empty: " + ", ".join(missing))
        object.__setattr__(self, "action_method", str(self.action_method).strip().upper())
        object.__setattr__(self, "normalized_path", normalize_provider_relative_path(self.normalized_path))
        if self.resource_identifier is not None and not str(self.resource_identifier).strip():
            raise ValueError("resource_identifier must be non-empty when provided")
        for material in (self.normalized_payload, self.material_parameters, self.symbolic_resolutions):
            _reject_secret_material(material)

    def canonical_material(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "organization_id": self.organization_id,
            "client_id": self.client_id,
            "canonical_capability": self.canonical_capability,
            "selected_provider_id": self.selected_provider_id,
            "provider_capability": self.provider_capability,
            "action_method": self.action_method,
            "resource_type": self.resource_type,
            "resource_identifier": self.resource_identifier,
            "normalized_path": self.normalized_path,
            "normalized_payload": _json_safe(self.normalized_payload),
            "material_parameters": _json_safe(self.material_parameters),
            "symbolic_resolutions": _json_safe(self.symbolic_resolutions),
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.canonical_material(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class PreparedExecutionPlan:
    """A concrete plan plus provider-private prepared state.

    `opaque` may contain credentials or dynamic transport details, but it is never
    persisted, audited, or fingerprinted. The orchestrator authorizes only `plan`.
    """

    plan: ExecutionPlan
    opaque: Any = None
