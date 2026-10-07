from __future__ import annotations

import json
from pathlib import Path

import issue_resolution_engine as engine


def test_production_symptoms_collapse_into_one_root_incident():
    incidents = engine.correlate_failures(
        [
            "production_convergence_scheduled_artifact_drift:self_heal_watchdog",
            "container_down:jason-runtime",
            "failed_user_unit:jason-self-heal-watchdog.service",
        ]
    )

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["family"] == "production_convergence"
    assert len(incident["symptoms"]) == 3
    assert incident["repair"]["level"] == 2
    assert incident["repair"]["requires_owner_action"] is False
    assert "runtime SHA = MCP SHA" in incident["root_invariant"]


def test_provider_canary_is_separate_from_ticket_admission():
    incidents = engine.correlate_failures(
        [
            'health_metric:jason_provider_canary_health{provider="microsoft_graph"}',
            "autonomy_admission_stalled:eligible_work_not_selected",
        ]
    )
    assert [item["family"] for item in incidents] == ["provider_health", "ticket_admission"]


def test_safe_repair_exhaustion_does_not_imply_owner_action():
    incident = engine.correlate_failures(
        ["production_convergence_scheduled_artifact_drift:self_heal_watchdog"]
    )[0]
    assert incident["repair"]["level"] == 2
    assert incident["repair"]["automatic_execution"] is True
    assert incident["repair"]["requires_owner_action"] is False


def test_real_authority_boundary_requires_owner_action():
    incident = engine.correlate_failures(
        ["provider_authority_required:microsoft_graph:admin_consent_required"]
    )[0]
    assert incident["repair"]["level"] == 4
    assert incident["repair"]["requires_owner_action"] is True


def test_recurrence_counts_only_after_clear_and_reappear(tmp_path):
    memory = tmp_path / "memory.json"
    first = engine.correlate_failures(["autonomy_admission_stalled:eligible_work_not_selected"])
    first = engine.update_recurrence_memory(memory, first, observed_at="2026-10-07T10:00:00+00:00")
    assert first[0]["occurrence_count"] == 1
    assert first[0]["recurring"] is False

    still_active = engine.correlate_failures(["autonomy_admission_stalled:eligible_work_not_selected"])
    still_active = engine.update_recurrence_memory(
        memory, still_active, observed_at="2026-10-07T10:05:00+00:00"
    )
    assert still_active[0]["occurrence_count"] == 1

    engine.update_recurrence_memory(memory, [], observed_at="2026-10-07T10:10:00+00:00")
    recurring = engine.correlate_failures(["autonomy_admission_stalled:eligible_work_not_selected"])
    recurring = engine.update_recurrence_memory(
        memory, recurring, observed_at="2026-10-07T10:15:00+00:00"
    )
    assert recurring[0]["occurrence_count"] == 2
    assert recurring[0]["recurring"] is True
    assert recurring[0]["architectural_correction_required"] is True
    assert recurring[0]["priority"] == "P0"
    assert "architectural correction" in engine.acceptance_text(recurring[0])


def test_verification_contract_requires_detector_recheck():
    incident = engine.correlate_failures(
        ["outcome_contract_overdue:client_notification:notify-123"]
    )[0]
    contract = incident["verification_contract"]
    assert contract["closure_requires_detector_recheck"] is True
    assert contract["must_clear_family"] == "operational_outcome"
    assert any("original outcome verifier" in item for item in contract["required_checks"])


def test_memory_file_is_auditable_json(tmp_path):
    path = tmp_path / "memory.json"
    incidents = engine.update_recurrence_memory(
        path,
        engine.correlate_failures(["container_down:jason-runtime"]),
        observed_at="2026-10-07T10:00:00+00:00",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["families"]["runtime_health"]["occurrence_count"] == 1
    assert incidents[0]["priority"] == "P1"
