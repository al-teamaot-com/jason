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
