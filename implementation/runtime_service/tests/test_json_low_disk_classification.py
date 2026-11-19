"""Low disk JSON candidate pure parity and protected-data denial tests."""
import pytest
from jason_runtime.json_low_disk_classification import (
    JsonLowDiskBoundaryError, classify_low_disk_readonly,
)
from jason_runtime.low_disk_analysis import (
    choose_cleanup, storage_health_summary, relevant_findings,
)

GIB = 1024 ** 3
DEVICE = {"resource_id": "device-1", "companyID": "777",
          "online": True, "device_type": {"category": "Desktop"}}
VOLUME = {"DriveLetter": "C", "Size": 100 * GIB, "SizeRemaining": 5 * GIB}


def evidence(*, sysmon_bytes=0, storage_errors=0, dependencies=False):
    return {
        "physical_disks": [{"HealthStatus": "Healthy",
                            "OperationalStatus": "OK"}],
        "reliability": [{"ReadErrorsTotal": storage_errors,
                         "WriteErrorsTotal": 0}],
        "sysmon": [{"Bytes": sysmon_bytes}],
        "sysmon_dependencies": (
            [{"Name": "live sysmon process"}] if dependencies else []),
        "software_distribution": [],
        "large_files": [], "top_folders": [], "vss": [],
        "system_files": [],
    }


def assess(**changes):
    args = {
        "exact_client_id": "777", "exact_device_uid": "device-1",
        "exact_drive_letter": "C:",
        "endpoint": DEVICE, "current_volume": VOLUME,
        "authoritative_low_disk_monitor_open": True,
        "source_grace_elapsed": True,
        "evidence": evidence(),
    }
    args.update(changes)
    return classify_low_disk_readonly(**args)


def test_reuses_exact_legacy_classifier_for_safe_sysmon_candidate():
    e = evidence(sysmon_bytes=5 * GIB)
    risk, health = storage_health_summary(e["physical_disks"],
                                           e["reliability"], 0)
    cleanup, count = choose_cleanup(
        sysmon=e["sysmon"],
        sysmon_dependencies=e["sysmon_dependencies"],
        software_distribution=e["software_distribution"],
        storage_health_risk=risk)
    actual = assess(evidence=e)
    assert not actual.storage_risk
    assert actual.storage_health_text == health
    assert actual.cleanup_kind == cleanup == "sysmon"
    assert actual.cleanup_bytes == count
    assert actual.disposition == "one_exact_cleanup_candidate_requires_promotion"
    assert actual.mutation_permitted is False


def test_storage_risk_never_proposes_autonomous_cleanup():
    actual = assess(evidence=evidence(sysmon_bytes=5 * GIB, storage_errors=3))
    assert actual.storage_risk is True
    assert actual.cleanup_kind is None
    assert actual.disposition == "storage_health_risk_human_review"


def test_protected_server_requires_review_not_cleanup():
    actual = assess(endpoint={
        **DEVICE, "device_type": {"category": "Server"}},
        evidence=evidence(sysmon_bytes=5 * GIB))
    assert actual.disposition == "protected_device_human_review"
    assert not actual.mutation_permitted


def test_existing_autotask_grace_prevents_duplicate_cleanup():
    actual = assess(source_grace_elapsed=False)
    assert actual.disposition == "waiting_existing_autotask_cleanup"
    assert actual.cleanup_kind is None


def test_monitor_cleared_requires_readback_not_cleanup():
    actual = assess(authoritative_low_disk_monitor_open=False)
    assert actual.disposition == "monitor_cleared_verify_ticket"
    assert not actual.mutation_permitted


def test_protected_software_distribution_never_selected():
    e = evidence(sysmon_bytes=0)
    e["software_distribution"] = [{"Bytes": 6 * GIB}]
    actual = assess(evidence=e)
    assert actual.cleanup_kind is None
    assert actual.disposition == "capacity_review"


def test_uncertain_dependency_suppresses_cleanup():
    actual = assess(
        evidence=evidence(sysmon_bytes=5 * GIB),
        evidence_failures=["sysmon_dependencies"])
    assert actual.cleanup_kind is None
    assert actual.disposition == "evidence_inconclusive_human_review"


def test_not_online_holds_without_reading_incomplete_evidence():
    actual = assess(endpoint={**DEVICE, "online": False}, evidence={})
    assert actual.disposition == "waiting_device_access"


@pytest.mark.parametrize("kwargs", [
    {"exact_client_id": "wrong"},
    {"exact_device_uid": "other"},
    {"exact_drive_letter": "D:"},
    {"current_volume": {"DriveLetter": "C", "Size": -1, "SizeRemaining": 1}},
    {"current_volume": {"DriveLetter": "C", "Size": 10, "SizeRemaining": 20}},
    {"authoritative_low_disk_monitor_open": "true"},
    {"evidence": {"physical_disks": []}},
])
def test_missing_identity_or_authoritative_evidence_blocks(kwargs):
    with pytest.raises(JsonLowDiskBoundaryError):
        assess(**kwargs)


def test_json_low_disk_mutation_is_not_authorized_by_source_facts():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    doc = validate_playbook_document(json.loads(
        (Path(__file__).resolve().parents[3] /
         "docs/playbooks/json/migration/candidates/low_disk_space.v1.json").read_text()))
    j = JsonPlaybookInterpreter(doc)
    assert j.instruction(step_id="ticket_gate", facts={}).step_id == "human_review"
    assert j.instruction(step_id="grace_gate", facts={}).step_id == "wait_grace"
    assert j.instruction(step_id="classification_gate", facts={}).step_id == "human_review"
    assert j.instruction(step_id="cleanup_approval", facts={}).step_id == "human_review"
    assert j.instruction(step_id="after_gate", facts={}).step_id == "human_review"
    action = j.instruction(
        step_id="cleanup_approval",
        facts={"exact_component_identity_client_owner_grant_and_no_prior_attempt": True,
               "trusted_exact_cleanup_job_arguments": {
                   "device_uid": "synthetic", "component_uid": "fixture-only"}},
    )
    assert action.step_id == "run_cleanup"
    assert action.capability == "automation.component.execute"
    assert action.approval_required
    assert action.approval_classification == "modifying"
