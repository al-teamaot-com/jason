"""Deterministic DRMM -> Datto EDR threat correlation for the EDR/AV playbook.

This module performs no provider access. It correlates already-governed evidence
and fails closed when the originating Datto EDR detection is not unique.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


class ThreatCorrelationError(ValueError):
    """Base error for unsafe or insufficient threat correlation."""


class AmbiguousThreatCorrelationError(ThreatCorrelationError):
    """Raised when more than one provider-native EDR detection is plausible."""


@dataclass(frozen=True)
class CorrelatedThreat:
    threat_reference: str
    drmm_alert_uid: str
    edr_alert_id: str
    device_uid: str
    agent_id: str
    event_delta_seconds: float
    basis: str


def correlate_drmm_threat_to_edr_detection(
    *,
    threat_reference: str,
    drmm_alert: Mapping[str, Any],
    edr_detections: Sequence[Mapping[str, Any]],
    device_uid: str,
    agent_id: str,
    max_time_skew_seconds: int = 120,
) -> CorrelatedThreat:
    """Resolve one DRMM threat reference to exactly one Datto EDR alert UUID."""

    reference = str(threat_reference or "").strip()
    device = str(device_uid or "").strip()
    agent = str(agent_id or "").strip()
    if not reference or not device or not agent:
        raise ThreatCorrelationError(
            "threat reference, exact device UID, and exact EDR agent ID are required"
        )

    context = drmm_alert.get("alertContext")
    source = drmm_alert.get("alertSourceInfo")
    if not isinstance(context, Mapping) or not isinstance(source, Mapping):
        raise ThreatCorrelationError("DRMM alert lacks threat/source context")

    if str(context.get("esAlertId") or "").strip() != reference:
        raise ThreatCorrelationError("DRMM alert threat reference does not match request")
    if str(source.get("deviceUid") or "").strip() != device:
        raise ThreatCorrelationError("DRMM alert device does not match authoritative device UID")

    drmm_time = _drmm_timestamp(drmm_alert)
    matches: list[tuple[Mapping[str, Any], float]] = []

    for detection in edr_detections:
        if str(detection.get("device_id") or "").strip() != device:
            continue
        if str(detection.get("agent_id") or "").strip() != agent:
            continue
        if str(detection.get("source_type") or "").strip().casefold() != "av":
            continue
        if detection.get("signal") is False:
            continue

        observed = _edr_timestamp(detection)
        delta = abs((observed - drmm_time).total_seconds())
        if delta <= max_time_skew_seconds:
            matches.append((detection, delta))

    if not matches:
        raise ThreatCorrelationError(
            "no Datto EDR AV detection matches the exact device/agent and event window"
        )
    if len(matches) != 1:
        raise AmbiguousThreatCorrelationError(
            "multiple Datto EDR detections match; correlation must fail closed"
        )

    detection, delta = matches[0]
    alert_id = str(detection.get("alert_id") or "").strip()
    if not alert_id:
        raise ThreatCorrelationError("matched EDR detection lacks provider-native alert ID")

    return CorrelatedThreat(
        threat_reference=reference,
        drmm_alert_uid=str(drmm_alert.get("alertUid") or "").strip(),
        edr_alert_id=alert_id,
        device_uid=device,
        agent_id=agent,
        event_delta_seconds=delta,
        basis="exact_device_uid+exact_agent_id+drmm_threat_reference+event_time_window",
    )


def _drmm_timestamp(alert: Mapping[str, Any]) -> datetime:
    value = alert.get("timestamp")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ThreatCorrelationError("DRMM alert timestamp is required")
    return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)


def _edr_timestamp(detection: Mapping[str, Any]) -> datetime:
    for key in ("event_time", "created_on"):
        value = str(detection.get(key) or "").strip()
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise ThreatCorrelationError("EDR detection lacks a usable event timestamp")
