"""Idle Log Off exact policy/monitor source-only classification."""
from datetime import datetime,timedelta,timezone
import pytest
from jason_runtime.json_idle_logoff_classifier import (
    JsonIdleLogoffBoundaryError,classify_idle_logoff_readonly,
)

NOW=datetime(2026,11,19,16,tzinfo=timezone.utc)
UID="2b5de042-a3ec-4721-ba66-e0ca193a3604"
ENDPOINT={"resource_id":"uid-1","companyID":"777",
          "online":True,"device_type":{"category":"Laptop"}}
ALERT={"alertUid":"alert-1","alertSourceInfo":{"deviceUid":"uid-1"},
       "alertMonitorInfo":{"componentUid":UID},
       "diagnostics":"Compliant: False"}
VARIABLES={
    "CheckForIdleEvery_X_Min":"5","MyIdleTimeInMin":"240",
    "MyWarningTimeOut":"2","MyFileDestination":"C:\\AOT\\Idle",
}


def classify(**change):
    params={
        "client_id":"777","device_uid":"uid-1",
        "endpoint":ENDPOINT,"exact_monitor_component_uid":UID,
        "current_alerts":[ALERT],"policy_required":True,
        "approved_policy_variables":VARIABLES,
        "setter_attempts":0,"setter_job_completed":None,
        "setter_stderr":None,"observed_at":NOW,
    }
    params.update(change)
    return classify_idle_logoff_readonly(**params)


def test_current_noncompliance_one_exact_setter_candidate_not_logoff():
    r=classify()
    assert r.disposition=="exact_setter_candidate_needs_governed_approval"
    assert r.current_compliant is False
    assert r.repair_candidate
    assert not r.user_disruption_authorized


def test_healthy_alert_absence_requires_independent_compliance_read():
    r=classify(current_alerts=[])
    assert r.disposition=="no_current_alert_verify_compliance"
    assert not r.repair_candidate


def test_monitor_execution_error_not_compliant_false():
    r=classify(current_alerts=[{**ALERT,
                              "diagnostics":"PowerShell invalid path"}])
    assert r.disposition=="monitor_execution_error_human_review"


def test_policy_exception_server_and_kiosk_never_setter():
    for role in ("Server","Kiosk","RDS"):
        r=classify(endpoint={
            **ENDPOINT,"device_type":{"category":role}})
        assert r.disposition=="not_applicable_human_review"
        assert not r.repair_candidate
    assert classify(policy_required=False).disposition=="not_applicable_human_review"


def test_one_setter_completed_waits_for_normal_monitor_clear():
    r=classify(setter_attempts=1,setter_job_completed=True,
               setter_stderr="",
               last_setter_completed_at=NOW-timedelta(minutes=4))
    assert r.disposition=="waiting_normal_monitor_clear"
    assert not r.repair_candidate


def test_past_grace_one_attempt_no_automatic_second_setter():
    r=classify(setter_attempts=1,setter_job_completed=True,
               setter_stderr="",
               last_setter_completed_at=NOW-timedelta(minutes=20))
    assert r.disposition=="setter_completed_monitor_still_unhealthy_human_review"


def test_job_stdout_error_is_human_review():
    r=classify(setter_attempts=1,setter_job_completed=True,
               setter_stderr="Unexpected error")
    assert r.disposition=="setter_execution_failed_human_review"


def test_missing_policy_values_refuse_component():
    r=classify(approved_policy_variables={
        **VARIABLES,"MyIdleTimeInMin":None})
    assert r.disposition=="policy_variables_not_verified_human_review"


@pytest.mark.parametrize("change",[
    {"client_id":"other"},
    {"device_uid":"different"},
    {"endpoint":{**ENDPOINT,"companyID":"another"}},
    {"setter_attempts":2},
    {"current_alerts":[ALERT,ALERT]},
    {"setter_attempts":1,"setter_job_completed":True,
     "last_setter_completed_at":NOW.replace(tzinfo=None)},
])
def test_identity_duplicate_or_unbounded_execution_fails_closed(change):
    with pytest.raises(JsonIdleLogoffBoundaryError):
        classify(**change)


def test_idle_json_exact_component_not_autoexecuted():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    doc=validate_playbook_document(json.loads(
        (Path(__file__).resolve().parents[3]/
         "docs/playbooks/json/migration/candidates/idle_log_off.v1.json").read_text()))
    interpreter=JsonPlaybookInterpreter(doc)
    assert "endpoint.alert.resolve" not in doc.capabilities
    assert interpreter.instruction(step_id="ticket_gate",facts={}).step_id=="human_review"
    assert interpreter.instruction(step_id="setter_gate",facts={}).step_id=="human_review"
    assert interpreter.instruction(step_id="output_gate",facts={}).step_id=="human_review"
    assert interpreter.instruction(step_id="ticket_readback_gate",facts={}).step_id=="human_review"
    planned=interpreter.instruction(step_id="setter_gate",facts={
        "exact_policy_setter_component_variables_owner_grant_one_attempt":True,
        "trusted_exact_idle_setter_job_args":{
            "device_uid":"synthetic","component_uid":"synthetic"},
    })
    assert planned.step_id=="run_setter"
    assert planned.approval_required
    assert planned.capability=="automation.component.execute"
