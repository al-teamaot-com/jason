#!/usr/bin/env python3
"""Jason-native production self-heal watchdog.

Detects degraded already-approved Jason functions independently of the normal MCP
request path, performs only bounded non-disruptive recovery, persists a stable
incident fingerprint, feeds unresolved source/operational defects to the native
support-repair lane, and requests governed Teams escalation only after bounded
recovery cannot restore full functionality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sqlite3
import statistics
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from issue_resolution_engine import acceptance_text, correlate_failures, update_recurrence_memory

DEFAULT_ROOT = Path("/var/lib/jason/openclaw/self-heal")
HEALTH_URL = "http://127.0.0.1:9467/metrics"
LOCAL_RECOVERY_CONTAINERS = ("jason-runtime", "jason-mcp-pilot")
MAX_RECOVERY_ATTEMPTS = 2
AUTONOMY_ANOMALY_WINDOW = 12
AUTONOMY_RECENT_WINDOW = 3
OUTCOME_CONTRACT_DIRNAME = "contracts"
AUTONOMY_WORK_DB = Path("/var/lib/jason/openclaw/autonomy-operational-work.sqlite3")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_MANAGER_SOURCE_LINK = Path.home() / ".local/lib/jason/release-manager-source"
RELEASE_MANAGER_RUNNER = Path.home() / ".local/lib/jason/release_manager_host_runner.py"
RELEASE_MANAGER_TIMER = Path.home() / ".config/systemd/user/jason-release-manager.timer"
ENGINEERING_SOURCE_LINK = Path.home() / ".local/lib/jason/engineering-worker-source"
CURRENT_RELEASE_LINK = Path("/opt/jason/current")
ROOT_HOST_RECONCILER = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
SCHEDULED_ARTIFACTS = (
    ("support_repair_worker", "tools/support_repair_host_worker.py", Path.home() / ".local/lib/jason/support_repair_host_worker.py"),
    ("owner_approved_development_worker", "tools/owner_approved_development_worker.py", Path.home() / ".local/lib/jason/owner_approved_development_worker.py"),
    ("todo_engineering_intake", "tools/todo_engineering_intake.py", Path.home() / ".local/lib/jason/todo_engineering_intake.py"),
    ("todo_release_bridge", "tools/todo_release_bridge.py", Path.home() / ".local/lib/jason/todo_release_bridge.py"),
    ("self_heal_watchdog", "tools/jason_self_heal_watchdog.py", Path.home() / ".local/lib/jason/jason_self_heal_watchdog.py"),
    ("issue_resolution_engine", "tools/issue_resolution_engine.py", Path.home() / ".local/lib/jason/issue_resolution_engine.py"),
    ("root_host_reconciler", "tools/release_host_reconcile_worker.py", ROOT_HOST_RECONCILER),
)
REQUIRED_USER_TIMERS = (
    "jason-release-manager.timer",
    "jason-support-repair-worker.timer",
    "jason-self-heal-watchdog.timer",
)
PROVIDER_CANARY_REPORT = Path("/var/lib/jason/provider-health-canaries.json")
PROVIDER_CANARY_MAX_AGE_SECONDS = 30 * 60
EXPECTED_RELEASE_TIMER = "OnCalendar=*-*-* *:00/5:00 America/New_York"

WORKFLOW_STALE_SECONDS = {
    "vulscan_client_notification_verify_complete": 15 * 60,
    "vulscan_client_notification_verify_monitoring": 15 * 60,
    "low_disk_verify": 30 * 60,
}



def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(args: list[str], *, timeout: int = 20, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=check,
    )


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        os.chmod(temp, 0o600)
        json.dump(dict(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _parse_iso8601(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _container_source_revision(name: str) -> str | None:
    result = run(
        [
            "docker",
            "inspect",
            name,
            "--format",
            '{{index .Config.Labels "com.teamaot.jason.source_revision"}}',
        ],
        timeout=10,
    )
    value = result.stdout.strip().casefold() if result.returncode == 0 else ""
    return value if SHA_RE.fullmatch(value) else None


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def production_convergence_failures(
    *,
    release_manager_source_link: Path = RELEASE_MANAGER_SOURCE_LINK,
    installed_runner: Path = RELEASE_MANAGER_RUNNER,
    installed_timer: Path = RELEASE_MANAGER_TIMER,
    releases_root: Path | None = None,
    verify_scheduled_surfaces: bool | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Verify canonical production intent, installed host state, and live runtime agree.

    The live runtime/MCP revision is the production revision. The exact immutable
    release for that revision is the source of truth for Release Manager host
    artifacts. This detects partial deployments and stale host installs without
    guessing at newer source.
    """
    failures: list[str] = []
    evidence: dict[str, Any] = {}
    runtime_revision = _container_source_revision("jason-runtime")
    mcp_revision = _container_source_revision("jason-mcp-pilot")
    evidence["runtime_revision"] = runtime_revision
    evidence["mcp_revision"] = mcp_revision

    if runtime_revision is None or mcp_revision is None:
        failures.append("production_convergence_revision_unavailable")
        return failures, evidence
    if runtime_revision != mcp_revision:
        failures.append("production_convergence_revision_mismatch:runtime_mcp")
        return failures, evidence

    desired_revision = runtime_revision
    if verify_scheduled_surfaces is None:
        verify_scheduled_surfaces = releases_root is None
    release_root = releases_root or Path("/opt/jason/releases")
    release_dir = release_root / desired_revision
    evidence["desired_revision"] = desired_revision
    evidence["release_dir"] = str(release_dir)
    if not release_dir.is_dir():
        failures.append("production_convergence_release_source_missing")
        return failures, evidence

    try:
        installed_source = release_manager_source_link.resolve(strict=True)
    except (FileNotFoundError, OSError):
        installed_source = None
    evidence["release_manager_source"] = str(installed_source) if installed_source else None
    if installed_source != release_dir.resolve():
        failures.append("production_convergence_release_manager_source_drift")

    pairs = (
        ("runner", release_dir / "tools/release_manager_host_runner.py", installed_runner),
        (
            "timer",
            release_dir / "infrastructure/openclaw-operations/systemd/user/jason-release-manager.timer",
            installed_timer,
        ),
    )
    artifact_evidence: dict[str, Any] = {}
    for name, desired, installed in pairs:
        desired_hash = _sha256(desired)
        installed_hash = _sha256(installed)
        artifact_evidence[name] = {
            "desired": str(desired),
            "installed": str(installed),
            "desired_sha256": desired_hash,
            "installed_sha256": installed_hash,
        }
        if desired_hash is None:
            failures.append(f"production_convergence_desired_artifact_missing:{name}")
        elif installed_hash != desired_hash:
            failures.append(f"production_convergence_installed_artifact_drift:{name}")
    evidence["release_manager_artifacts"] = artifact_evidence

    if verify_scheduled_surfaces:
        # Completion means every scheduled implementation and the active host source
        # converge on the same production SHA, not merely runtime/MCP health.
        try:
            current_release = CURRENT_RELEASE_LINK.resolve(strict=True)
        except (FileNotFoundError, OSError):
            current_release = None
        evidence["current_release"] = str(current_release) if current_release else None
        if current_release != release_dir.resolve():
            failures.append("production_convergence_current_release_drift")

        try:
            engineering_source = ENGINEERING_SOURCE_LINK.resolve(strict=True)
        except (FileNotFoundError, OSError):
            engineering_source = None
        evidence["engineering_source"] = str(engineering_source) if engineering_source else None
        engineering_revision = None
        if engineering_source is not None:
            result = run(["git", "-C", str(engineering_source), "rev-parse", "HEAD"], timeout=10)
            candidate = result.stdout.strip().casefold() if result.returncode == 0 else ""
            engineering_revision = candidate if SHA_RE.fullmatch(candidate) else None
        evidence["engineering_source_revision"] = engineering_revision
        if engineering_revision != desired_revision:
            failures.append("production_convergence_engineering_source_drift")

        scheduled_artifacts: dict[str, Any] = {}
        for name, relative, installed in SCHEDULED_ARTIFACTS:
            desired = release_dir / relative
            desired_hash = _sha256(desired)
            installed_hash = _sha256(installed)
            scheduled_artifacts[name] = {
                "desired": str(desired),
                "installed": str(installed),
                "desired_sha256": desired_hash,
                "installed_sha256": installed_hash,
            }
            if desired_hash is None:
                failures.append(f"production_convergence_desired_artifact_missing:{name}")
            elif installed_hash != desired_hash:
                failures.append(f"production_convergence_scheduled_artifact_drift:{name}")
        evidence["scheduled_artifacts"] = scheduled_artifacts

    desired_timer = pairs[1][1]
    timer_text = desired_timer.read_text(encoding="utf-8") if desired_timer.is_file() else ""
    evidence["release_manager_24x7_timer_declared"] = EXPECTED_RELEASE_TIMER in timer_text
    if EXPECTED_RELEASE_TIMER not in timer_text:
        failures.append("production_convergence_intent_contradiction:release_manager_timer_not_24x7")

    policy = read_json(release_dir / "config/release-manager-policy.json")
    schedule = policy.get("schedule") if isinstance(policy.get("schedule"), Mapping) else {}
    coordinator = read_json(release_dir / "config/development-release-coordinator.json")
    production = coordinator.get("production") if isinstance(coordinator.get("production"), Mapping) else {}
    automatic_window = production.get("automatic_window") if isinstance(production.get("automatic_window"), Mapping) else {}
    evidence["release_manager_policy_schedule"] = dict(schedule)
    evidence["development_release_automatic_window"] = dict(automatic_window)
    if str(schedule.get("mode") or "").casefold() != "continuous_24x7":
        failures.append("production_convergence_intent_contradiction:release_policy_not_24x7")
    if "daily_window_local" in schedule:
        failures.append("production_convergence_intent_contradiction:legacy_daily_window_present")
    if str(automatic_window.get("mode") or "").casefold() != "continuous_24x7":
        failures.append("production_convergence_intent_contradiction:coordinator_not_24x7")
    if "local_time" in automatic_window:
        failures.append("production_convergence_intent_contradiction:legacy_coordinator_time_present")

    uid = os.getuid()
    timer_evidence: dict[str, bool] = {}
    for timer_name in REQUIRED_USER_TIMERS:
        timer_state = run(
            [
                "/usr/bin/env",
                f"XDG_RUNTIME_DIR=/run/user/{uid}",
                f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
                "systemctl",
                "--user",
                "is-active",
                timer_name,
            ],
            timeout=10,
        )
        active = timer_state.returncode == 0 and timer_state.stdout.strip() == "active"
        timer_evidence[timer_name] = active
        if not active:
            failures.append(f"production_convergence_required_timer_inactive:{timer_name}")
    evidence["required_user_timers"] = timer_evidence
    evidence["release_manager_timer_active"] = timer_evidence.get("jason-release-manager.timer", False)

    root_path = run(["systemctl", "is-active", "jason-release-host-reconcile.path"], timeout=10)
    root_path_active = root_path.returncode == 0 and root_path.stdout.strip() == "active"
    evidence["root_host_reconcile_path_active"] = root_path_active
    if not root_path_active:
        failures.append("production_convergence_root_host_reconcile_path_inactive")

    return sorted(set(failures)), evidence


def provider_canary_monitoring_failures(
    report_path: Path = PROVIDER_CANARY_REPORT,
    *,
    max_age_seconds: int = PROVIDER_CANARY_MAX_AGE_SECONDS,
) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    evidence: dict[str, Any] = {"report_path": str(report_path), "fresh": False}
    payload = read_json(report_path)
    generated = payload.get("generated_at_epoch") if payload else None
    try:
        generated_value = float(generated)
    except (TypeError, ValueError):
        generated_value = 0.0
    now_epoch = datetime.now(timezone.utc).timestamp()
    age_seconds = max(0.0, now_epoch - generated_value) if generated_value > 0 else None
    evidence["generated_at_epoch"] = generated_value or None
    evidence["age_seconds"] = age_seconds
    if not payload or generated_value <= 0:
        failures.append("provider_canary_report_missing_or_invalid")
    elif age_seconds is None or age_seconds > max_age_seconds:
        failures.append("provider_canary_report_stale")
    else:
        evidence["fresh"] = True

    timer = run(
        ["systemctl", "is-active", "jason-provider-health-canary.timer"],
        timeout=10,
    )
    timer_active = timer.returncode == 0 and timer.stdout.strip() == "active"
    evidence["timer_active"] = timer_active
    if not timer_active:
        failures.append("provider_canary_timer_inactive")
    return sorted(set(failures)), evidence


def failed_jason_user_units() -> list[str]:
    result = run(
        ["systemctl", "--user", "--failed", "--no-legend", "--plain"],
        timeout=10,
    )
    if result.returncode != 0:
        return []
    failed: list[str] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        unit = line.split()[0]
        if unit.startswith("jason-"):
            failed.append(unit)
    return sorted(set(failed))


def operational_outcome_contract_failures(root: Path) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    evidence: list[dict[str, Any]] = []
    contract_dir = root / OUTCOME_CONTRACT_DIRNAME
    if not contract_dir.exists():
        return failures, evidence

    now_utc = datetime.now(timezone.utc)
    for path in sorted(contract_dir.glob("*.json")):
        payload = read_json(path)
        if not payload:
            failures.append(f"outcome_contract_invalid:{path.name}")
            evidence.append({"contract": path.name, "state": "invalid"})
            continue

        contract_id = str(payload.get("contract_id") or path.stem).strip()[:120]
        function = str(payload.get("function") or "unknown").strip()[:120]
        state = str(payload.get("state") or "pending").strip().casefold()
        verify_by = _parse_iso8601(payload.get("verify_by"))
        summary = str(payload.get("evidence_summary") or "").strip()[:500]

        record = {
            "contract_id": contract_id,
            "function": function,
            "state": state,
            "verify_by": verify_by.isoformat() if verify_by else None,
            "evidence_summary": summary,
        }
        evidence.append(record)

        if state == "verified":
            continue
        if state == "failed":
            failures.append(f"outcome_contract_failed:{function}:{contract_id}")
            continue
        if state not in {"pending", "waiting"}:
            failures.append(f"outcome_contract_invalid_state:{function}:{contract_id}")
            continue
        if verify_by is None:
            failures.append(f"outcome_contract_missing_deadline:{function}:{contract_id}")
            continue
        if now_utc > verify_by:
            failures.append(f"outcome_contract_overdue:{function}:{contract_id}")

    return sorted(set(failures)), evidence




def autonomy_behavior_anomalies(
    db_path: Path = AUTONOMY_WORK_DB,
    *,
    history_window: int = AUTONOMY_ANOMALY_WINDOW,
    recent_window: int = AUTONOMY_RECENT_WINDOW,
) -> tuple[list[str], dict[str, Any]]:
    if not db_path.exists():
        return [], {}
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT cycle_id,scanned_at,evaluated,eligible,unsupported,"
            "governance_blocked,assigned_elsewhere,active_slots,selected,"
            "waiting_device,human_review "
            "FROM autonomy_ticket_scan_cycle ORDER BY scanned_at DESC LIMIT ?",
            (max(history_window, recent_window),),
        ).fetchall()
    except sqlite3.Error as exc:
        return ["autonomy_behavior_health_read_failed"], {
            "error_class": type(exc).__name__
        }
    finally:
        try:
            connection.close()
        except (UnboundLocalError, sqlite3.Error):
            pass

    records = [dict(row) for row in rows]
    failures: list[str] = []
    evidence: dict[str, Any] = {"cycles": records[:history_window]}
    if not records:
        return failures, evidence

    # Generic invariants: these are structural truths, not enumerated incident types.
    for row in records[:recent_window]:
        cycle = str(row.get("cycle_id") or "unknown")
        numeric = {
            key: int(row.get(key) or 0)
            for key in (
                "evaluated", "eligible", "unsupported", "governance_blocked",
                "assigned_elsewhere", "active_slots", "selected",
                "waiting_device", "human_review",
            )
        }
        if any(value < 0 for value in numeric.values()):
            failures.append(f"autonomy_invariant_violation:negative_count:{cycle}")
        if numeric["eligible"] > numeric["evaluated"]:
            failures.append(f"autonomy_invariant_violation:eligible_gt_evaluated:{cycle}")
        if numeric["selected"] > numeric["eligible"]:
            failures.append(f"autonomy_invariant_violation:selected_gt_eligible:{cycle}")
        if numeric["selected"] > numeric["active_slots"]:
            failures.append(f"autonomy_invariant_violation:selected_gt_active_slots:{cycle}")

    # Generic behavioral baseline: compare recent selection efficiency with Jason's
    # own older healthy-looking cycles instead of hard-coding a particular failure.
    chronological = list(reversed(records[:history_window]))
    baseline_rows = chronological[:-recent_window] if len(chronological) > recent_window else []
    recent_rows = chronological[-recent_window:]
    baseline_ratios = [
        int(row.get("selected") or 0) / max(1, int(row.get("eligible") or 0))
        for row in baseline_rows
        if int(row.get("eligible") or 0) > 0 and int(row.get("active_slots") or 0) > 0
    ]
    recent_ratios = [
        int(row.get("selected") or 0) / max(1, int(row.get("eligible") or 0))
        for row in recent_rows
        if int(row.get("eligible") or 0) > 0 and int(row.get("active_slots") or 0) > 0
    ]
    if len(baseline_ratios) >= 4 and len(recent_ratios) == recent_window:
        baseline_median = statistics.median(baseline_ratios)
        recent_median = statistics.median(recent_ratios)
        evidence["selection_efficiency_baseline_median"] = baseline_median
        evidence["selection_efficiency_recent_median"] = recent_median
        if baseline_median >= 0.10 and recent_median <= max(0.01, baseline_median * 0.20):
            failures.append("autonomy_behavior_anomaly:selection_efficiency_collapse")

    return sorted(set(failures)), evidence

def autonomy_admission_failures(
    db_path: Path = AUTONOMY_WORK_DB,
) -> tuple[list[str], dict[str, Any]]:
    if not db_path.exists():
        return [], {}
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT cycle_id,scanned_at,eligible,active_slots,selected "
            "FROM autonomy_ticket_scan_cycle ORDER BY scanned_at DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error as exc:
        return ["autonomy_admission_health_read_failed"], {
            "error_class": type(exc).__name__
        }
    finally:
        try:
            connection.close()
        except (UnboundLocalError, sqlite3.Error):
            pass

    if row is None:
        return [], {}
    evidence = {
        "cycle_id": str(row["cycle_id"] or ""),
        "scanned_at": str(row["scanned_at"] or ""),
        "eligible": int(row["eligible"] or 0),
        "active_slots": int(row["active_slots"] or 0),
        "selected": int(row["selected"] or 0),
    }
    failures: list[str] = []
    if (
        evidence["eligible"] > 0
        and evidence["active_slots"] > 0
        and evidence["selected"] == 0
    ):
        failures.append("autonomy_admission_stalled:eligible_work_not_selected")
    return failures, evidence

def stale_operational_work_failures(
    db_path: Path = AUTONOMY_WORK_DB,
) -> tuple[list[str], list[dict[str, Any]]]:
    if not db_path.exists():
        return [], []
    failures: list[str] = []
    evidence: list[dict[str, Any]] = []
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT ticket_id,ticket_number,playbook_id,phase,updated_at,last_reason "
            "FROM autonomy_operational_work"
        ).fetchall()
    except sqlite3.Error as exc:
        return ["autonomy_work_health_read_failed"], [
            {"error_class": type(exc).__name__}
        ]
    finally:
        try:
            connection.close()
        except (UnboundLocalError, sqlite3.Error):
            pass

    current = datetime.now(timezone.utc)
    for row in rows:
        phase = str(row["phase"] or "")
        threshold = WORKFLOW_STALE_SECONDS.get(phase)
        if threshold is None:
            continue
        updated = _parse_iso8601(row["updated_at"])
        age_seconds = (
            (current - updated).total_seconds()
            if updated is not None
            else None
        )
        record = {
            "ticket_id": int(row["ticket_id"]),
            "ticket_number": str(row["ticket_number"] or ""),
            "playbook_id": str(row["playbook_id"] or ""),
            "phase": phase,
            "updated_at": str(row["updated_at"] or ""),
            "age_seconds": age_seconds,
            "last_reason": str(row["last_reason"] or "")[:300],
        }
        evidence.append(record)
        if age_seconds is None or age_seconds > threshold:
            failures.append(
                "workflow_outcome_stale:"
                + str(row["playbook_id"] or "unknown")[:80]
                + ":"
                + phase[:100]
                + ":ticket="
                + str(row["ticket_id"])
            )
    return sorted(set(failures)), evidence


def container_running(name: str) -> bool:
    result = run(["docker", "inspect", name, "--format", "{{.State.Running}}"], timeout=10)
    return result.returncode == 0 and result.stdout.strip().casefold() == "true"


def mcp_status_probe() -> tuple[bool, str]:
    if not container_running("jason-mcp-pilot"):
        return False, "jason-mcp-pilot is not running"
    code = (
        "from jason_mcp.server import jason_mcp_status; "
        "import json; s=jason_mcp_status(); "
        "assert s.get('status') == 'ok'; "
        "a=s.get('autonomy_work') or {}; "
        "assert a.get('status') == 'succeeded'; "
        "print(json.dumps({'status':s.get('status'),'active_count':a.get('active_count'),"
        "'waiting_count':a.get('waiting_count'),'blocked_count':a.get('blocked_count')}))"
    )
    result = run(["docker", "exec", "jason-mcp-pilot", "python", "-c", code], timeout=20)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "status probe failed").strip()
        return False, detail[-600:]
    return True, result.stdout.strip()[-600:]


def health_metrics() -> tuple[dict[str, float], str | None]:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=10) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return {}, f"production health exporter unavailable: {type(exc).__name__}"
    metrics: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or " " not in line:
            continue
        key, raw = line.rsplit(" ", 1)
        if key.startswith(
            (
                "jason_production_component_health",
                "jason_mcp_contract",
                "jason_provider_canary_health",
                "jason_grafana_configuration_assurance",
                "jason_root_filesystem_writable",
            )
        ):
            try:
                metrics[key] = float(raw)
            except ValueError:
                continue
    return metrics, None


def detect(root: Path = DEFAULT_ROOT) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    evidence: dict[str, Any] = {}

    for name in LOCAL_RECOVERY_CONTAINERS:
        running = container_running(name)
        evidence[f"container:{name}"] = running
        if not running:
            failures.append(f"container_down:{name}")

    ok, detail = mcp_status_probe()
    evidence["mcp_status_probe"] = {"ok": ok, "detail": detail}
    if not ok:
        failures.append("mcp_status_functional_failure")

    convergence_failures, convergence_evidence = production_convergence_failures()
    evidence["production_convergence"] = convergence_evidence
    failures.extend(convergence_failures)

    failed_units = failed_jason_user_units()
    evidence["failed_jason_user_units"] = failed_units
    for unit in failed_units:
        failures.append(f"systemd_unit_failed:{unit}")

    outcome_failures, outcome_evidence = operational_outcome_contract_failures(root)
    evidence["operational_outcome_contracts"] = outcome_evidence
    failures.extend(outcome_failures)

    workflow_failures, workflow_evidence = stale_operational_work_failures()
    evidence["stale_operational_work"] = workflow_evidence
    failures.extend(workflow_failures)

    admission_failures, admission_evidence = autonomy_admission_failures()
    evidence["autonomy_admission"] = admission_evidence
    failures.extend(admission_failures)

    behavior_failures, behavior_evidence = autonomy_behavior_anomalies()
    evidence["autonomy_behavior"] = behavior_evidence
    failures.extend(behavior_failures)

    canary_failures, canary_evidence = provider_canary_monitoring_failures()
    evidence["provider_canary_monitoring"] = canary_evidence
    failures.extend(canary_failures)
    canary_fresh = canary_evidence.get("fresh") is True

    metrics, metric_error = health_metrics()
    evidence["health_exporter_error"] = metric_error
    if metric_error:
        failures.append("production_health_unavailable")
    else:
        unhealthy = sorted(
            key for key, value in metrics.items()
            if (
                key.startswith("jason_production_component_health")
                or key.startswith("jason_mcp_contract")
                or (canary_fresh and key.startswith("jason_provider_canary_health"))
                or key == "jason_grafana_configuration_assurance"
            )
            and value == 0
        )
        for key in unhealthy:
            failures.append("health_metric:" + key[:180])
        evidence["unhealthy_metrics"] = unhealthy

    return sorted(set(failures)), evidence


def fingerprint(failures: list[str]) -> str:
    material = json.dumps(sorted(failures), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def bounded_recovery(failures: list[str]) -> list[str]:
    actions: list[str] = []
    for name in LOCAL_RECOVERY_CONTAINERS:
        if f"container_down:{name}" in failures:
            result = run(["docker", "start", name], timeout=30)
            actions.append(f"docker start {name}: rc={result.returncode}")

    if "mcp_status_functional_failure" in failures and container_running("jason-mcp-pilot"):
        result = run(["docker", "restart", "-t", "10", "jason-mcp-pilot"], timeout=40)
        actions.append(f"docker restart jason-mcp-pilot: rc={result.returncode}")
    return actions


def queue_support_repair(root: Path, fp: str, failures: list[str], evidence: Mapping[str, Any]) -> Path:
    incident = {
        "schema_version": "1.0",
        "fingerprint": fp,
        "support_item": "SUPPORT-AUTO-" + fp[:12].upper(),
        "priority": "P1",
        "title": "Jason self-heal unresolved degraded state",
        "evidence": "; ".join(failures)[:1200],
        "acceptance": (
            "Restore the affected already-approved Jason function, add regression coverage, "
            "verify it in production, and preserve existing governance boundaries."
        ),
        "context": dict(evidence),
        "detected_at": now(),
        "state": "repair_required",
    }
    path = root / "incidents" / f"{fp}.json"
    atomic_json(path, incident)
    run(["systemctl", "--user", "start", "--no-block", "jason-support-repair-worker.service"], timeout=10)
    return path


def queue_resolution_incident(root: Path, incident: Mapping[str, Any], evidence: Mapping[str, Any]) -> Path:
    fp = str(incident.get("fingerprint") or "")
    symptoms = [str(value) for value in incident.get("symptoms", [])]
    repair = incident.get("repair") if isinstance(incident.get("repair"), Mapping) else {}
    verification = incident.get("verification_contract") if isinstance(incident.get("verification_contract"), Mapping) else {}
    payload = {
        "schema_version": "2.0",
        "fingerprint": fp,
        "support_item": "SUPPORT-AUTO-" + fp[:12].upper(),
        "priority": str(incident.get("priority") or "P1"),
        "title": str(incident.get("title") or "Jason operational invariant degraded")[:240],
        "family": str(incident.get("family") or "unknown"),
        "root_invariant": str(incident.get("root_invariant") or "")[:1200],
        "symptoms": symptoms,
        "evidence": "; ".join(symptoms)[:1600],
        "acceptance": acceptance_text(incident),
        "repair_level": int(repair.get("level") or 2),
        "repair_class": str(repair.get("name") or "bounded_autonomous_repair"),
        "requires_owner_action": bool(repair.get("requires_owner_action")),
        "occurrence_count": int(incident.get("occurrence_count") or 1),
        "recurring": bool(incident.get("recurring")),
        "architectural_correction_required": bool(incident.get("architectural_correction_required")),
        "verification_contract": dict(verification),
        "context": dict(evidence),
        "detected_at": now(),
        "state": "repair_required",
    }
    path = root / "incidents" / f"{fp}.json"
    atomic_json(path, payload)
    run(["systemctl", "--user", "start", "--no-block", "jason-support-repair-worker.service"], timeout=10)
    return path


def write_incident_escalation(root: Path, *, incident: Mapping[str, Any], attempts: int, actions: list[str]) -> Path:
    fp = str(incident.get("fingerprint") or "")
    symptoms = [str(value) for value in incident.get("symptoms", [])]
    repair = incident.get("repair") if isinstance(incident.get("repair"), Mapping) else {}
    payload = {
        "schema_version": "2.0",
        "fingerprint": fp,
        "state": "owner_action_required",
        "family": str(incident.get("family") or "unknown"),
        "root_invariant": str(incident.get("root_invariant") or "")[:1200],
        "degraded_function": str(incident.get("title") or ", ".join(symptoms))[:240],
        "evidence_summary": "; ".join(symptoms)[:600],
        "attempt_summary": ("; ".join(actions) or "bounded automatic recovery produced no safe action")[:600],
        "owner_action": "A genuine authority or disruptive-action boundary remains; review only that specific blocked action.",
        "repair_level": int(repair.get("level") or 4),
        "repair_class": str(repair.get("name") or "external_or_authority_blocker"),
        "attempts": attempts,
        "created_at": now(),
    }
    path = root / "escalations" / f"{fp}.json"
    atomic_json(path, payload)
    return path


def write_escalation(
    root: Path,
    *,
    fp: str,
    failures: list[str],
    attempts: int,
    actions: list[str],
) -> Path:
    payload = {
        "schema_version": "1.0",
        "fingerprint": fp,
        "state": "owner_action_required",
        "degraded_function": ", ".join(failures)[:160],
        "evidence_summary": "; ".join(failures)[:400],
        "attempt_summary": ("; ".join(actions) or "bounded automatic recovery produced no safe action")[:400],
        "owner_action": (
            "Review the unresolved Jason self-heal incident; recovery exhausted or no safe "
            "automatic remediation exists within current authority."
        ),
        "attempts": attempts,
        "created_at": now(),
    }
    path = root / "escalations" / f"{fp}.json"
    atomic_json(path, payload)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--max-attempts", type=int, default=MAX_RECOVERY_ATTEMPTS)
    args = parser.parse_args()
    root = args.root.resolve()
    state_path = root / "state.json"
    memory_path = root / "issue-memory.json"
    state = read_json(state_path)

    failures, evidence = detect(root)
    if not failures:
        update_recurrence_memory(memory_path, [])
        atomic_json(state_path, {
            "schema_version": "2.0",
            "state": "healthy",
            "last_verified_at": now(),
            "previous_fingerprint": state.get("fingerprint"),
            "incidents": [],
        })
        return 0

    fp = fingerprint(failures)
    attempts = int(state.get("attempts") or 0) if state.get("fingerprint") == fp else 0
    actions: list[str] = []

    if attempts < max(1, int(args.max_attempts)):
        actions = bounded_recovery(failures)
        attempts += 1
        failures_after, evidence_after = detect(root)
        if not failures_after:
            update_recurrence_memory(memory_path, [])
            atomic_json(state_path, {
                "schema_version": "2.0",
                "state": "recovered",
                "fingerprint": fp,
                "attempts": attempts,
                "recovery_actions": actions,
                "verified_at": now(),
                "verification": "original detector rerun passed with no remaining failures",
                "incidents": [],
            })
            return 0
        failures = failures_after
        evidence = evidence_after
        fp = fingerprint(failures)

    incidents = update_recurrence_memory(memory_path, correlate_failures(failures))
    incident_paths: list[str] = []
    owner_escalations: list[str] = []
    for incident in incidents:
        incident_path = queue_resolution_incident(root, incident, evidence)
        incident_paths.append(str(incident_path))
        repair = incident.get("repair") if isinstance(incident.get("repair"), Mapping) else {}
        if attempts >= max(1, int(args.max_attempts)) and bool(repair.get("requires_owner_action")):
            escalation = write_incident_escalation(
                root, incident=incident, attempts=attempts, actions=actions
            )
            owner_escalations.append(str(escalation))

    atomic_json(state_path, {
        "schema_version": "2.0",
        "state": "owner_action_required" if owner_escalations else "repair_required",
        "fingerprint": fp,
        "attempts": attempts,
        "failures": failures,
        "last_recovery_actions": actions,
        "incident_paths": incident_paths,
        "incidents": incidents,
        "owner_escalations": owner_escalations,
        "updated_at": now(),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
