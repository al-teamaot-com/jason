from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from connectors.core.contracts import ConnectorResult
from connectors.resource_convergence import IdentityEvidence, ResourceConvergenceError


_MATCH_FIELDS = (
    "name",
    "hostname",
    "serial_number",
    "serialNumber",
    "device_uid",
    "deviceUid",
)


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    return ""


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResourceConvergenceError(f"{label} payload must be a mapping")
    return value


def _identity_attributes(record: Mapping[str, Any]) -> dict[str, str]:
    attributes: dict[str, str] = {}
    nested = record.get("attributes")
    if isinstance(nested, Mapping):
        for key in _MATCH_FIELDS:
            value = _string(nested.get(key))
            if value:
                canonical = "serial_number" if key in {"serial_number", "serialNumber"} else (
                    "device_uid" if key in {"device_uid", "deviceUid"} else key
                )
                attributes.setdefault(canonical, value)
    for key in _MATCH_FIELDS:
        value = _string(record.get(key))
        if value:
            canonical = "serial_number" if key in {"serial_number", "serialNumber"} else (
                "device_uid" if key in {"device_uid", "deviceUid"} else key
            )
            attributes.setdefault(canonical, value)
    return attributes


def _require_identifier(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _string(record.get(key))
        if value:
            return value
    raise ResourceConvergenceError("provider payload is missing a stable external identifier")


def project_it_glue_configuration(result: ConnectorResult, organization_id: str) -> IdentityEvidence:
    if result.provider != "it_glue":
        raise ResourceConvergenceError("IT Glue projector received the wrong provider")
    if result.capability not in {"it_glue.entity.get", "it_glue.configuration.search"}:
        raise ResourceConvergenceError("IT Glue projector received an unsupported capability")
    payload = _mapping(result.data, label="IT Glue")
    record: Mapping[str, Any]
    data = payload.get("data")
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        if len(data) != 1:
            raise ResourceConvergenceError("IT Glue projector requires exactly one configuration record")
        record = _mapping(data[0], label="IT Glue configuration")
    else:
        record = _mapping(data, label="IT Glue configuration")

    external_id = _require_identifier(record, "id")
    attributes = _identity_attributes(record)
    if not attributes:
        raise ResourceConvergenceError("IT Glue configuration has no governed matching attributes")
    return IdentityEvidence(
        provider="it_glue",
        resource_type="configuration",
        external_id=external_id,
        organization_id=organization_id,
        attributes=attributes,
        source_authority="it_glue:governed-live-read",
    )


def project_datto_rmm_device(result: ConnectorResult, organization_id: str) -> IdentityEvidence:
    if result.provider != "datto_rmm":
        raise ResourceConvergenceError("Datto projector received the wrong provider")
    if result.capability not in {"datto_rmm.device.get", "datto_rmm.device.search"}:
        raise ResourceConvergenceError("Datto projector received an unsupported capability")
    payload = _mapping(result.data, label="Datto RMM")

    record: Mapping[str, Any] | None = None
    for key in ("device", "data"):
        candidate = payload.get(key)
        if isinstance(candidate, Mapping):
            record = candidate
            break
    if record is None:
        for key in ("devices", "results", "items"):
            candidate = payload.get(key)
            if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
                if len(candidate) != 1:
                    raise ResourceConvergenceError("Datto projector requires exactly one device candidate")
                record = _mapping(candidate[0], label="Datto RMM device")
                break
    if record is None:
        record = payload

    external_id = _require_identifier(record, "uid", "deviceUid", "device_uid", "id")
    attributes = _identity_attributes(record)
    if not attributes:
        raise ResourceConvergenceError("Datto RMM device has no governed matching attributes")
    return IdentityEvidence(
        provider="datto_rmm",
        resource_type="device",
        external_id=external_id,
        organization_id=organization_id,
        attributes=attributes,
        source_authority="datto_rmm:governed-live-read",
    )
