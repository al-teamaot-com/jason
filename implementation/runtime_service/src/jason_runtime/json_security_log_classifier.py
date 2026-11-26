"""Read-only Security Log Quick Test and exact side-effect candidate analysis.

Never clears an event log or performs a provider write. A repair-generated SOC
alert must be uniquely attributable to the exact repair job and device before
it can be presented to a separately approved cleanup capability. In source
registry endpoint.alert.resolve is NOT granted, so cleanup is human review.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence


class JsonSecurityLogBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonSecurityLogAssessment:
    disposition: str
    test_status: str
    single_repair_attempted: bool
    exact_correlated_side_effect_uid: str | None
    side_effect_cleanup_permitted: bool = False
    security_log_clear_permitted: bool = False


def classify_security_log_readonly(
    *,
    client_id: str,
    device_uid: str,
    original_alert_uid: str,
    endpoint: Mapping[str, Any],
    source_alert: Mapping[str, Any],
    quick_test_job_uid: str,
    quick_test_component_uid: str,
    quick_test_terminal: bool,
    quick_test_stdout: str,
    quick_test_stderr: str,
    repair_attempt_count: int,
    repair_started_at: datetime | None,
    observed_at: datetime,
    possible_side_effects: Sequence[Mapping[str, Any]] = (),
) -> JsonSecurityLogAssessment:
    if (not client_id or not device_uid or not original_alert_uid or
        str(endpoint.get("resource_id") or "")!=device_uid or
        str(endpoint.get("companyID") or "")!=client_id or
        str(source_alert.get("alertUid") or "")!=original_alert_uid):
        raise JsonSecurityLogBoundaryError("SECURITY_LOG_EXACT_SCOPE_CHANGED")
    context=source_alert.get("alertSourceInfo")
    if not isinstance(context, Mapping) or str(
        context.get("deviceUid") or "")!=device_uid:
        raise JsonSecurityLogBoundaryError("SECURITY_LOG_ORIGINAL_ALERT_DEVICE_UNVERIFIED")
    if endpoint.get("online") is not True:
        return JsonSecurityLogAssessment(
            "waiting_device_access","unknown",bool(repair_attempt_count),None)
    if (not quick_test_job_uid or
        quick_test_component_uid != "a50d486b-2cce-4658-9e11-64fb6bf9ab9d" or
        quick_test_terminal is not True or
        not isinstance(quick_test_stdout,str) or
        not quick_test_stdout.strip() or
        not isinstance(quick_test_stderr,str) or
        quick_test_stderr.strip() or repair_attempt_count not in (0,1) or
        observed_at.tzinfo is None):
        raise JsonSecurityLogBoundaryError("SECURITY_LOG_QUICK_TEST_JOB_UNVERIFIED")
    text=quick_test_stdout.casefold()
    healthy=any(x in text for x in ("status=healthy","status: healthy"))
    unhealthy=any(x in text for x in (
        "status=unhealthy","status: unhealthy",
        "security log not readable",
        "could not retrieve information about the security log. error: the data is invalid",
    ))
    if healthy and unhealthy:
        raise JsonSecurityLogBoundaryError("SECURITY_LOG_CONTRADICTORY_TEST")
    if len(possible_side_effects)>100:
        raise JsonSecurityLogBoundaryError("SECURITY_LOG_SIDE_EFFECTS_UNBOUNDED")
    matches=[]
    for record in possible_side_effects:
        if not isinstance(record,Mapping):
            raise JsonSecurityLogBoundaryError("SECURITY_LOG_SIDE_EFFECT_INVALID")
        if str(record.get("companyID") or "")!=client_id:
            raise JsonSecurityLogBoundaryError("SECURITY_LOG_CROSS_CLIENT_SIDE_EFFECT")
        if str(record.get("deviceUid") or "")!=device_uid:
            raise JsonSecurityLogBoundaryError("SECURITY_LOG_CROSS_DEVICE_SIDE_EFFECT")
        evidence=str(record.get("description") or "").casefold()
        if "event log" not in evidence or "cleared" not in evidence:
            continue
        if repair_started_at is None or repair_started_at.tzinfo is None:
            raise JsonSecurityLogBoundaryError("SECURITY_LOG_REPAIR_CORRELATION_TIME_MISSING")
        timestamp=record.get("occurred_at")
        if not isinstance(timestamp,datetime) or timestamp.tzinfo is None:
            raise JsonSecurityLogBoundaryError("SECURITY_LOG_SIDE_EFFECT_TIME_INVALID")
        if timedelta(0)<=timestamp-repair_started_at<=timedelta(minutes=15):
            matches.append(record)
    if len(matches)>1:
        raise JsonSecurityLogBoundaryError("SECURITY_LOG_SIDE_EFFECT_AMBIGUOUS")
    correlated=(
        str(matches[0].get("alertUid") or "").strip() if matches else None
    )
    if matches and not correlated:
        raise JsonSecurityLogBoundaryError("SECURITY_LOG_SIDE_EFFECT_UID_MISSING")
    if healthy:
        disposition=("healthy_requires_correlated_soc_human_review"
                     if matches else "healthy_original_alert_completion_unapproved")
    elif unhealthy and repair_attempt_count==0:
        disposition="one_security_log_self_heal_candidate_requires_source_grant"
    elif unhealthy:
        disposition="one_repair_failed_human_review"
    else:
        disposition="unexpected_quick_test_output_human_review"
    return JsonSecurityLogAssessment(
        disposition,
        "healthy" if healthy else "unhealthy" if unhealthy else "unknown",
        repair_attempt_count==1,correlated)
