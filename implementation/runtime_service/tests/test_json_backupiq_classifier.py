"""BackupIQ source classifier parity and duplicate asset safety."""
from datetime import datetime, timedelta, timezone
import pytest

from jason_runtime.json_backupiq_classifier import (
    JsonBackupIQBoundaryError, classify_backupiq_readonly,
)
from autonomous_remediation.deb_availability import select_deb_asset

NOW=datetime(2026,11,19,16,tzinfo=timezone.utc)
ENDPOINT={"resource_id":"device-1","companyID":"0",
          "hostname":"AOT-DEV1","online":True}


def asset(*,status="online",enabled=True,
          last_success=None,last_online=None,id="asset-1"):
    return {
        "id":id,"name":"AOT-DEV1","status":status,
        "backupEnabled":enabled,
        "lastSuccessfulBackupTimestamp":(
            last_success if last_success is not None else
            (NOW-timedelta(hours=2)).isoformat()),
        "lastOnlineTimestamp":(
            last_online if last_online is not None else
            (NOW-timedelta(hours=1)).isoformat()),
    }


def classify(*,endpoint=ENDPOINT,assets=None,alerts=(),**extra):
    args={
        "exact_autotask_company_id":"0",
        "verified_provider_customer_boundary":True,
        "exact_device_uid":"device-1",
        "exact_hostname":"AOT-DEV1",
        "endpoint":endpoint,
        "provider_assets":assets if assets is not None else [asset()],
        "current_provider_alerts":alerts,
        "ticket_created_at":NOW-timedelta(days=1),
        "observed_at":NOW,
    }
    args.update(extra)
    return classify_backupiq_readonly(**args)


def test_aot_company_zero_is_valid_and_recent_success_no_open_alert_is_recovered():
    result=classify()
    assert result.classification=="stale_or_recovered_alert"
    assert result.asset_id=="asset-1"
    assert result.provider_matches==1
    assert not result.reinstall_candidate
    assert not result.provider_mutation_allowed


@pytest.mark.parametrize("endpoint_online,provider_online,enabled,alerts,expected",[
    (False,False,True,(),"true_offline_both_sources"),
    (False,True,True,(),"drmm_only_offline_conflict"),
    (True,False,True,(),"backup_agent_connectivity_failure"),
    (True,True,False,(),"backup_configuration_issue"),
    (True,True,True,({"id":"current-alert"},),
     "persistent_backupiq_condition_after_success"),
])
def test_two_source_backup_condition_matches_legacy_branch(
    endpoint_online,provider_online,enabled,alerts,expected,
):
    result=classify(
        endpoint={**ENDPOINT,"online":endpoint_online},
        assets=[asset(status="online" if provider_online else "offline",
                      enabled=enabled)],alerts=alerts)
    assert result.classification==expected
    assert not result.provider_mutation_allowed


def test_old_last_success_is_stale_backup_and_only_candidate():
    result=classify(assets=[asset(
        last_success=(NOW-timedelta(days=15)).isoformat())])
    assert result.classification=="backup_failure_or_stale_success"
    assert result.reinstall_candidate
    assert not result.provider_mutation_allowed


def test_exact_duplicate_resolution_reuses_existing_source_selector():
    active=asset(last_online=(NOW-timedelta(hours=1)).isoformat())
    old=asset(status="offline",id="prior",
              last_online=(NOW-timedelta(days=60)).isoformat())
    selection=select_deb_asset([old,active],hostname="AOT-DEV1",observed_at=NOW)
    result=classify(assets=[old,active])
    assert result.asset_id==selection.selected_asset_id=="asset-1"
    assert result.provider_matches==2


def test_unresolved_current_duplicate_asset_never_authorizes_reinstall():
    result=classify(assets=[asset(id="first"),asset(id="second")])
    assert result.classification=="duplicate_or_ambiguous_provider_asset"
    assert result.asset_id is None
    assert not result.reinstall_candidate


def test_no_asset_is_lifecycle_issue_not_provider_authentication_failure():
    result=classify(assets=[])
    assert result.classification=="asset_identity_or_lifecycle_issue"
    assert not result.reinstall_candidate


@pytest.mark.parametrize("change",[
    {"verified_provider_customer_boundary":False},
    {"exact_autotask_company_id":"other"},
    {"exact_device_uid":"other"},
    {"exact_hostname":"other"},
    {"endpoint":{**ENDPOINT,"companyID":"other"}},
    {"current_provider_alerts":[{}]*101},
])
def test_missing_or_cross_company_boundary_blocks_all_work(change):
    with pytest.raises(JsonBackupIQBoundaryError):
        classify(**change)


def test_backupiq_json_requires_customer_binding_and_owner_promotion():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    file=(Path(__file__).resolve().parents[3]/
          "docs/playbooks/json/migration/candidates/backupiq_endpoint_backup.v1.json")
    doc=validate_playbook_document(json.loads(file.read_text()))
    j=JsonPlaybookInterpreter(doc)
    for step in ("ticket_gate","endpoint_gate","provider_customer_gate",
                 "reinstall_gate","note_gate","ticket_readback_gate"):
        assert j.instruction(step_id=step,facts={}).step_id=="human_review"
    assert j.instruction(step_id="classification_gate",facts={
        "verified_backupiq_disposition":"true_offline_both_sources",
    }).step_id=="wait_device"
    assert j.instruction(step_id="classification_gate",facts={
        "verified_backupiq_disposition":"drmm_only_offline_conflict",
    }).step_id=="human_review"
    plan=j.instruction(step_id="classification_gate",facts={
        "verified_backupiq_disposition":"backup_agent_connectivity_failure",
        "exact_one_reinstall_component_owner_grant_and_no_prior_attempt":True,
        "trusted_exact_backupiq_reinstall_component_arguments":{
            "device_uid":"synthetic","component_uid":"synthetic-only",
        },
    })
    assert plan.step_id=="reinstall_agent"
    assert plan.approval_required
    assert plan.capability=="automation.component.execute"
    assert j.instruction(step_id="backup_success_gate",facts={}).step_id=="human_review"


def test_numeric_aot_company_zero_is_not_falsely_rejected():
    result=classify(endpoint={**ENDPOINT,"companyID":0})
    assert result.classification=="stale_or_recovered_alert"
    assert not result.provider_mutation_allowed
