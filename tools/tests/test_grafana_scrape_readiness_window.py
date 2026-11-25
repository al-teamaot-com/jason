"""Dashboard telemetry remains available but cannot block a Jason release."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_grafana_assurance_is_scheduled_independently_of_host_release():
    host = (ROOT / "tools/reconcile_production_host_services.sh").read_text()
    unit = ROOT / "infrastructure/showcase/systemd/jason-grafana-assurance.timer"
    checker = ROOT / "tools/grafana_assurance.py"
    assert "JASON_OBSERVABILITY_RELEASE_GATE=NOT_REQUIRED" in host
    assert "systemctl start jason-grafana-assurance.service" not in host
    assert "install_observability_assurance.sh" not in host
    assert unit.is_file()
    assert checker.is_file()
    assert "step_start production_drift_guard" in host
