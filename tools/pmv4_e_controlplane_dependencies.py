#!/usr/bin/env python3
"""Source-only Stage E guard: legacy self-heal/release dependencies.

A read-only inventory is not a root acceptance receipt and never authorizes
retirement. Missing or modified source is a blocker, not evidence of parity.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import stat
from typing import Any,Mapping


SOURCE_ROOT=Path(__file__).resolve().parents[1]
WATCHDOG="tools/jason_self_heal_watchdog.py"
RELEASE_MANAGER="tools/release_manager_host_runner.py"
ROOT_RECONCILER="tools/reconcile_production_host_services.sh"
SOURCE_ALLOWLIST=(WATCHDOG,RELEASE_MANAGER,ROOT_RECONCILER)
SOURCE_LIMIT=1_000_000
# These are observed requirements of the deployed PMv3 control plane.
WATCHDOG_TIMER=b'"jason-release-manager.timer"'
WATCHDOG_REPAIR=b'"jason-support-repair-worker.timer"'
WATCHDOG_START=b'"jason-support-repair-worker.service"'
ROOT_INSTALL=b'install_support_repair_host_worker.py'
ROOT_RECONCILER_START=b'--activate'
RELEASE_MANAGER_TIMER=b'"jason-release-manager.timer"'
RELEASE_MANAGER_REPAIR=b'"jason-support-repair-worker.timer"'


class ControlplaneEvidenceDenied(RuntimeError):
    pass


def read_exact_source(base:Path,relative:str)->bytes:
    if relative not in SOURCE_ALLOWLIST:
        raise ControlplaneEvidenceDenied("PMV4_E_SOURCE_NOT_APPROVED")
    try:
        path=base/relative
        meta=path.lstat()
        if (path.is_symlink() or not stat.S_ISREG(meta.st_mode)
            or meta.st_size<1 or meta.st_size>SOURCE_LIMIT
            or meta.st_mode & 0o002):
            raise ControlplaneEvidenceDenied(
                "PMV4_E_CONTROLPLANE_SOURCE_UNTRUSTED")
        raw=path.read_bytes()
        if len(raw)!=meta.st_size:
            raise ControlplaneEvidenceDenied("PMV4_E_SOURCE_CHANGED_DURING_READ")
        return raw
    except OSError as exc:
        raise ControlplaneEvidenceDenied(
            "PMV4_E_CONTROLPLANE_SOURCE_UNAVAILABLE") from exc


def inspect(*,source_root:Path=SOURCE_ROOT)->dict[str,Any]:
    sources={}
    for relative in SOURCE_ALLOWLIST:
        source=read_exact_source(source_root,relative)
        sources[relative]={
            "sha256":sha256(source).hexdigest(),
            "byte_count":len(source),
        }
    watchdog=read_exact_source(source_root,WATCHDOG)
    release=read_exact_source(source_root,RELEASE_MANAGER)
    root=read_exact_source(source_root,ROOT_RECONCILER)
    flags={
        "self_heal_requires_legacy_user_timers":(
            WATCHDOG_TIMER in watchdog and WATCHDOG_REPAIR in watchdog),
        "self_heal_restarts_legacy_engineering_worker":WATCHDOG_START in watchdog,
        "release_manager_requires_legacy_timers":(
            RELEASE_MANAGER_TIMER in release and RELEASE_MANAGER_REPAIR in release),
        "root_host_reconciler_reinstalls_legacy_worker":(
            ROOT_INSTALL in root and ROOT_RECONCILER_START in root),
    }
    problems=[]
    for present,code in (
        ("self_heal_requires_legacy_user_timers",
         "PMV4_E_WATCHDOG_REQUIRES_LEGACY_TIMERS"),
        ("self_heal_restarts_legacy_engineering_worker",
         "PMV4_E_WATCHDOG_RESTARTS_LEGACY_WORKER"),
        ("release_manager_requires_legacy_timers",
         "PMV4_E_RELEASE_MANAGER_REQUIRES_LEGACY_TIMERS"),
        ("root_host_reconciler_reinstalls_legacy_worker",
         "PMV4_E_ROOT_HOST_RECONCILER_REINSTALLS_LEGACY_WORKER"),
    ):
        if flags[present]:problems.append(code)
    # An absent string is not proof that the new installation, live scheduler
    # and protected policy have passed root acceptance. Never close that gate.
    problems.append("PMV4_E_REPLACEMENT_CONTROLPLANE_ROOT_ACCEPTANCE_MISSING")
    return {
        "status":"retirement_blocked_pending_replacement_acceptance",
        "phase":"E",
        "source_refs":sources,
        "legacy_dependencies":flags,
        "blocking_gates":problems,
        "replacement_controller_root_acceptance_verified":False,
        "legacy_release_worker_retirement_authorized":False,
        "production_mutations":False,
        "provider_calls":False,
    }
