"""Server-owned DRMM fact reduction for the existing JSON interpreter.

Normalizes only currently read governed results. This module has no provider
transport, mutation, approval, or registry access. It must fail closed on
ambiguous alert, device, or security-agent identity.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .json_shadow_integration import JsonShadowBoundaryError

SUPPORTED_CLASS = "endpoint_security_threat_ctx"


def _data(result: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = result.get("evidence")
    if not isinstance(evidence, Mapping):
        raise JsonShadowBoundaryError("GOVERNED_EVIDENCE_MISSING")
    data = evidence.get("data")
    if not isinstance(data, Mapping):
        raise JsonShadowBoundaryError("GOVERNED_DATA_MISSING")
    return data


def reduce_daily_drmm_alert(
    capability: str, result: Mapping[str, Any],
    facts: Mapping[str, Any], *, at: datetime,
) -> Mapping[str, Any]:
    if not isinstance(at, datetime) or at.tzinfo is None:
        raise JsonShadowBoundaryError("TRUSTED_CLOCK_REQUIRED")
    if capability == "management.alert.search":
        data = _data(result)
        values = data.get("provider_data", data)
        if not isinstance(values, Mapping):
            raise JsonShadowBoundaryError("ALERT_RESPONSE_INVALID")
        alerts = values.get("alerts")
        if not isinstance(alerts, list):
            raise JsonShadowBoundaryError("ALERT_LIST_MISSING")
        target = str(facts.get("target_id") or "")
        matching = [x for x in alerts if isinstance(x, Mapping)
                    and str(x.get("alertUid") or "") == target]
        if len(matching) != 1:
            raise JsonShadowBoundaryError("ALERT_ID_NOT_UNIQUE")
        alert = matching[0]
        source = alert.get("alertSourceInfo")
        if not isinstance(source, Mapping):
            raise JsonShadowBoundaryError("EXACT_DEVICE_ID_MISSING")
        device = str(source.get("deviceUid") or "").strip()
        if not device:
            raise JsonShadowBoundaryError("EXACT_DEVICE_ID_MISSING")
        try:
            created = datetime.fromtimestamp(
                int(alert["timestamp"]) / 1000, tz=timezone.utc)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise JsonShadowBoundaryError("PROVIDER_TIMESTAMP_INVALID") from exc
        context = alert.get("alertContext")
        if not isinstance(context, Mapping):
            raise JsonShadowBoundaryError("ALERT_CLASS_UNAVAILABLE")
        alert_class = str(context.get("@class") or "").strip()
        # Only exact verified alert provides device identity; caller seed may
        # identify alert UID but cannot select arbitrary endpoint/agent.
        return {
            "alert_uid": target, "device_uid": device,
            "alert_in_24_hour_window": at - timedelta(hours=24) <= created <= at,
            "exact_alert_device_identity": True,
            "registered_alert_class": alert_class,
            "ticket_number": str(alert.get("ticketNumber") or ""),
        }
    if capability == "endpoint.device.read":
        evidence = result.get("evidence")
        record = evidence.get("record") if isinstance(evidence, Mapping) else None
        if not isinstance(record, Mapping):
            raise JsonShadowBoundaryError("ENDPOINT_RECORD_MISSING")
        observed = str(record.get("resource_id") or record.get("deviceUid") or "")
        if not observed or observed != str(facts.get("device_uid") or ""):
            raise JsonShadowBoundaryError("ENDPOINT_IDENTITY_UNVERIFIED")
        return {"exact_endpoint_online": record.get("online") is True}
    if capability == "endpoint.security.status.read":
        data = _data(result)
        matches = data.get("resource_matches")
        if not isinstance(matches, list) or len(matches) != 1:
            raise JsonShadowBoundaryError("SECURITY_AGENT_NOT_UNIQUE")
        item = matches[0]
        if not isinstance(item, Mapping):
            raise JsonShadowBoundaryError("SECURITY_AGENT_INVALID")
        observed_device = str(item.get("device_uid") or "")
        if observed_device != str(facts.get("device_uid") or ""):
            raise JsonShadowBoundaryError("SECURITY_AGENT_DEVICE_MISMATCH")
        agent = str(item.get("agent_id") or "").strip()
        av = item.get("datto_av")
        if not isinstance(av, Mapping):
            raise JsonShadowBoundaryError("SECURITY_HEALTH_MISSING")
        healthy = bool(agent) and all(av.get(k) is True for k in (
            "enabled", "connected", "engine_ready"))
        return {
            "exact_agent_and_av_engine_healthy": healthy,
            "agent_id": agent,
        }
    if capability == "endpoint.security.detection.search":
        data = _data(result)
        alerts = data.get("alerts")
        if not isinstance(alerts, list):
            raise JsonShadowBoundaryError("SECURITY_DETECTION_LIST_MISSING")
        return {"current_nonarchived_detection_count": len(alerts)}
    raise JsonShadowBoundaryError("UNREGISTERED_FACT_REDUCER_CAPABILITY")
