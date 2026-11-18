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
import socket
import sqlite3
import stat
import struct
import subprocess
from typing import Any, Callable, Mapping, Sequence

REPOSITORY_DESIRED = Path(__file__).resolve().parents[1] / "config/production-desired-state.json"
PRODUCTION_CURRENT = Path("/opt/jason/current")
TICKET_LEDGER = Path("/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3")
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
STAGE_C_WORKER = "jason-pmv4-ticket-core"
STAGE_D_UNIT = "jason-runbook-management-read.service"
STAGE_D_SOCKET = Path("/run/jason-runbook-management/read.sock")
STAGE_D_UID = 1000
# Pin the separately Owner-accepted isolated A1 v5 release. A new shadow
# release must produce a new governed Stage E review; this is not a generic
# "any healthy container" check.
STAGE_A1_SHADOW = "jason-pmv4-shadow-gateway"
STAGE_A1_SHA = "9859463e5255ecf7040de21d73e9f4062b46a18e"
STAGE_A1_PRIOR_SHA = "75f2b4c0c48a15bd17d700b9f039fe56623e3f52"
STAGE_A1_IMAGE = "sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd"
STAGE_A1_POINTER = Path("/var/lib/jason/pmv4-shadow/current")
STAGE_A1_SHADOW_FORMAT = (
    "{{.State.Health.Status}}|{{.HostConfig.Memory}}|{{.Image}}|"
    "{{.State.Running}}|{{.HostConfig.NetworkMode}}"
)
STAGE_A1_SHADOW_EXPECTED = (
    "healthy|4294967296|" + STAGE_A1_IMAGE + "|true|none"
)
STAGE_C_HEALTH_FORMAT = "{{.State.Health.Status}}"
STAGE_C_RUNTIME_HOST_FORMAT = (
    '{{range .Config.Env}}{{if eq . "JASON_TICKET_WORKER_HOSTING=external"}}'
    'external{{end}}{{end}}'
)


class RetirementEvidenceDenied(RuntimeError):
    pass


def command(argv: Sequence[str], *, runner: Callable[..., Any] = subprocess.run) -> str:
    allowed = ("/usr/bin/systemctl", "/usr/bin/docker")
    if not argv or argv[0] not in allowed:
        raise RetirementEvidenceDenied("PMV4_E_READONLY_COMMAND_NOT_ALLOWLISTED")
    if argv[0] == "/usr/bin/systemctl":
        # No systemd mutation, no start, stop, reload, reset-failed, etc.
        if not all(arg in ("--user", "is-active", "is-enabled") or arg in (
            USER_LEGACY + SYSTEM_LEGACY + REQUIRED_CONTINUITY + (STAGE_D_UNIT,)
        ) for arg in argv[1:]):
            raise RetirementEvidenceDenied("PMV4_E_SYSTEMD_MUTATION_DENIED")
        if len(argv) not in (3,4) or argv[-2] not in ("is-active", "is-enabled"):
            raise RetirementEvidenceDenied("PMV4_E_SYSTEMD_ARGS_INVALID")
    else:
        if len(argv) != 5 or argv[1:3] != ["inspect", "--format"]:
            raise RetirementEvidenceDenied("PMV4_E_DOCKER_MUTATION_DENIED")
        fmt, target = argv[3], argv[4]
        approved = (
            fmt == "{{.State.Running}}" and
            target in PROTECTED_CONTAINERS + (STAGE_C_WORKER,)
        ) or (fmt == STAGE_C_HEALTH_FORMAT and target == STAGE_C_WORKER
        ) or (fmt == STAGE_C_RUNTIME_HOST_FORMAT and target == "jason-runtime"
        ) or (fmt == STAGE_A1_SHADOW_FORMAT and target == STAGE_A1_SHADOW)
        if not approved:
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


def runbook_socket_status(*, path:Path=STAGE_D_SOCKET)->dict[str,Any]:
    """Read only the fixed status operation from the same-UID local service."""
    try:
        folder=path.parent.lstat()
        meta=path.lstat()
        if (path.is_symlink() or path.parent.is_symlink()
            or not stat.S_ISDIR(folder.st_mode) or folder.st_uid!=STAGE_D_UID
            or stat.S_IMODE(folder.st_mode)!=0o700
            or not stat.S_ISSOCK(meta.st_mode) or meta.st_uid!=STAGE_D_UID
            or stat.S_IMODE(meta.st_mode)!=0o600):
            raise RetirementEvidenceDenied("PMV4_E_RUNBOOK_SOCKET_UNTRUSTED")
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
            peer.settimeout(4)
            peer.connect(str(path))
            _,uid,_=struct.unpack("3i",peer.getsockopt(socket.SOL_SOCKET,
                                                       socket.SO_PEERCRED,12))
            if uid!=STAGE_D_UID:
                raise RetirementEvidenceDenied("PMV4_E_RUNBOOK_SERVICE_UID_CHANGED")
            peer.sendall(b'{"operation":"status"}\n')
            with peer.makefile("rb") as stream:
                line=stream.readline(8193)
        if not line or len(line)>8192 or not line.endswith(b"\n"):
            raise RetirementEvidenceDenied("PMV4_E_RUNBOOK_READBACK_INVALID")
        result=json.loads(line)
        if (not isinstance(result,dict)
            or result.get("status")!="healthy"
            or type(result.get("registry_generation")) is not int
            or result["registry_generation"]<0
            or type(result.get("active_count")) is not int
            or result["active_count"]<0
            or result.get("provider_calls") is not False
            or result.get("execution_authority") is not False
            or result.get("configuration_mutations") is not False):
            raise RetirementEvidenceDenied("PMV4_E_RUNBOOK_READBACK_NOT_READONLY")
        return {
            "registry_generation":result["registry_generation"],
            "active_count":result["active_count"],
            "provider_calls":False,"execution_authority":False,
            "configuration_mutations":False,
        }
    except (OSError,ValueError,TypeError,struct.error) as exc:
        raise RetirementEvidenceDenied("PMV4_E_RUNBOOK_READ_UNAVAILABLE") from exc


def stage_d_readback(*,runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    result={"unit_active":False,"unit_enabled":False,"socket_healthy":False,
            "registry_generation":None,"active_count":None,"live":False,
            "root_acceptance_receipt_verified":False}
    try:
        result["unit_active"]=(command(
            ["/usr/bin/systemctl","is-active",STAGE_D_UNIT],runner=runner)=="active")
        result["unit_enabled"]=(command(
            ["/usr/bin/systemctl","is-enabled",STAGE_D_UNIT],runner=runner)=="enabled")
        if result["unit_active"] and result["unit_enabled"]:
            state=runbook_socket_status()
            result["socket_healthy"]=True
            result["registry_generation"]=state["registry_generation"]
            result["active_count"]=state["active_count"]
    except RetirementEvidenceDenied:
        pass
    result["live"]=all(result[k] for k in (
        "unit_active","unit_enabled","socket_healthy"))
    return result


def stage_a1_readback(*, pointer:Path=STAGE_A1_POINTER,
                      runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    """Observe the immutable A1 release, not a generic green Docker health."""
    status={"pointer_exact":False,"shadow_healthy":False,
            "network_disconnected":False,"signed_image_pinned":False,
            "memory_bytes":None,"live":False,
            "root_acceptance_receipt_verified":False}
    try:
        info=pointer.lstat()
        status["pointer_exact"]=(
            stat.S_ISLNK(info.st_mode)
            and info.st_uid==0
            and os.readlink(pointer)=="releases/"+STAGE_A1_SHA
        )
        if not status["pointer_exact"]:
            return status
        read=command(
            ["/usr/bin/docker","inspect","--format",STAGE_A1_SHADOW_FORMAT,
             STAGE_A1_SHADOW],runner=runner)
        fields=read.split("|")
        if len(fields)!=5:
            return status
        health,memory,image,running,network=fields
        if not memory.isdecimal() or len(memory)>16:
            return status
        status["memory_bytes"]=int(memory)
        status["shadow_healthy"]=health=="healthy" and running=="true"
        status["network_disconnected"]=network=="none"
        status["signed_image_pinned"]=image==STAGE_A1_IMAGE
        status["live"]=read==STAGE_A1_SHADOW_EXPECTED
    except (RetirementEvidenceDenied,OSError,ValueError,TypeError):
        return status
    return status


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
    # A live independent Stage C worker is not the same as the root-owned
    # final acceptance receipt, which must still be verified separately.
    stage_c = {"runtime_external": False, "worker_running": False,
               "worker_healthy": False, "live": False,
               "root_acceptance_receipt_verified": False}
    for key, args, expected in (
        ("runtime_external", ["/usr/bin/docker", "inspect", "--format",
                              STAGE_C_RUNTIME_HOST_FORMAT, "jason-runtime"], "external"),
        ("worker_running", ["/usr/bin/docker", "inspect", "--format",
                            "{{.State.Running}}", STAGE_C_WORKER], "true"),
        ("worker_healthy", ["/usr/bin/docker", "inspect", "--format",
                            STAGE_C_HEALTH_FORMAT, STAGE_C_WORKER], "healthy"),
    ):
        try:
            stage_c[key] = command(args, runner=runner) == expected
        except RetirementEvidenceDenied:
            stage_c[key] = False
    stage_c["live"] = all(stage_c[k] for k in (
        "runtime_external", "worker_running", "worker_healthy"))
    stage_d=stage_d_readback(runner=runner)
    stage_a1=stage_a1_readback(runner=runner)
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
    if not stage_a1["live"]:
        problems.append("PMV4_A1_ISOLATED_SHADOW_RELEASE_NOT_ACCEPTED")
    elif not stage_a1["root_acceptance_receipt_verified"]:
        problems.append("PMV4_A1_ROOT_ACCEPTANCE_RECEIPT_NOT_READBACK")
    # A1 proves one isolated ShadowController release, NOT that the generic
    # controller replaces old engineering and release scheduler functions.
    problems.append("PMV4_REPLACEMENT_CONTROLLER_PARITY_NOT_ACCEPTED")
    problems.append(
        "STAGE_C_ROOT_ACCEPTANCE_RECEIPT_NOT_READBACK"
        if stage_c["live"] else "STAGE_C_INDEPENDENT_WORKER_NOT_ACCEPTED"
    )
    problems.append(
        "STAGE_D_ROOT_ACCEPTANCE_RECEIPT_NOT_READBACK"
        if stage_d["live"] else "STAGE_D_INDEPENDENT_RUNBOOK_MANAGEMENT_NOT_ACCEPTED"
    )
    problems.extend((
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
        "stage_c_independent_worker":stage_c,
        "stage_d_independent_runbook_management":stage_d,
        "stage_a1_isolated_shadow":stage_a1,
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
