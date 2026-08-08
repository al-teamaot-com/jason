from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_exporter():
    path = Path(__file__).resolve().parents[1] / "status_exporter.py"
    spec = importlib.util.spec_from_file_location("jason_status_exporter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_operational_health_metrics_are_secret_safe_and_bounded(tmp_path, monkeypatch):
    module = load_exporter()
    health = tmp_path / "operational-health.json"
    health.write_text(
        json.dumps(
            {
                "status": "pass",
                "delegations": {"active": 2, "expired_active_records": 1, "inactive": 3},
                "trusted_key_registry": {"active_records": 2, "mode": "0o600", "present": True},
                "backup_restore_proof": {
                    "backup_integrity": "ok",
                    "restore_integrity": "ok",
                    "counts_match": True,
                },
            }
        ),
        encoding="utf-8",
    )
    module.OPENCLAW_AUTHORITY_HEALTH_PATH = health
    monkeypatch.setattr(module, "_docker_running", lambda _name: False)
    monkeypatch.setattr(module, "_tcp_open", lambda _host, _port: False)
    monkeypatch.setattr(module, "_ollama_model_ready", lambda _model: False)
    monkeypatch.setattr(module, "_roadmap", lambda: {"milestones": []})

    metrics = module.render_metrics()

    assert "jason_openclaw_authority_operational_health 1" in metrics
    assert "jason_openclaw_trusted_signing_keys 2" in metrics
    assert 'jason_openclaw_delegations{state="active"} 2' in metrics
    assert 'jason_openclaw_delegations{state="expired_active_records"} 1' in metrics
    assert "jason_authority_backup_restore_proof 1" in metrics
    assert "fingerprint" not in metrics.lower()
    assert "public_key" not in metrics.lower()


def test_missing_snapshot_fails_health_closed(monkeypatch, tmp_path):
    module = load_exporter()
    module.OPENCLAW_AUTHORITY_HEALTH_PATH = tmp_path / "missing.json"
    monkeypatch.setattr(module, "_docker_running", lambda _name: False)
    monkeypatch.setattr(module, "_tcp_open", lambda _host, _port: False)
    monkeypatch.setattr(module, "_ollama_model_ready", lambda _model: False)
    monkeypatch.setattr(module, "_roadmap", lambda: {"milestones": []})

    metrics = module.render_metrics()
    assert "jason_openclaw_authority_operational_health 0" in metrics
    assert "jason_openclaw_authority_snapshot_age_seconds -1" in metrics
