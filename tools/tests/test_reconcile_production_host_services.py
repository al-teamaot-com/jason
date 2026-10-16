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
    assert 'pgrep -u al -f "$script_name"' not in text
    assert 'PORT_GUARD="$RELEASE_DIR/tools/release_exporter_port_guard.py"' in text
    assert '--mode free --unit "$unit" --timeout-seconds 12' in text
    assert '--mode owned --unit "$unit" --timeout-seconds 30' in text
    assert 'HOST_RECONCILE_FAILURE step=' in text
    assert 'kill "$pid"' not in text
    assert text.index('--mode free --unit') < text.index('--mode owned --unit')
    assert text.index('timeout --signal=TERM --kill-after=5s 25s systemctl stop') < text.index('--mode free --unit')
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
    assert 'install_release_control_transition.py' in text
    assert 'installed root release-transition worker differs from production source' in text
    assert 'jason-release-control-transition.timer' in text
    assert 'root release-transition timer is not active after production install' in text
    assert 'JASON_ROOT_RELEASE_TRANSITION_RECONCILIATION=PASS' in text
    assert text.index('install_release_control_transition.py') < text.index('install_release_host_reconciler.py')
    assert 'install_release_host_reconciler.py' in text
    assert 'installed root host reconciler differs from production source' in text
    assert 'JASON_ROOT_HOST_RECONCILER_RECONCILIATION=PASS' in text
    assert 'HOST_RECONCILE_STEP_START=' in text
    assert 'HOST_RECONCILE_STEP_PASS=' in text
    assert 'verify_exporter_port()' in text
    assert 'for attempt in 1 2 3' in text
    assert 'curl --connect-timeout 2 --max-time 15 -fsS' in text
    assert 'exporter verification failed on port $port after 3 bounded attempts' in text
    assert 'timeout --signal=TERM --kill-after=5s 120s systemctl start "$unit"' in text
    assert 'timeout --signal=TERM --kill-after=5s 180s systemctl start "$unit"' in text
    assert 'if [ "$unit" = "jason-openclaw-authority-health.service" ]; then' in text
    assert text.index('timeout --signal=TERM --kill-after=5s 180s systemctl start "$unit"') < text.index('timeout --signal=TERM --kill-after=5s 120s systemctl start "$unit"')
    assert 'HOST_RECONCILE_FAILURE step=' in text
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
    assert "jason-operations-configuration-exporter.service" in text
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


def test_unmanaged_toner_exporter_is_removed_during_production_reconciliation() -> None:
    text = RECONCILE.read_text(encoding="utf-8")
    assert "jason-toner-exporter.service" in text
    assert "systemctl --user disable --now" in text
    assert "JASON_OBSOLETE_USER_UNIT_CLEANUP=PASS" in text
    assert "/home/al/.config/systemd/user/default.target.wants/$unit" in text


def test_forbidden_developer_path_user_units_are_removed() -> None:
    text = RECONCILE.read_text(encoding="utf-8")
    for unit in (
        "jason-autonomous-repair-runner.service",
        "jason-autonomous-repair-runner.path",
        "jason-resolution-memory-exporter.service",
        "jason-playbook-exporter.service",
        "jason-pr-integration-reconciler.service",
        "jason-pr-integration-reconciler.timer",
    ):
        assert unit in text
    assert "systemctl --user disable --now" in text
    assert "JASON_OBSOLETE_USER_UNIT_CLEANUP=PASS" in text


def test_production_drift_watchdog_is_installed_after_cleanup() -> None:
    text = RECONCILE.read_text(encoding="utf-8")
    assert "jason-production-drift-watchdog.service" in text
    assert "jason-production-drift-watchdog.timer" in text
    assert "production_drift_guard.py" in text
    assert "JASON_PRODUCTION_DRIFT_GUARD=PASS" in text
    assert "JASON_ROLLBACK_CONTAINER_RETENTION=PASS" in text
    assert "systemctl --user reset-failed" in text


def _recovered_exporter_probe(tmp_path: Path, mode: str) -> tuple[int, str, list[str]]:
    """Execute the actual bounded shell helper with fake stateless host tools.

    Only tool paths are swapped to local fixtures. No systemd, Docker or
    production service is contacted.
    """
    import os

    script = RECONCILE.read_text(encoding="utf-8")
    start = script.index("ensure_owned_exporter() {")
    end = script.index('\nfor unit in "${EXPORTER_UNITS[@]}"; do', start)
    helper = script[start:end].replace(
        '/usr/bin/python3 "$PORT_GUARD"', 'python3 "$PORT_GUARD"'
    )
    guard = tmp_path / "fake_guard.py"
    guard.write_text(
        """
import os, sys
from pathlib import Path
log = Path(os.environ["PROBE_LOG"])
calls = log.read_text().splitlines() if log.exists() else []
check = sys.argv[sys.argv.index("--mode") + 1]
calls.append("guard " + check)
log.write_text("\\n".join(calls) + "\\n")
if check == "free":
    print("EXPORTER_PORT_GUARD=PASS check=free")
    sys.exit(0)
attempt = sum(line == "guard owned" for line in calls)
mode = os.environ["PROBE_MODE"]
if mode == "foreign":
    print("EXPORTER_PORT_GUARD=FAIL detail=owned by a different/unknown process", file=sys.stderr)
    sys.exit(1)
if mode == "persistent" or attempt == 1 or (mode == "queued" and attempt <= 2):
    print("EXPORTER_PORT_GUARD=FAIL detail=port 9464 has no listening owner (MainPID=0)", file=sys.stderr)
    sys.exit(1)
print("EXPORTER_PORT_GUARD=PASS check=owned")
"""
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    timeout = bindir / "timeout"
    timeout.write_text(
        '#!/bin/sh\n'
        'shift 3\n'
        'exec "$@"\n'
    )
    timeout.chmod(0o755)
    systemctl = bindir / "systemctl"
    systemctl.write_text(
        '#!/bin/sh\n'
        'printf "systemctl %s\\n" "$*" >> "$PROBE_LOG"\n'
    )
    # Model a real systemd start job which remains pending during a slow boot.
    systemctl_script = systemctl.read_text()
    systemctl.write_text(systemctl_script +
        'if [ "$1" = "show" ] && [ "$PROBE_MODE" = "queued" ]; then printf "123/start\\n"; fi\n'
    )
    systemctl.chmod(0o755)
    sleep = bindir / "sleep"
    sleep.write_text('#!/bin/sh\nexit 0\n')
    sleep.chmod(0o755)
    env = dict(os.environ)
    env.update({
        "PORT_GUARD": str(guard),
        "PROBE_LOG": str(tmp_path / "calls"),
        "PROBE_MODE": mode,
        "PATH": str(bindir) + os.pathsep + env["PATH"],
    })
    result = subprocess.run(
        ["bash", "-c", "set -eu\n" + helper + "\nensure_owned_exporter jason-status-exporter.service\n"],
        env=env, capture_output=True, text=True, timeout=15,
    )
    events = (tmp_path / "calls").read_text().splitlines()
    return result.returncode, result.stderr, events


def test_exporter_ownership_guard_can_recover_only_verified_empty_socket(tmp_path: Path) -> None:
    status, stderr, events = _recovered_exporter_probe(tmp_path, "transient")
    assert status == 0, stderr
    assert events == [
        "guard owned", "guard free",
        "systemctl show jason-status-exporter.service --property=Job --value",
        "systemctl restart --no-block jason-status-exporter.service",
        "guard owned",
    ]


def test_exporter_ownership_guard_waits_for_queued_job_without_restart(tmp_path: Path) -> None:
    status, stderr, events = _recovered_exporter_probe(tmp_path, "queued")
    assert status == 0, stderr
    assert "EXPORTER_OWNERSHIP_RECONCILIATION=WAIT" in stderr
    assert events == [
        "guard owned", "guard free",
        "systemctl show jason-status-exporter.service --property=Job --value",
        "guard owned", "guard free",
        "systemctl show jason-status-exporter.service --property=Job --value",
        "guard owned",
    ]


def test_exporter_ownership_guard_rejects_foreign_owner_without_restart(tmp_path: Path) -> None:
    status, stderr, events = _recovered_exporter_probe(tmp_path, "foreign")
    assert status != 0
    assert "EXPORTER_OWNERSHIP_RECONCILIATION=FAIL" in stderr
    assert events == ["guard owned"]


def test_exporter_ownership_guard_persistent_absence_stays_fatal(tmp_path: Path) -> None:
    status, stderr, events = _recovered_exporter_probe(tmp_path, "persistent")
    assert status != 0
    assert "EXPORTER_OWNERSHIP_RECONCILIATION=FAIL" in stderr
    assert events.count("guard owned") == 4
    assert events.count("guard free") == 3
    assert events.count("systemctl show jason-status-exporter.service --property=Job --value") == 3
    assert events.count("systemctl restart --no-block jason-status-exporter.service") == 3

def test_exporter_activation_queues_nonblocking_start_and_waits_for_real_port_owner() -> None:
    text = RECONCILE.read_text(encoding="utf-8")
    assert 'systemctl enable --now "$unit"' not in text
    assert 'systemctl start --no-block "$unit"' in text
    assert 'systemctl restart --no-block "$unit"' in text
    assert 'timeout --signal=TERM --kill-after=5s 15s systemctl enable "$unit"' in text
    assert 'timeout --signal=TERM --kill-after=5s 15s systemctl start --no-block "$unit"' in text
    assert 'timeout --signal=TERM --kill-after=5s 15s systemctl restart --no-block "$unit"' in text
    assert text.index('systemctl start --no-block "$unit"') < text.index('ensure_owned_exporter "$unit"')
    assert text.index('ensure_owned_exporter "$unit"') < text.index('if [ "$(systemctl is-active "$unit")" != "active" ]')
