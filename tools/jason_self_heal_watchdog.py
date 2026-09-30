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
import subprocess
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_ROOT = Path("/var/lib/jason/openclaw/self-heal")
HEALTH_URL = "http://127.0.0.1:9467/metrics"
LOCAL_RECOVERY_CONTAINERS = ("jason-runtime", "jason-mcp-pilot")
MAX_RECOVERY_ATTEMPTS = 2
OUTCOME_CONTRACT_DIRNAME = "contracts"
AUTONOMY_WORK_DB = Path("/var/lib/jason/openclaw/autonomy-operational-work.sqlite3")
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
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
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
                or key.startswith("jason_provider_canary_health")
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
    run(["systemctl", "--user", "start", "jason-support-repair-worker.service"], timeout=10)
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
    state = read_json(state_path)

    failures, evidence = detect(root)
    if not failures:
        atomic_json(
            state_path,
            {
                "schema_version": "1.0",
                "state": "healthy",
                "last_verified_at": now(),
                "previous_fingerprint": state.get("fingerprint"),
            },
        )
        return 0

    fp = fingerprint(failures)
    attempts = int(state.get("attempts") or 0) if state.get("fingerprint") == fp else 0
    actions: list[str] = []

    if attempts < max(1, int(args.max_attempts)):
        actions = bounded_recovery(failures)
        attempts += 1
        failures_after, evidence_after = detect(root)
        if not failures_after:
            atomic_json(
                state_path,
                {
                    "schema_version": "1.0",
                    "state": "recovered",
                    "fingerprint": fp,
                    "attempts": attempts,
                    "recovery_actions": actions,
                    "verified_at": now(),
                },
            )
            return 0
        failures = failures_after
        evidence = evidence_after
        fp = fingerprint(failures)

    incident_path = queue_support_repair(root, fp, failures, evidence)
    state_payload = {
        "schema_version": "1.0",
        "state": "repair_required",
        "fingerprint": fp,
        "attempts": attempts,
        "failures": failures,
        "last_recovery_actions": actions,
        "incident_path": str(incident_path),
        "updated_at": now(),
    }
    if attempts >= max(1, int(args.max_attempts)):
        escalation_path = write_escalation(
            root,
            fp=fp,
            failures=failures,
            attempts=attempts,
            actions=actions,
        )
        state_payload["state"] = "owner_action_required"
        state_payload["escalation_path"] = str(escalation_path)
    atomic_json(state_path, state_payload)
    # Degradation is persisted state, not watchdog process failure. Keeping the
    # oneshot unit successful prevents the watchdog from creating a secondary
    # failed-systemd-unit condition while it is already handling the primary fault.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
