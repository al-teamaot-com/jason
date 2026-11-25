"""Read-only Idle Log Off eligibility, exact monitor and setter verification.

Does not perform a logoff or run a component. Existing source component
catalog/config/standing policy remain authoritative outside this classifier.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence


class JsonIdleLogoffBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonIdleLogoffAssessment:
    disposition: str
    exact_alert_uid: str | None
    current_compliant: bool | None
    repair_candidate: bool
    user_disruption_authorized: bool = False


def classify_idle_logoff_readonly(
    *,
    client_id: str,
    device_uid: str,
    endpoint: Mapping[str, Any],
    exact_monitor_component_uid: str,
    current_alerts: Sequence[Mapping[str, Any]],
    policy_required: bool,
    approved_policy_variables: Mapping[str, Any] | None,
    setter_attempts: int,
    setter_job_completed: bool | None,
    setter_stderr: str | None,
    observed_at: datetime,
    last_setter_completed_at: datetime | None = None,
    monitor_recheck_grace: timedelta = timedelta(minutes=15),
) -> JsonIdleLogoffAssessment:
    if (not client_id or not device_uid or
        not isinstance(policy_required,bool) or
        str(endpoint.get("resource_id") or "")!=device_uid or
        str(endpoint.get("companyID") or "")!=client_id or
        not exact_monitor_component_uid or
        observed_at.tzinfo is None or
        setter_attempts not in (0,1)):
        raise JsonIdleLogoffBoundaryError("IDLE_EXACT_SCOPE_OR_ATTEMPT_UNVERIFIED")
    if endpoint.get("online") is not True:
        return JsonIdleLogoffAssessment("waiting_device_access",None,None,False)
    device_type=str(endpoint.get("device_type") or "").casefold()
    protected=any(x in device_type for x in (
        "server","domain controller","kiosk","shared","rds","terminal"))
    if protected or not policy_required:
        return JsonIdleLogoffAssessment(
            "not_applicable_human_review",None,None,False)
    if (not isinstance(current_alerts,Sequence) or len(current_alerts)>100):
        raise JsonIdleLogoffBoundaryError("IDLE_MONITOR_PAGE_UNVERIFIED")
    matching=[]
    for alert in current_alerts:
        if not isinstance(alert,Mapping):
            raise JsonIdleLogoffBoundaryError("IDLE_ALERT_MALFORMED")
        context=alert.get("alertSourceInfo")
        if not isinstance(context,Mapping):
            raise JsonIdleLogoffBoundaryError("IDLE_ALERT_SOURCE_MISSING")
        if str(context.get("deviceUid") or "")!=device_uid:
            continue
        monitor=alert.get("alertMonitorInfo")
        if (not isinstance(monitor,Mapping) or
            str(monitor.get("componentUid") or "")!=exact_monitor_component_uid):
            continue
        matching.append(alert)
    if len(matching)>1:
        raise JsonIdleLogoffBoundaryError("IDLE_MONITOR_NOT_UNIQUE")
    if not matching:
        if setter_attempts:
            return JsonIdleLogoffAssessment(
                "monitor_cleared_verify_ticket",None,True,False)
        return JsonIdleLogoffAssessment(
            "no_current_alert_verify_compliance",None,None,False)
    alert=matching[0]
    uid=str(alert.get("alertUid") or "").strip()
    diagnostics=str(alert.get("diagnostics") or "")
    if not uid:
        raise JsonIdleLogoffBoundaryError("IDLE_ALERT_UID_MISSING")
    if ("compliant: false" not in diagnostics.casefold() and
        "compliant=false" not in diagnostics.casefold()):
        return JsonIdleLogoffAssessment(
            "monitor_execution_error_human_review",uid,None,False)
    if setter_attempts:
        if setter_job_completed is not True or (setter_stderr or "").strip():
            return JsonIdleLogoffAssessment(
                "setter_execution_failed_human_review",uid,False,False)
        if last_setter_completed_at is None or last_setter_completed_at.tzinfo is None:
            raise JsonIdleLogoffBoundaryError("IDLE_SETTER_JOB_TIMESTAMP_UNVERIFIED")
        if observed_at-last_setter_completed_at < monitor_recheck_grace:
            return JsonIdleLogoffAssessment(
                "waiting_normal_monitor_clear",uid,False,False)
        return JsonIdleLogoffAssessment(
            "setter_completed_monitor_still_unhealthy_human_review",
            uid,False,False)
    required=("CheckForIdleEvery_X_Min","MyIdleTimeInMin",
              "MyWarningTimeOut","MyFileDestination")
    if (not isinstance(approved_policy_variables,Mapping) or
        any(not str(approved_policy_variables.get(k) or "").strip()
            for k in required)):
        return JsonIdleLogoffAssessment(
            "policy_variables_not_verified_human_review",uid,False,False)
    return JsonIdleLogoffAssessment(
        "exact_setter_candidate_needs_governed_approval",uid,False,True)
