#!/usr/bin/env python3
"""Read-only PMv4 Phase E legacy dependency retirement admission.

This attestor observes only already deployed timers, source desired state,
the existing production runtime and the canonical ticket scan ledger.
It never disables a service or publishes desired state. Root-protected live
watchdog policy must be independently verified at any later release.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Any, Callable, Mapping, Sequence

REPOSITORY_DESIRED = Path(__file__).resolve().parents[1] / "config/production-desired-state.json"
PRODUCTION_CURRENT = Path("/opt/jason/current")
TICKET_LEDGER = Path("/var/lib/jason/openclaw/autonomy-operational-work.sqlite3")
USER_LEGACY = (
    "jason-support-repair-worker.timer",
    "jason-release-manager.timer",
    "jason-release-approval-only.timer",
)
SYSTEM_LEGACY = (
    "jason-release-control-transition.timer",
    "jason-release-control-readback.timer",
    "jason-release-host-reconcile.path",
)
REQUIRED_CONTINUITY = (
    "jason-production-drift-watchdog.timer",
    "jason-boot-recovery.timer",
    "jason-openclaw-authority-health.timer",
)
PROTECTED_CONTAINERS = ("jason-runtime", "jason-mcp-pilot")


class RetirementEvidenceDenied(RuntimeError):
    pass


def command(argv: Sequence[str], *, runner: Callable[..., Any] = subprocess.run) -> str:
    allowed = ("/usr/bin/systemctl", "/usr/bin/docker")
    if not argv or argv[0] not in allowed:
        raise RetirementEvidenceDenied("PMV4_E_READONLY_COMMAND_NOT_ALLOWLISTED")
    if argv[0] == "/usr/bin/systemctl":
        # No systemd mutation, no start, stop, reload, reset-failed, etc.
        if not all(arg in ("--user", "is-active", "is-enabled") or arg in (
            USER_LEGACY + SYSTEM_LEGACY + REQUIRED_CONTINUITY
        ) for arg in argv[1:]):
            raise RetirementEvidenceDenied("PMV4_E_SYSTEMD_MUTATION_DENIED")
        if len(argv) not in (3,4) or argv[-2] not in ("is-active", "is-enabled"):
            raise RetirementEvidenceDenied("PMV4_E_SYSTEMD_ARGS_INVALID")
    else:
        if len(argv) != 5 or argv[1:4] != ["inspect", "--format", "{{.State.Running}}"]:
            raise RetirementEvidenceDenied("PMV4_E_DOCKER_MUTATION_DENIED")
        if argv[-1] not in PROTECTED_CONTAINERS:
            raise RetirementEvidenceDenied("PMV4_E_DOCKER_TARGET_OUTSIDE_CORE")
    try:
        env=dict(os.environ)
        if "--user" in argv:
            env["XDG_RUNTIME_DIR"]="/run/user/1000"
            env["DBUS_SESSION_BUS_ADDRESS"]="unix:path=/run/user/1000/bus"
        result=runner(list(argv),capture_output=True,text=True,
                      check=False,timeout=12,env=env)
    except (OSError,ValueError,TypeError,subprocess.TimeoutExpired) as exc:
        raise RetirementEvidenceDenied("PMV4_E_READ_UNAVAILABLE") from exc
    if result.returncode not in (0,1,3) or not isinstance(result.stdout,str):
        raise RetirementEvidenceDenied("PMV4_E_READ_UNAVAILABLE")
    text=result.stdout.strip()
    if not text or len(text)>120:
        raise RetirementEvidenceDenied("PMV4_E_READBACK_INVALID")
    return text


def units_readback(*, runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    observed={}
    for group, units, user in (
        ("legacy_user",USER_LEGACY,True),
        ("legacy_system",SYSTEM_LEGACY,False),
        ("continuity",REQUIRED_CONTINUITY,False),
    ):
        entries=[]
        for name in units:
            prefix=["/usr/bin/systemctl"]+(["--user"] if user else [])
            try:
                active=command(prefix+["is-active",name],runner=runner)
                enabled=command(prefix+["is-enabled",name],runner=runner)
            except RetirementEvidenceDenied:
                active=enabled="unavailable"
            entries.append({"unit":name,"active":active,"enabled":enabled})
        observed[group]=entries
    return observed


def scan_summary(db:Path=TICKET_LEDGER)->dict[str,Any]:
    db=Path(db)
    if (not db.is_absolute() or not db.is_file() or db.is_symlink()):
        return {"status":"unavailable"}
    try:
        con=sqlite3.connect("file:"+db.as_posix()+"?mode=ro",uri=True,timeout=4)
        con.execute("PRAGMA query_only=ON")
        row=con.execute(
            "SELECT scanned_at,provider_items,duplicate_items,evaluated "
            "FROM autonomy_ticket_scan_cycle ORDER BY scanned_at DESC LIMIT 1"
        ).fetchone()
        con.close()
    except sqlite3.Error:
        return {"status":"unavailable"}
    if (not row or not isinstance(row[0],str)
        or any(type(value) is not int or value<0 for value in row[1:])
        or row[2]!=0):
        return {"status":"unverified"}
    try:
        at=datetime.fromisoformat(row[0].replace("Z","+00:00"))
        age=(datetime.now(timezone.utc)-at).total_seconds()
        if at.tzinfo is None or age<0 or age>360:
            return {"status":"stale"}
    except (TypeError,ValueError):
        return {"status":"unverified"}
    return {
        "status":"fresh", "observed_at":row[0],
        "provider_items":row[1],"duplicate_items":row[2],
        "evaluated":row[3],
    }


def inspect(*, policy:Path=REPOSITORY_DESIRED,
            current:Path=PRODUCTION_CURRENT, db:Path=TICKET_LEDGER,
            runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    # Source policy is advisory only; root-protected LIVE policy is a separate
    # readback gate and never assumed identical to repository desired state.
    try:
        doc=json.loads(Path(policy).read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError) as exc:
        raise RetirementEvidenceDenied("PMV4_E_SOURCE_POLICY_UNAVAILABLE") from exc
    if not isinstance(doc,dict) or doc.get("schema_version")!="1.0":
        raise RetirementEvidenceDenied("PMV4_E_SOURCE_POLICY_UNTRUSTED")
    required_user=set(doc.get("required_user_units") or [])
    required_system=set(doc.get("required_system_units") or [])
    legacy_required=(
        set(USER_LEGACY).issubset(required_user)
        and set(SYSTEM_LEGACY).issubset(required_system)
    )
    state=units_readback(runner=runner)
    legacy_rows=[item for group in ("legacy_user","legacy_system")
                 for item in state[group]]
    original_live=any(item["active"]=="active" for item in legacy_rows)
    legacy_observation_complete=all(
        item["active"] in ("active","inactive","failed")
        and item["enabled"] in ("enabled","disabled","static","masked")
        for item in legacy_rows
    )
    continuity=all(item["active"]=="active" for item in state["continuity"])
    prod={}
    for name in PROTECTED_CONTAINERS:
        try:
            prod[name]=command(
                ["/usr/bin/docker","inspect","--format",
                 "{{.State.Running}}",name],runner=runner
            )=="true"
        except RetirementEvidenceDenied:
            prod[name]=False
    scans=scan_summary(db)
    try:
        active_sha=Path(current).resolve(strict=True).name
    except OSError:
        active_sha="unverified"
    problems=[]
    if legacy_required:
        problems.append("LEGACY_UNITS_STILL_REQUIRED_BY_PROTECTED_SOURCE_DESIRED_STATE")
    if original_live:
        problems.append("LEGACY_ENG_AND_RELEASE_CONTROLLERS_STILL_ACTIVE")
    if not legacy_observation_complete:
        problems.append("LEGACY_SYSTEMD_UNIT_READBACK_UNVERIFIED")
    if not continuity:
        problems.append("REQUIRED_MONITORING_AND_RECOVERY_NOT_ALL_ACTIVE")
    if not all(prod.values()):
        problems.append("PROTECTED_RUNTIME_OR_MCP_NOT_RUNNING")
    if scans.get("status")!="fresh":
        problems.append("TICKET_CORE_PROVIDER_SCAN_NOT_FRESH")
    problems.extend((
        "PMV4_REPLACEMENT_CONTROLLER_PARITY_NOT_ACCEPTED",
        "STAGE_C_INDEPENDENT_WORKER_NOT_ACCEPTED",
        "STAGE_D_INDEPENDENT_RUNBOOK_MANAGEMENT_NOT_ACCEPTED",
        "ROOT_PROTECTED_LIVE_DESIRED_STATE_NOT_READBACK",
        "EXACT_OWNER_RELEASE_FOR_RETIREMENT_NOT_RECORDED",
    ))
    return {
        "status":"not_ready_for_pmv3_retirement",
        "phase":"E",
        "source_policy_legacy_required":legacy_required,
        "legacy_active":original_live,
        "legacy_observation_complete":legacy_observation_complete,
        "required_monitoring_active":continuity,
        "protected_containers_running":prod,
        "legacy_dependency_units":state,
        "ticket_scan":scans,
        "production_source":active_sha,
        "blocking_gates":problems,
        "governed_release_authorized":False,
        "service_mutations":False,
        "ticket_mutations":False,
        "provider_actions":False,
    }


if __name__=="__main__":
    print(json.dumps(inspect(),sort_keys=True))
