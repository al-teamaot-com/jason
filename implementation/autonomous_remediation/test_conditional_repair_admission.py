"""Source-only, provider-free acceptance cases for conditional repair admission."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from .conditional_repair_admission import (
    AdmissionState,
    CertifiedRepairPolicy,
    RepairObservation,
    evaluate_repair_admission,
)


NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)
UID = "71463154-6eee-4f8c-a537-75b109727293"
NAME = "Start system repair (SFC / DISM) AOT Ver 05292024"
HASH = "a" * 64


def verified_policy(**changes):
    baseline = CertifiedRepairPolicy(
        component_uid=UID,
        component_name=NAME,
        certified_script_sha256=HASH,
        approved_playbook_id="windows_integrity_repair",
        approved_playbook_version="1.0.0",
        active=True,
        script_review_passed=True,
        no_reboot_or_disruption_certified=True,
        durable_playbook_approval_verified=True,
        max_cpu_percent=30.0,
        max_disk_busy_percent=30.0,
        min_free_gb=10.0,
        max_observation_age_seconds=300,
    )
    return replace(baseline, **changes)


def verified_observation(**changes):
    baseline = RepairObservation(
        ticket_id="T-123",
        device_uid="device-xyz",
        ticket_bound_device_uid="device-xyz",
        ticket_client_id="client-a",
        device_client_id="client-a",
        component_uid=UID,
        component_name=NAME,
        live_script_sha256=HASH,
        playbook_id="windows_integrity_repair",
        playbook_version="1.0.0",
        os_family="windows",
        repair_evidence_codes=frozenset({"sfc_corruption_confirmed"}),
        observed_at=NOW,
        online=True,
        user_idle=True,
        cpu_percent=5.0,
        disk_busy_percent=7.0,
        free_gb=30.0,
        on_ac_power=True,
        existing_repair_job=False,
        incident_repair_attempts=0,
        reboot_requested=False,
    )
    return replace(baseline, **changes)


def test_full_verified_fixture_allows_proposal_not_dispatch():
    result = evaluate_repair_admission(
        verified_policy(), verified_observation(), now=NOW,
    )
    assert result.state is AdmissionState.READY_FOR_GOVERNANCE
    assert result.may_propose_to_governance is True
    assert result.reasons == ()


def test_default_policy_is_disabled_even_with_perfect_machine_evidence():
    policy = replace(verified_policy(), active=False)
    result = evaluate_repair_admission(policy, verified_observation(), now=NOW)
    assert result.state is AdmissionState.BLOCKED
    assert "AUTONOMOUS_REPAIR_DISABLED" in result.reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"script_review_passed": False}, "SCRIPT_SAFETY_CERTIFICATION_REQUIRED"),
        ({"no_reboot_or_disruption_certified": False}, "SCRIPT_SAFETY_CERTIFICATION_REQUIRED"),
        ({"durable_playbook_approval_verified": False}, "DURABLE_PLAYBOOK_AUTHORITY_REQUIRED"),
        ({"component_uid": "other"}, "COMPONENT_IDENTITY_MISMATCH"),
        ({"component_name": "Renamed component"}, "COMPONENT_IDENTITY_MISMATCH"),
        ({"approved_playbook_version": "2.0.0"}, "PLAYBOOK_VERSION_MISMATCH"),
        ({"certified_script_sha256": "b" * 64}, "LIVE_SCRIPT_REVISION_UNVERIFIED"),
        ({"certified_script_sha256": ""}, "LIVE_SCRIPT_REVISION_UNVERIFIED"),
        ({"max_cpu_percent": None}, "RESOURCE_LIMIT_NOT_CONFIGURED"),
        ({"max_disk_busy_percent": None}, "RESOURCE_LIMIT_NOT_CONFIGURED"),
        ({"min_free_gb": None}, "FREE_SPACE_LIMIT_NOT_CONFIGURED"),
        ({"min_free_gb": float("nan")}, "FREE_SPACE_LIMIT_NOT_CONFIGURED"),
        ({"max_cpu_percent": float("nan")}, "RESOURCE_LIMIT_NOT_CONFIGURED"),
    ],
)
def test_unverified_policy_blocks(changes, reason):
    result = evaluate_repair_admission(
        verified_policy(**changes), verified_observation(), now=NOW,
    )
    assert result.state is AdmissionState.BLOCKED
    assert result.may_propose_to_governance is False
    assert reason in result.reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"component_uid": "other"}, "COMPONENT_IDENTITY_MISMATCH"),
        ({"component_name": "Renamed component"}, "COMPONENT_IDENTITY_MISMATCH"),
        ({"live_script_sha256": "b" * 64}, "LIVE_SCRIPT_REVISION_UNVERIFIED"),
        ({"live_script_sha256": "not-a-sha"}, "LIVE_SCRIPT_REVISION_UNVERIFIED"),
        ({"ticket_client_id": "client-b"}, "TICKET_DEVICE_SCOPE_MISMATCH"),
        ({"ticket_id": ""}, "TICKET_DEVICE_SCOPE_MISMATCH"),
        ({"device_uid": ""}, "TICKET_DEVICE_SCOPE_MISMATCH"),
        ({"ticket_bound_device_uid": "different-device"}, "TICKET_DEVICE_SCOPE_MISMATCH"),
        ({"os_family": "linux"}, "OS_NOT_ELIGIBLE"),
        ({"repair_evidence_codes": frozenset({"computer_sluggish"})}, "CONFIRMED_CORRUPTION_EVIDENCE_REQUIRED"),
        ({"repair_evidence_codes": frozenset()}, "CONFIRMED_CORRUPTION_EVIDENCE_REQUIRED"),
        ({"playbook_version": "2.0.0"}, "PLAYBOOK_VERSION_MISMATCH"),
        ({"reboot_requested": True}, "REBOOT_REQUEST_NOT_ALLOWED"),
        ({"reboot_requested": None}, "REBOOT_REQUEST_NOT_ALLOWED"),
        ({"incident_repair_attempts": 1}, "REPAIR_ATTEMPT_ALREADY_CONSUMED"),
    ],
)
def test_hard_safety_conflicts_block(changes, reason):
    result = evaluate_repair_admission(
        verified_policy(), verified_observation(**changes), now=NOW,
    )
    assert result.state is AdmissionState.BLOCKED
    assert result.may_propose_to_governance is False
    assert reason in result.reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"observed_at": None}, "CURRENT_DEVICE_OBSERVATION_REQUIRED"),
        ({"observed_at": NOW - timedelta(minutes=10)}, "CURRENT_DEVICE_OBSERVATION_REQUIRED"),
        ({"observed_at": NOW + timedelta(seconds=20)}, "CURRENT_DEVICE_OBSERVATION_REQUIRED"),
        ({"online": None}, "WAIT_DEVICE_ONLINE"),
        ({"online": False}, "WAIT_DEVICE_ONLINE"),
        ({"user_idle": None}, "WAIT_VERIFIED_IDLE_USER"),
        ({"user_idle": False}, "WAIT_VERIFIED_IDLE_USER"),
        ({"on_ac_power": None}, "WAIT_SAFE_POWER_STATE"),
        ({"on_ac_power": False}, "WAIT_SAFE_POWER_STATE"),
        ({"existing_repair_job": None}, "WAIT_EXISTING_REPAIR_JOB"),
        ({"existing_repair_job": True}, "WAIT_EXISTING_REPAIR_JOB"),
        ({"cpu_percent": 95.0}, "WAIT_CPU_IDLE"),
        ({"cpu_percent": None}, "WAIT_CPU_IDLE"),
        ({"cpu_percent": float("nan")}, "WAIT_CPU_IDLE"),
        ({"disk_busy_percent": 70.0}, "WAIT_DISK_IDLE"),
        ({"disk_busy_percent": None}, "WAIT_DISK_IDLE"),
        ({"free_gb": 3.0}, "WAIT_SUFFICIENT_FREE_SPACE"),
        ({"free_gb": None}, "WAIT_SUFFICIENT_FREE_SPACE"),
        ({"free_gb": float("nan")}, "WAIT_SUFFICIENT_FREE_SPACE"),
    ],
)
def test_retryable_operational_state_defers_without_dispatch(changes, reason):
    result = evaluate_repair_admission(
        verified_policy(), verified_observation(**changes), now=NOW,
    )
    assert result.state is AdmissionState.DEFERRED
    assert result.may_propose_to_governance is False
    assert reason in result.reasons


@pytest.mark.parametrize(
    "signal",
    [
        "sfc_corruption_confirmed",
        "dism_component_store_corruption_confirmed",
        "windows_servicing_corruption_confirmed",
    ],
)
def test_only_independently_verified_corruption_triggers(signal):
    result = evaluate_repair_admission(
        verified_policy(),
        verified_observation(repair_evidence_codes=frozenset({signal})),
        now=NOW,
    )
    assert result.may_propose_to_governance is True
