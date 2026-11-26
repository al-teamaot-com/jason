"""Read-only Security Log result and exact SOC-side effect classification."""
from datetime import datetime,timedelta,timezone
import pytest
from jason_runtime.json_security_log_classifier import (
    JsonSecurityLogBoundaryError,classify_security_log_readonly,
)

NOW=datetime(2026,11,19,16,tzinfo=timezone.utc)
ENDPOINT={"resource_id":"dev-1","companyID":"777","online":True}
ALERT={"alertUid":"security-original","alertSourceInfo":{"deviceUid":"dev-1"}}
UID="a50d486b-2cce-4658-9e11-64fb6bf9ab9d"


def classify(**changes):
    args={
        "client_id":"777","device_uid":"dev-1",
        "original_alert_uid":"security-original",
        "endpoint":ENDPOINT,"source_alert":ALERT,
        "quick_test_job_uid":"synthetic-job-1",
        "quick_test_component_uid":UID,
        "quick_test_terminal":True,
        "quick_test_stdout":"Status=Healthy","quick_test_stderr":"",
        "repair_attempt_count":0,
        "repair_started_at":None,"observed_at":NOW,
        "possible_side_effects":[],
    }
    args.update(changes)
    return classify_security_log_readonly(**args)


def test_healthy_quick_test_does_not_claim_original_alert_resolved():
    result=classify()
    assert result.test_status=="healthy"
    assert result.disposition=="healthy_original_alert_completion_unapproved"
    assert not result.security_log_clear_permitted
    assert not result.side_effect_cleanup_permitted


def test_known_unhealthy_one_bounded_self_heal_candidate_not_autoexec():
    result=classify(quick_test_stdout=(
        "Status=Unhealthy - Security log NOT readable"))
    assert result.disposition=="one_security_log_self_heal_candidate_requires_source_grant"
    assert not result.security_log_clear_permitted


def test_repeated_one_attempt_unhealthy_requires_human_review():
    result=classify(
        quick_test_stdout="Status=Unhealthy",
        repair_attempt_count=1,
        repair_started_at=NOW-timedelta(minutes=5))
    assert result.disposition=="one_repair_failed_human_review"
    assert result.single_repair_attempted


def test_exact_same_device_time_soc_event_is_review_not_autocleanup():
    related={
        "alertUid":"soc-1","companyID":"777","deviceUid":"dev-1",
        "description":"Windows Security event log cleared",
        "occurred_at":NOW-timedelta(minutes=1),
    }
    result=classify(
        possible_side_effects=[related],
        repair_attempt_count=1,
        repair_started_at=NOW-timedelta(minutes=4))
    assert result.disposition=="healthy_requires_correlated_soc_human_review"
    assert result.exact_correlated_side_effect_uid=="soc-1"
    assert not result.side_effect_cleanup_permitted


def test_unrelated_soc_event_no_false_correlation():
    other={
        "alertUid":"soc-2","companyID":"777","deviceUid":"dev-1",
        "description":"High-risk logon detected",
        "occurred_at":NOW-timedelta(minutes=1),
    }
    result=classify(possible_side_effects=[other])
    assert result.exact_correlated_side_effect_uid is None


def test_offline_device_keeps_mutation_inert():
    assert classify(endpoint={**ENDPOINT,"online":False},
                    quick_test_terminal=False).disposition=="waiting_device_access"


@pytest.mark.parametrize("change",[
    {"client_id":"other"},
    {"device_uid":"other"},
    {"original_alert_uid":"other"},
    {"endpoint":{**ENDPOINT,"companyID":"other"}},
    {"source_alert":{**ALERT,"alertSourceInfo":{"deviceUid":"other"}}},
    {"quick_test_component_uid":"wrong"},
    {"quick_test_terminal":False},
    {"quick_test_stderr":"error"},
    {"quick_test_stdout":""},
    {"quick_test_stdout":"Status=Healthy Status=Unhealthy"},
    {"repair_attempt_count":2},
])
def test_missing_identity_test_output_or_attempts_fail_closed(change):
    with pytest.raises(JsonSecurityLogBoundaryError):
        classify(**change)


def test_cross_client_soc_never_ignored_or_cleaned():
    record={
        "alertUid":"other","companyID":"different",
        "deviceUid":"dev-1","description":"Security event log cleared",
        "occurred_at":NOW,
    }
    with pytest.raises(JsonSecurityLogBoundaryError,match="CROSS_CLIENT"):
        classify(possible_side_effects=[record],
                 repair_started_at=NOW-timedelta(minutes=1))


def test_multiple_related_soc_alerts_ambiguous_requires_review():
    record={
        "alertUid":"a","companyID":"777","deviceUid":"dev-1",
        "description":"Security event log cleared","occurred_at":NOW,
    }
    with pytest.raises(JsonSecurityLogBoundaryError,match="AMBIGUOUS"):
        classify(possible_side_effects=[record,{**record,"alertUid":"b"}],
                 repair_started_at=NOW-timedelta(minutes=1))


def test_security_log_json_requires_sensitive_promotion_no_auto_alert_cleanup():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    doc=validate_playbook_document(json.loads(
        (Path(__file__).resolve().parents[3]/
         "docs/playbooks/json/migration/candidates/security_log_self_heal.v1.json").read_text()))
    interpreter=JsonPlaybookInterpreter(doc)
    assert "endpoint.alert.resolve" not in doc.capabilities
    for step in ("ticket_gate","quick_gate","job_gate","classification_gate",
                 "security_sensitive_gate","verify_gate","note_readback_gate"):
        assert interpreter.instruction(step_id=step,facts={}).step_id=="human_review"
    assert interpreter.instruction(step_id="classification_gate",facts={
        "verified_security_log_disposition":"healthy_original_alert_completion_unapproved",
    }).step_id=="human_review"
    assert interpreter.instruction(step_id="classification_gate",facts={
        "verified_security_log_disposition":"healthy_requires_correlated_soc_human_review",
    }).step_id=="human_review"
    planned=interpreter.instruction(step_id="security_sensitive_gate",facts={
        "exact_security_log_mutation_owner_approval_and_one_attempt":True,
        "trusted_exact_security_log_self_heal_args":{
            "device_uid":"synthetic","component_uid":"synthetic"},
    })
    assert planned.step_id=="self_heal"
    assert planned.approval_required is True
    assert planned.approval_classification=="modifying"
    assert planned.capability=="automation.component.execute"
