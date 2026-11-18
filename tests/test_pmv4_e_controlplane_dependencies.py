"""Stage E source-only dependencies must not be mistaken for cutover parity."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil

import pytest

from tools import pmv4_e_controlplane_dependencies as dep
from tools import pmv4_e_retirement_readiness as stage

ROOT=Path(__file__).resolve().parents[1]


def fixture_tree(tmp_path):
    for name in dep.SOURCE_ALLOWLIST:
        p=tmp_path/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes((ROOT/name).read_bytes())
    return tmp_path


def test_authoritative_source_still_activates_old_worker_and_old_timers():
    x=dep.inspect(source_root=ROOT)
    assert x["status"]=="retirement_blocked_pending_replacement_acceptance"
    assert x["legacy_dependencies"]=={
        "self_heal_requires_legacy_user_timers":True,
        "self_heal_restarts_legacy_engineering_worker":True,
        "release_manager_requires_legacy_timers":True,
        "root_host_reconciler_reinstalls_legacy_worker":True,
    }
    assert len(x["source_refs"])==3
    for name,entry in x["source_refs"].items():
        assert entry["sha256"]==sha256((ROOT/name).read_bytes()).hexdigest()
        assert entry["byte_count"]>0
    assert "PMV4_E_WATCHDOG_RESTARTS_LEGACY_WORKER" in x["blocking_gates"]
    assert "PMV4_E_ROOT_HOST_RECONCILER_REINSTALLS_LEGACY_WORKER" in x["blocking_gates"]
    assert x["replacement_controller_root_acceptance_verified"] is False
    assert x["legacy_release_worker_retirement_authorized"] is False
    assert x["production_mutations"] is False
    assert x["provider_calls"] is False


def test_disappearing_legacy_tokens_are_not_accepted_as_root_parity(tmp_path):
    root=fixture_tree(tmp_path)
    for name in dep.SOURCE_ALLOWLIST:
        p=root/name
        text=p.read_text()
        text=text.replace("jason-release-manager.timer","jason-pmv4-component-release.timer")
        text=text.replace("jason-support-repair-worker.timer","jason-pmv4-engineering.timer")
        text=text.replace("jason-support-repair-worker.service","jason-pmv4-engineering.service")
        text=text.replace("install_support_repair_host_worker.py","install_pmv4_engineering.py")
        p.write_text(text)
    x=dep.inspect(source_root=root)
    assert all(value is False for value in x["legacy_dependencies"].values())
    assert x["status"]=="retirement_blocked_pending_replacement_acceptance"
    assert x["blocking_gates"]==[
        "PMV4_E_REPLACEMENT_CONTROLPLANE_ROOT_ACCEPTANCE_MISSING"
    ]
    assert x["legacy_release_worker_retirement_authorized"] is False


def test_unreviewed_source_path_denied(tmp_path):
    with pytest.raises(dep.ControlplaneEvidenceDenied,match="SOURCE_NOT_APPROVED"):
        dep.read_exact_source(tmp_path,"/etc/shadow")


def test_missing_root_reconciler_source_denied(tmp_path):
    root=fixture_tree(tmp_path)
    (root/dep.ROOT_RECONCILER).unlink()
    with pytest.raises(dep.ControlplaneEvidenceDenied,match="SOURCE_UNAVAILABLE"):
        dep.inspect(source_root=root)


def test_symlinked_watchdog_source_denied(tmp_path):
    root=fixture_tree(tmp_path)
    p=root/dep.WATCHDOG
    p.unlink();p.symlink_to(root/dep.RELEASE_MANAGER)
    with pytest.raises(dep.ControlplaneEvidenceDenied,match="SOURCE_UNTRUSTED"):
        dep.inspect(source_root=root)


def test_world_writable_source_denied(tmp_path):
    root=fixture_tree(tmp_path)
    p=root/dep.RELEASE_MANAGER
    p.chmod(0o666)
    with pytest.raises(dep.ControlplaneEvidenceDenied,match="SOURCE_UNTRUSTED"):
        dep.inspect(source_root=root)


def test_source_size_limit_denied(tmp_path):
    root=fixture_tree(tmp_path)
    p=root/dep.WATCHDOG
    p.write_bytes(b"A"*(dep.SOURCE_LIMIT+1))
    with pytest.raises(dep.ControlplaneEvidenceDenied,match="SOURCE_UNTRUSTED"):
        dep.inspect(source_root=root)


def test_no_controlplane_deploy_or_emergency_override_code():
    text=Path(dep.__file__).read_text()
    for token in (
        "docker compose up", "systemctl disable",
        "systemctl stop", "subprocess.run(",
        "os.chown(", "os.unlink(", "os.replace(",
        "force_close_breaker",
    ):
        assert token not in text
    assert '"production_mutations":False' in text
    assert '"legacy_release_worker_retirement_authorized":False' in text


def test_stage_e_blocks_if_source_inspection_fails(monkeypatch,tmp_path):
    def unavailable(**kwargs):
        raise dep.ControlplaneEvidenceDenied("source-not-trusted")
    monkeypatch.setattr(stage.controlplane,"inspect",unavailable)
    monkeypatch.setattr(stage,"units_readback",lambda **kw:{
        "legacy_user":[],"legacy_system":[],"continuity":[]})
    monkeypatch.setattr(stage,"stage_d_readback",lambda **kw:{"live":False})
    monkeypatch.setattr(stage,"stage_a1_readback",lambda **kw:{"live":False})
    monkeypatch.setattr(stage,"scan_summary",lambda *args,**kw:{"status":"unavailable"})
    monkeypatch.setattr(stage,"command",lambda *args,**kw:"inactive")
    result=stage.inspect(policy=ROOT/"config/production-desired-state.json",
                         runner=lambda *a,**kw:None)
    assert "PMV4_E_CONTROLPLANE_SOURCE_CANNOT_BE_VERIFIED" in result["blocking_gates"]
    assert "PMV4_E_REPLACEMENT_CONTROLPLANE_ROOT_ACCEPTANCE_MISSING" in result["blocking_gates"]
    assert result["governed_release_authorized"] is False
    assert result["service_mutations"] is False
