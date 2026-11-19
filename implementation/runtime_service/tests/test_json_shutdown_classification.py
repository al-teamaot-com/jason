"""Source-reused Windows shutdown read-only classifier negative/positive parity."""
import pytest

from jason_runtime.json_shutdown_classification import (
    ShutdownJsonBoundaryError, classify_shutdown_json_readonly,
)
from jason_runtime.unexpected_shutdown_analysis import (
    classify_site_scope, shutdown_character, site_event_id, storage_health_risk,
)

EVENT = 1795070000000
ENDPOINT = {
    "resource_id": "endpoint-1", "companyID": "777",
    "site_uid": "site-1", "online": True,
    "device_type": {"category": "Desktop"},
}
HEALTHY_DISK = {"HealthStatus": "Healthy", "OperationalStatus": "OK"}


def peer(uid, *, shift=60, vm=False, company="777", site="site-1"):
    return {
        "resource_id": uid, "companyID": company,
        "site_uid": site, "is_virtual": vm,
        "incident_timestamp_ms": EVENT + shift * 1000,
    }


def assess(**changes):
    data = {
        "exact_client_id": "777", "target_uid": "endpoint-1",
        "target_site_uid": "site-1",
        "endpoint": ENDPOINT,
        "incident_timestamp_ms": EVENT,
        "peer_shutdowns": [peer("endpoint-2"), peer("endpoint-3", shift=-120)],
        "windows_events": [{"Id": 6008}],
        "whea_events": [],
        "physical_disks": [HEALTHY_DISK],
        "reliability": [{"ReadErrorsTotal": 0, "WriteErrorsTotal": 0}],
        "volumes": [{"HealthStatus": "Healthy"}],
        "independent_recurring_incidents": 0,
        "health_evidence_complete": True,
    }
    data.update(changes)
    return classify_shutdown_json_readonly(**data)


def test_three_same_site_physical_peers_source_classifier_and_stable_incident():
    row = assess()
    assert row.site_scope == classify_site_scope(
        affected_physical_devices=3, active_physical_devices=3)
    assert row.shutdown_character == shutdown_character([{"Id": 6008}])
    assert row.disposition == "site_environmental_classified"
    assert row.site_incident_id == site_event_id("site-1", EVENT - 120000)
    assert not row.storage_risk
    assert row.live_mutations == 0


def test_virtual_machine_cannot_establish_three_physical_device_threshold():
    row = assess(peer_shutdowns=[
        peer("endpoint-2"), peer("vm-3", vm=True)])
    assert row.site_scope == "SITE_CORRELATED_SMALL_SITE"
    assert row.disposition == "site_correlated_small_site_review"
    assert row.affected_physical_devices == 2
    assert row.excluded_vm_count == 1


@pytest.mark.parametrize("risk", [
    {"windows_events": [{"Id": 6008}, {"Id": 7}]},
    {"whea_events": [{"Id": 18}]},
    {"physical_disks": [{"HealthStatus": "Unhealthy"}]},
    {"reliability": [{"ReadErrorsTotal": 3}]},
    {"volumes": [{"HealthStatus": "Failed"}]},
])
def test_hardware_or_storage_risk_blocks_clean_site_closure(risk):
    row = assess(**risk)
    assert row.disposition == "device_specific_risk"
    assert row.storage_risk is True
    assert row.risk_reasons


def test_protected_role_never_autonomously_closes():
    row = assess(endpoint={**ENDPOINT, "device_type": {"category": "Server"}})
    assert row.disposition == "protected_role_review"


def test_recurrence_and_unknown_character_remain_human_review():
    assert assess(independent_recurring_incidents=2).disposition == "recurring_issue"
    assert assess(windows_events=[]).disposition == "evidence_inconclusive"


def test_offline_device_never_autonomously_closes():
    row = assess(endpoint={**ENDPOINT, "online": False})
    assert row.disposition == "waiting_device_access"


@pytest.mark.parametrize("invalid", [
    {"exact_client_id": "other"},
    {"target_uid": "other"},
    {"target_site_uid": "other"},
    {"health_evidence_complete": False},
    {"peer_shutdowns": [peer("endpoint-2", company="other")]},
    {"peer_shutdowns": [peer("endpoint-2", site="foreign")]},
    {"peer_shutdowns": [peer("endpoint-2", shift=60, vm=None)] * 101},
])
def test_cross_scope_missing_evidence_and_unbounded_peers_fail_closed(invalid):
    with pytest.raises(ShutdownJsonBoundaryError):
        assess(**invalid)


def test_peer_outside_fifteen_minute_window_is_excluded():
    result = assess(peer_shutdowns=[
        peer("endpoint-2", shift=60),
        peer("endpoint-3", shift=960)])
    assert result.affected_physical_devices == 2
    assert result.site_scope == "SITE_CORRELATED_SMALL_SITE"


def test_canonical_json_shutdown_actions_are_separately_approval_bound():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    candidate = (Path(__file__).resolve().parents[3] /
                 "docs/playbooks/json/migration/candidates/unexpected_shutdown.v1.json")
    runner = JsonPlaybookInterpreter(
        validate_playbook_document(json.loads(candidate.read_text())))
    assert runner.instruction(step_id="classification", facts={}).step_id == "human_review"
    assert runner.instruction(
        step_id="classification",
        facts={"verified_shutdown_disposition": "device_specific_risk"},
    ).step_id == "human_review"
    assert runner.instruction(
        step_id="classification",
        facts={"verified_shutdown_disposition": "site_environmental_classified"},
    ).step_id == "human_review"
    action = runner.instruction(
        step_id="classification",
        facts={
            "verified_shutdown_disposition": "site_environmental_classified",
            "all_devices_no_storage_risk_and_exact_owner_promotion": True,
            "trusted_exact_internal_note_create_args": {
                "payload": {"ticketID": 321, "title": "Synthetic",
                            "description": "No provider call"}},
        },
    )
    assert action.step_id == "create_internal_note"
    assert action.approval_required
    assert action.capability == "service.ticket.note.create"
    assert runner.instruction(step_id="note_gate", facts={}).step_id == "human_review"
    assert runner.instruction(step_id="ticket_gate", facts={}).step_id == "human_review"
