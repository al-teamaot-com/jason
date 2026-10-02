from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RECONCILE = REPO_ROOT / "tools" / "reconcile_production_host_services.sh"

EXPORTER_UNITS = (
    "jason-client-posture-exporter.service",
    "jason-playbook-exporter.service",
    "jason-production-health-exporter.service",
    "jason-resolution-memory-exporter.service",
    "jason-reflection-exporter.service",
    "jason-security-control-exporter.service",
    "jason-status-exporter.service",
    "jason-usage-attribution-exporter.service",
    "jason-usage-exporter.service",
)
MAINTENANCE_UNITS = (
    "jason-delegation-maintenance.service",
    "jason-openclaw-authority-health.service",
    "jason-documentation-reconciliation.service",
)
MAINTENANCE_TIMERS = (
    "jason-delegation-maintenance.timer",
    "jason-openclaw-authority-health.timer",
    "jason-documentation-reconciliation.timer",
)
OBSOLETE_UNITS = (
    "jason-communication-template-exporter.service",
    "jason-completion-gap-exporter.service",
    "jason-component-engineering-exporter.service",
    "jason-prompt-exporter.service",
)


def test_canonical_host_units_use_immutable_release_path() -> None:
    for unit in EXPORTER_UNITS:
        path = REPO_ROOT / "infrastructure" / "showcase" / "systemd" / unit
        text = path.read_text(encoding="utf-8")
        assert "/opt/jason/current" in text
        assert "/home/al/projects/jason" not in text
        assert "/home/al/jason-worktrees/" not in text

    for unit in MAINTENANCE_UNITS:
        path = (
            REPO_ROOT
            / "infrastructure"
            / "openclaw-operations"
            / "systemd"
            / unit
        )
        text = path.read_text(encoding="utf-8")
        assert "WorkingDirectory=/opt/jason/current" in text
        assert "ReadOnlyPaths=/opt/jason/current" in text
        assert "/home/al/projects/jason" not in text
        assert "/home/al/jason-worktrees/" not in text


def test_reconciliation_contract_covers_all_known_host_drift() -> None:
    text = RECONCILE.read_text(encoding="utf-8")

    for unit in EXPORTER_UNITS + MAINTENANCE_UNITS + MAINTENANCE_TIMERS + OBSOLETE_UNITS:
        assert unit in text

    assert 'LIVE_MCP_REVISION' in text
    assert 'live MCP revision does not match requested host release' in text
    assert 'ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"' in text
    assert 'systemctl disable --now "$unit"' in text
    assert 'pgrep -u "$SERVICE_USER" -f "$script_name"' in text
    assert 'developer checkout dependency remains in $unit' in text
    assert '/home/al/' not in text
    assert 'JASON_HOST_SERVICE_RECONCILIATION=PASS' in text
    assert 'publish_documentation_reconciliation.sh' in text
    assert 'POST_SUCCESS_DOCUMENTATION_RECONCILIATION=PASS' in text
    assert 'production succeeded but documentation reconciliation publication failed' in text


def test_reconciliation_fails_closed_without_root() -> None:
    revision = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = subprocess.run(
        ["bash", str(RECONCILE), revision],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 77
    assert "root privileges are required" in result.stderr
