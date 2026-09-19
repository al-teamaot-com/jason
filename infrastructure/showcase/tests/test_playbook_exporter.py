import json
from pathlib import Path

from playbook_exporter import render_metrics


def test_playbook_metrics_are_aggregated_without_ticket_or_device_labels(tmp_path: Path):
    registry = tmp_path / "registry.json"
    events = tmp_path / "events.jsonl"
    registry.write_text(
        json.dumps(
            {
                "playbooks": [
                    {
                        "id": "datto_edr_av",
                        "name": "Jason - Datto EDR/AV Diagnose & Repair",
                        "version": "1.2.0",
                        "lifecycle": "pilot",
                        "enabled": True,
                        "review_status": "healthy",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "timestamp": "2026-09-18T12:00:00Z",
            "playbook_id": "datto_edr_av",
            "ticket_id": "TSECRET",
            "device_id": "DEVICESECRET",
            "outcome": "resolved",
            "classification": "health_and_threat",
            "security_disposition": "resolved",
            "compromise_signal": "not_established",
            "verification_passed": True,
            "attempt_count": 3,
            "duration_seconds": 420,
            "evidence_sources": ["drmm_component", "datto_edr_api", "datto_av_scan"],
            "steps": [
                {"name": "health_check", "result": "pass"},
                {"name": "quick_scan", "result": "pass"},
            ],
        },
        {
            "timestamp": "2026-09-18T13:00:00Z",
            "playbook_id": "datto_edr_av",
            "outcome": "escalated",
            "classification": "threat_only",
            "security_disposition": "security_incident_escalation",
            "compromise_signal": "provider_indicated",
            "verification_passed": False,
            "attempt_count": 1,
            "duration_seconds": 90,
            "evidence_sources": ["datto_edr_api"],
            "reopened": True,
        },
    ]
    events.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    metrics = render_metrics(registry_path=registry, events_path=events)

    assert 'jason_playbook_info{playbook_id="datto_edr_av"' in metrics
    assert 'jason_playbook_runs_total{playbook_id="datto_edr_av",outcome="resolved"} 1' in metrics
    assert 'jason_playbook_runs_total{playbook_id="datto_edr_av",outcome="escalated"} 1' in metrics
    assert 'jason_playbook_evidence_source_total{playbook_id="datto_edr_av",source="datto_edr_api"} 2' in metrics
    assert 'jason_playbook_verification_total{playbook_id="datto_edr_av",result="pass"} 1' in metrics
    assert "TSECRET" not in metrics
    assert "DEVICESECRET" not in metrics


def test_active_run_metrics_are_aggregate_and_hide_run_ticket_device_ids(tmp_path: Path):
    registry = tmp_path / "registry.json"
    events = tmp_path / "events.jsonl"
    runs = tmp_path / "runs"
    runs.mkdir()
    registry.write_text(json.dumps({"playbooks":[{"id":"hosts_file_drift","name":"HOSTS Drift","version":"0.1.0","lifecycle":"draft","enabled":False,"review_status":"design"}]}), encoding="utf-8")
    events.write_text("", encoding="utf-8")
    rows = [
        {"run_id":"RUNSECRET1","playbook_id":"hosts_file_drift","playbook_version":"0.1.0","ticket_id":"TSECRET1","company_id":"827","device_id":"DEVICESECRET1","state":"diagnosing","approval_status":"not_required"},
        {"run_id":"RUNSECRET2","playbook_id":"hosts_file_drift","playbook_version":"0.1.0","ticket_id":"TSECRET2","company_id":"827","device_id":"DEVICESECRET2","state":"awaiting_approval","approval_status":"pending","approval_id":"APPROVALSECRET"},
        {"run_id":"RUNSECRET3","playbook_id":"hosts_file_drift","playbook_version":"0.1.0","ticket_id":"TSECRET3","company_id":"827","device_id":"DEVICESECRET3","state":"blocked","approval_status":"not_required","blocked_reason_class":"capability_unavailable"},
        {"run_id":"RUNSECRET4","playbook_id":"hosts_file_drift","playbook_version":"0.1.0","ticket_id":"TSECRET4","company_id":"827","device_id":"DEVICESECRET4","state":"recheck_pending","approval_status":"not_required","recheck_at":"2026-09-19T14:00:00Z"},
        {"run_id":"RUNSECRET5","playbook_id":"hosts_file_drift","playbook_version":"0.1.0","ticket_id":"TSECRET5","company_id":"827","device_id":"DEVICESECRET5","state":"complete","approval_status":"not_required"},
    ]
    for row in rows:
        (runs / f'{row["run_id"]}.json').write_text(json.dumps(row), encoding="utf-8")
    metrics = render_metrics(registry_path=registry, events_path=events, runs_path=runs)
    assert "jason_playbook_active_runs 4" in metrics
    assert 'jason_playbook_active_state{playbook_id="hosts_file_drift",state="diagnosing"} 1' in metrics
    assert 'jason_playbook_active_state{playbook_id="hosts_file_drift",state="awaiting_approval"} 1' in metrics
    assert 'jason_playbook_active_approval{playbook_id="hosts_file_drift",approval_status="pending"} 1' in metrics
    assert 'jason_playbook_blocked_runs{playbook_id="hosts_file_drift",reason_class="capability_unavailable"} 1' in metrics
    assert 'jason_playbook_recheck_pending{playbook_id="hosts_file_drift"} 1' in metrics
    for secret in ("RUNSECRET", "TSECRET", "DEVICESECRET", "APPROVALSECRET"):
        assert secret not in metrics
    assert 'jason_playbook_exporter_build_info{version="2"} 1' in metrics
