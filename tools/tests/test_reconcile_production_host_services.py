from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
RECONCILE = REPO_ROOT / "tools" / "reconcile_production_host_services.sh"

EXPORTER_UNITS = (
    "jason-client-posture-exporter.service",
    "jason-playbook-exporter.service",
    "jason-production-health-exporter.service",
    "jason-operations-configuration-exporter.service",
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
PROVIDER_CANARY_UNITS = (
    "jason-provider-health-canary.service",
    "jason-provider-health-canary.timer",
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

    for unit in EXPORTER_UNITS + MAINTENANCE_UNITS + MAINTENANCE_TIMERS + PROVIDER_CANARY_UNITS + OBSOLETE_UNITS:
        assert unit in text

    assert 'LIVE_MCP_REVISION' in text
    assert 'live MCP revision does not match requested host release' in text
    assert 'ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"' in text
    assert 'systemctl disable --now "$unit"' in text
    assert 'pgrep -u al -f "$script_name"' in text
    assert 'developer checkout dependency remains in $unit' in text
    assert 'JASON_HOST_SERVICE_RECONCILIATION=PASS' in text
    assert 'DEFERRED_MAINTENANCE_SERVICES' in text
    assert 'jason-documentation-reconciliation.service' in text
    assert 'POST_SUCCESS_DOCUMENTATION_RECONCILIATION=DEFERRED_TO_RELEASE_MANAGER' in text
    assert 'publish_documentation_reconciliation.sh' not in text
    assert 'ENGINEERING_SOURCE_REPO="/home/al/.local/lib/jason/engineering-source-repo"' in text
    assert 'DOCUMENTATION_SOURCE_REPO="/home/al/.local/lib/jason/documentation-source-repo"' in text
    assert 'prepare_managed_clone "$ENGINEERING_SOURCE_REPO"' in text
    assert 'prepare_managed_clone "$DOCUMENTATION_SOURCE_REPO"' in text
    assert 'managed documentation Git source was not materialized before unit activation' in text
    assert text.index('prepare_managed_clone "$DOCUMENTATION_SOURCE_REPO"') < text.index('systemctl daemon-reload')
    assert 'install_support_repair_host_worker.py' in text
    assert 'install_self_heal_watchdog.py' in text
    assert 'JASON_USER_WORKER_RECONCILIATION=PASS' in text
    assert 'engineering-worker-source does not match managed production Git source' in text
    assert 'installed worker differs from production source' in text
    assert 'installed self-heal watchdog differs from production source' in text
    assert 'installed issue-resolution engine differs from production source' in text
    assert 'JASON_DOCUMENTATION_REPO_ROOT=/home/al/projects/jason' not in text
    assert 'jason-support-repair-worker.timer' in text
    assert 'jason-self-heal-watchdog.timer' in text
    assert 'install_release_host_reconciler.py' in text
    assert 'installed root host reconciler differs from production source' in text
    assert 'JASON_ROOT_HOST_RECONCILER_RECONCILIATION=PASS' in text
    assert 'HOST_RECONCILE_STEP_START=' in text
    assert 'HOST_RECONCILE_STEP_PASS=' in text
    assert 'curl --connect-timeout 2 --max-time 5 -fsS' in text
    assert 'timeout --signal=TERM --kill-after=5s 120s systemctl start "$unit"' in text
    assert 'timeout --signal=TERM --kill-after=5s 180s env JASON_REPO_ROOT=' in text


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


def test_self_heal_user_unit_has_no_developer_checkout_dependency() -> None:
    path = (
        REPO_ROOT
        / "infrastructure"
        / "openclaw-operations"
        / "systemd"
        / "user"
        / "jason-self-heal-watchdog.service"
    )
    text = path.read_text(encoding="utf-8")
    assert "WorkingDirectory=/opt/jason/current" in text
    assert "ReadOnlyPaths=/opt/jason/current" in text
    assert "ExecStart=/usr/bin/python3 /opt/jason/current/tools/jason_self_heal_watchdog.py" in text
    assert "/home/al/projects/jason" not in text


def test_documentation_reconciliation_namespace_uses_stable_parent_path() -> None:
    path = (
        REPO_ROOT
        / "infrastructure"
        / "openclaw-operations"
        / "systemd"
        / "jason-documentation-reconciliation.service"
    )
    text = path.read_text(encoding="utf-8")
    assert "JASON_DOCUMENTATION_REPO_ROOT=/home/al/.local/lib/jason/documentation-source-repo" in text
    assert "ReadWritePaths=/home/al/jason-worktrees /home/al/.local/lib/jason" in text
    assert "ReadWritePaths=/home/al/jason-worktrees /home/al/.local/lib/jason/documentation-source-repo" not in text


def test_production_reconciliation_has_no_developer_checkout_dependency() -> None:
    text = (REPO_ROOT / "tools" / "reconcile_production_host_services.sh").read_text(encoding="utf-8")
    assert 'REPO_ROOT="/home/al/.local/lib/jason/engineering-source-repo"' in text
    assert "/home/al/projects/jason" not in text


def test_production_reconciliation_emits_candidate_source_boundary_evidence() -> None:
    text = (REPO_ROOT / "tools" / "reconcile_production_host_services.sh").read_text(encoding="utf-8")
    assert 'HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION=$SOURCE_REVISION' in text
    assert 'MANAGED_ENGINEERING_SOURCE=PASS' in text
    assert 'MANAGED_DOCUMENTATION_SOURCE=PASS' in text
    assert 'DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT' in text
    assert 'production reconciliation script contains a developer checkout dependency' in text


def test_control_panel_exporter_is_reconciled_on_dedicated_port() -> None:
    text = RECONCILE.read_text(encoding="utf-8")
    assert "jason-operations-configuration-exporter.service" in text
    assert "operations_configuration_exporter.py" in text
    assert "9477" in text
    unit = (
        REPO_ROOT
        / "infrastructure"
        / "showcase"
        / "systemd"
        / "jason-operations-configuration-exporter.service"
    ).read_text(encoding="utf-8")
    assert "JASON_OPERATIONS_CONFIGURATION_PORT=9477" in unit
    assert "WorkingDirectory=/opt/jason/current" in unit
    assert "/home/al/projects/jason" not in unit


def test_observability_reconciliation_is_conditional_and_managed() -> None:
    text = RECONCILE.read_text(encoding="utf-8")
    assert 'OBSERVABILITY_CURRENT_LINK="/opt/jason/observability/current"' in text
    assert 'OBSERVABILITY_PREVIOUS_REVISION' in text
    assert 'git -C "$REPO_ROOT" diff --quiet' in text
    assert 'infrastructure/showcase' in text
    assert 'config/observability/grafana-dashboard-manifest.json' in text
    assert 'JASON_REPO_ROOT="$ENGINEERING_SOURCE_REPO" /usr/bin/bash "$OBSERVABILITY_INSTALLER" "$SOURCE_REVISION"' in text
    assert 'JASON_OBSERVABILITY_RECONCILIATION=PASS' in text
    assert 'JASON_OBSERVABILITY_RECONCILIATION=UNCHANGED' in text
    assert 'observability release did not converge to production revision' in text
