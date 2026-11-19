#!/usr/bin/env python3
"""Immutable source/scope digest for a future exact signed Stage E root release.

Read-only source preparation. No trusted root installation or Owner proof.
The native root controller must independently rehash installed source,
confirm protected root policy/freeze and bind its signed grant to this scope.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import stat
from typing import Any

from tools import pmv4_e_replacement_unit_bundle as units
from tools import pmv4_e_scheduler_parity as parity

ROOT=Path(__file__).resolve().parents[1]
SHA40=re.compile(r"^[0-9a-f]{40}$")
SHA64=re.compile(r"^[0-9a-f]{64}$")
ACTION="pmv4-e-oneowner-six-unit-replacement-and-retirement-v1"
EXPECTED_PRIOR_ROOT_POLICY="4c9db0f4bbd12e1892b480a759d2d89b9749b84187eb2a753a260ecf326b7953"
EXPECTED_FREEZE="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
ROOT_TO_INSTALL=(
    "config/production-desired-state.json",
    "tools/pmv4_e_unit_admission.py",
    "tools/pmv4_e_scheduler_parity.py",
    "tools/pmv3_work_engine.py",
    "tools/pmv4_e_root_reconcile_admission.py",
    "tools/pmv4_e_root_cutover_preflight.py",
    "tools/pmv4_e_retirement_readiness.py",
    "tools/pmv4_e_controlplane_dependencies.py",
    "tools/pmv4_e_root_trust_stage.py",
    "tools/pmv4_e_exact_release_packet.py",
    "tools/pmv4_e_root_receipt_readback.py",
    "tools/pmv4_e_canary_acceptance_readback.py",
    "tools/pmv4_e_ticket_owner_readback.py",
    "tools/pmv4_e_replacement_unit_bundle.py",
    "tools/pmv4_e_native_systemd_adapter.py",
    "tools/pmv4_e_systemd_root_ops.py",
    "tools/pmv4_e_native_backend_bridge.py",
    "tools/pmv4_e_native_release_contract.py",
    "tools/pmv4_e_native_root_manifest_attestation.py",
)
ROOT_COMPONENTS_PREINSTALLED=(
    "tools/independent_component_release.py",
    "tools/independent_component_host_adapter.py",
    "tools/independent_component_release_root.py",
    "implementation/kernel/signed_owner_release.py",
)
LEGACY_CONTROL_SURFACES=(
    "tools/jason_self_heal_watchdog.py",
    "tools/release_manager_host_runner.py",
    "tools/reconcile_production_host_services.sh",
)
NEW_UNITS=tuple(sorted(
    "infrastructure/pmv4-e-scheduler/systemd/"
    +("user/" if p.side=="user" else "system/")
    +name
    for p in units.PAIRS
    for name in (p.new_trigger,p.new_service)
))
OLD_INPUTS=tuple(sorted(
    "infrastructure/openclaw-operations/systemd/"
    +("user/" if p.side=="user" else "")
    +name
    for p in units.PAIRS
    for name in (p.old_trigger,p.old_service)
))
REVIEWED_PATHS=tuple(sorted(set(
    ROOT_TO_INSTALL+ROOT_COMPONENTS_PREINSTALLED+LEGACY_CONTROL_SURFACES
    +NEW_UNITS+OLD_INPUTS
)))
assert len(NEW_UNITS)==12 and len(OLD_INPUTS)==12


class StageEReleasePacketDenied(PermissionError):
    pass


def require(ok:bool,reason:str):
    if not ok:
        raise StageEReleasePacketDenied("PMV4_E_PACKET_"+reason)


def canonical(obj:dict[str,Any])->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def read_reviewed(root:Path,relative:str)->bytes:
    p=root/relative
    require(not p.is_symlink() and p.is_file(),"REVIEWED_SOURCE_MISSING")
    info=p.lstat()
    require(stat.S_ISREG(info.st_mode) and
            info.st_mode&0o002==0 and info.st_size<1_000_000
            and info.st_size>0,"REVIEWED_SOURCE_UNTRUSTED")
    return p.read_bytes()


def prepare(*,root:Path=ROOT,candidate_sha:str,rollback_sha:str,
            observed_root_policy_sha256:str|None=None,
            observed_freeze_sha256:str|None=None)->dict[str,Any]:
    require(bool(SHA40.fullmatch(candidate_sha)) and
            bool(SHA40.fullmatch(rollback_sha)) and
            candidate_sha!=rollback_sha,"RELEASE_ROLLBACK_IDENTITY_INVALID")
    files={p:sha256(read_reviewed(root,p)).hexdigest()
           for p in REVIEWED_PATHS}
    generated=units.generate(base=root)
    for path,data in generated.items():
        require(files.get(path)==sha256(data).hexdigest(),
                "UNIT_SOURCE_DRIFT")
    source_policy=parity.read_source_policy(
        root/"config/production-desired-state.json")
    exact=parity.plan_exact_unit_delta(source_policy)
    source_scope={
        "schema_version":"1.0",
        "action":ACTION,
        "candidate_sha":candidate_sha,
        "rollback_sha":rollback_sha,
        "expected_prior_root_policy_sha256":EXPECTED_PRIOR_ROOT_POLICY,
        "expected_freeze_sha256":EXPECTED_FREEZE,
        "reviewed_source_policy_sha256":exact["prior_policy_sha256"],
        "source_candidate_policy_sha256":exact["candidate_policy_sha256"],
        "retire_user":exact["retire_user_units"],
        "retire_root":exact["retire_system_units"],
        "add_user":exact["add_user_units"],
        "add_root":exact["add_system_units"],
        "exact_replacement_files_sha256":files,
        "root_installer_may_mutate_only":{
            "user_triggers":exact["retire_user_units"]+exact["add_user_units"],
            "root_triggers":exact["retire_system_units"]+exact["add_system_units"],
            "reconcile_watchdog_code":list(LEGACY_CONTROL_SURFACES),
            "desired_state":"exact_six_control_delta",
            "trusted_root":"/opt/jason/pmv4-e-trusted",
            "owner_acceptance":"/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json",
        },
        "protected_runtime_mcp_restart_allowed":False,
        "provider_writes_allowed":False,
        "production_freeze_override_allowed":False,
    }
    scope_sha=sha256(canonical(source_scope)).hexdigest()
    marker_ok=observed_root_policy_sha256==EXPECTED_PRIOR_ROOT_POLICY
    freeze_ok=observed_freeze_sha256==EXPECTED_FREEZE
    return {
        "schema_version":"1.0",
        "status":"source_packet_pending_independent_root_acceptance",
        "source_sha":candidate_sha,
        "rollback_sha":rollback_sha,
        "source_scope_sha256":scope_sha,
        "source_manifest_sha256":sha256(canonical({
            "scope_sha256":scope_sha,"files":files,
        })).hexdigest(),
        "reviewed_files":len(files),
        "reviewed_systemd_new_files":12,
        "reviewed_systemd_old_inputs":12,
        "exact_action":ACTION,
        "protected_root_policy_verified":marker_ok,
        "freeze_verified":freeze_ok,
        "source_scope":source_scope,
        "signed_owner_proof":None,
        "owner_authority_issued":False,
        "production_mutations":False,
        "production_release_ready":False,
    }


if __name__=="__main__":
    raise SystemExit(
        "Source-only packet library: call prepare() with reviewed real SHA inputs"
    )
