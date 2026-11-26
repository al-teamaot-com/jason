"""Governed-result reducer for the existing Windows time-source JSON shadow.

Reuses the existing legacy *pure classifier* signatures, parsing, history
window and state semantics. It does not run the legacy worker, access providers
or create execution authority. Exact DRMM site ownership must be supplied by
a separate trusted client/site binding, never inferred from the alert alone.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping

from autonomous_remediation.json_shadow_integration import JsonShadowBoundaryError

from .windows_time_source_shadow import (
    RECURRENCE_WINDOW, RECURRENCE_THRESHOLD,
    _alert_items, _evidence, _provider_time, is_time_source_alert, parse_sources,
)


def _fingerprint(material: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def reduce_windows_time_shadow(
    capability: str,
    result: Mapping[str, Any],
    facts: Mapping[str, Any],
    *,
    at: datetime,
    expected_site: str,
) -> Mapping[str, Any]:
    """Reduce one exact governed read into narrow source-authoritative facts.

    No caller-supplied health, approval, or success facts are accepted.
    A stronger same-client site check than the legacy shadow is intentional.
    """
    if not isinstance(at, datetime) or at.tzinfo is None:
        raise JsonShadowBoundaryError("TIME_SOURCE_TRUSTED_CLOCK_REQUIRED")
    site_binding = str(expected_site or "").strip()
    if not site_binding:
        raise JsonShadowBoundaryError("TIME_SOURCE_EXACT_CLIENT_SITE_BINDING_REQUIRED")

    if capability == "management.alert.search":
        alerts = _alert_items(result)
        alert_uid = str(facts.get("target_id") or "").strip()
        matching = [
            row for row in alerts if str(row.get("alertUid") or "").strip() == alert_uid
        ]
        if len(matching) != 1:
            raise JsonShadowBoundaryError("TIME_SOURCE_EXACT_ALERT_NOT_UNIQUE")
        alert = matching[0]
        if not is_time_source_alert(alert):
            return {"time_signature_match": False}
        source = alert.get("alertSourceInfo")
        if not isinstance(source, Mapping):
            raise JsonShadowBoundaryError("TIME_SOURCE_SOURCE_IDENTITY_MISSING")
        device_uid = str(source.get("deviceUid") or "").strip()
        hostname = str(source.get("deviceName") or "").strip()
        site = str(source.get("siteName") or "").strip()
        observed, approved = parse_sources(alert)
        complete = bool(alert_uid and device_uid and hostname and site and
                        observed and approved)
        if not complete:
            return {
                "time_signature_match": True,
                "time_alert_identity_complete": False,
            }
        if site.casefold() != site_binding.casefold():
            raise JsonShadowBoundaryError("TIME_SOURCE_CLIENT_SITE_SCOPE_MISMATCH")
        return {
            "time_signature_match": True,
            "time_alert_identity_complete": True,
            "verified_site_client_binding": True,
            "alert_uid": alert_uid,
            "device_uid": device_uid,
            "hostname": hostname,
            "site": site,
            "observed_source": observed,
            "approved_sources": list(approved),
        }

    if capability == "endpoint.device.read":
        record = _evidence(result).get("record")
        if not isinstance(record, Mapping):
            raise JsonShadowBoundaryError("TIME_SOURCE_DEVICE_RECORD_MISSING")
        observed_uid = str(
            record.get("resource_id") or record.get("uid") or
            record.get("deviceUid") or ""
        ).strip()
        observed_host = str(
            record.get("hostname") or record.get("hostName") or
            record.get("name") or ""
        ).strip()
        if (observed_uid != str(facts.get("device_uid") or "")
                or observed_host.casefold() !=
                str(facts.get("hostname") or "").casefold()):
            raise JsonShadowBoundaryError("TIME_SOURCE_DEVICE_IDENTITY_CHANGED")
        online = record.get("online") is True
        output = {"endpoint_identity_verified": True, "device_online": online}
        if not online:
            reason = (
                "endpoint is offline in authoritative DRMM state; diagnostics "
                "and remediation are deferred"
            )
            material = {
                "alert_uid": str(facts["alert_uid"]),
                "device_uid": str(facts["device_uid"]),
                "hostname": str(facts["hostname"]),
                "site": str(facts["site"]),
                "observed_source": str(facts["observed_source"]),
                "approved_sources": tuple(facts["approved_sources"]),
                "recurrence_count": 0,
                "classification": "WAITING_DEVICE_ACCESS",
                "reason": reason,
            }
            output.update({
                "recurrence_count": 0,
                "classification": "WAITING_DEVICE_ACCESS",
                "classification_reason": reason,
                "decision_fingerprint": _fingerprint(material),
            })
        return output

    if capability == "endpoint.alert.history.search":
        cutoff = at - RECURRENCE_WINDOW
        count = 0
        for history in _alert_items(result):
            if not is_time_source_alert(history):
                continue
            created = _provider_time(history)
            if created is not None and cutoff <= created <= at:
                count += 1
        recurrence = count + 1
        recurring = recurrence >= RECURRENCE_THRESHOLD
        classification = (
            "RECURRING_FAILURE" if recurring else "CURRENT_TIME_SOURCE_MISMATCH"
        )
        source = str(facts.get("observed_source") or "")
        reason = (
            f"{recurrence} matching time-source mismatch episodes in the 30-day window"
            if recurring else
            f"current source {source} is outside the approved source set"
        )
        material = {
            "alert_uid": str(facts["alert_uid"]),
            "device_uid": str(facts["device_uid"]),
            "hostname": str(facts["hostname"]),
            "site": str(facts["site"]),
            "observed_source": source,
            "approved_sources": tuple(facts["approved_sources"]),
            "recurrence_count": recurrence,
            "classification": classification,
            "reason": reason,
        }
        return {
            "history_verified": True,
            "recurrence_count": recurrence,
            "recurring_failure": recurring,
            "classification": classification,
            "classification_reason": reason,
            "decision_fingerprint": _fingerprint(material),
        }
    raise JsonShadowBoundaryError("TIME_SOURCE_UNDECLARED_READ_CAPABILITY")
