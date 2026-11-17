"""Source-only exact installation plan and authorization boundary regressions."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from tools import catalog_scoped_root_install_plan as p
from tools.catalog_scoped_promotion_bundle import FILES

MAIN = "1b804ea6cff8efedc4f9b29b3dddaf45e86e8f82"
BASE = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
SNAP = "755fa5fe3f75958fee2427a0af0777dd242d8f00"


def fake_offer():
    return {
        "protected_main_sha": MAIN,
        "candidate_sha": SNAP,
        "rollback_sha": BASE,
        "scope_sha256": "d91998d980fc9b19105270e95067ded1a2068aaecf9ba59d5de642163dbc5ec9",
        "fresh_admission_receipt_sha256": "add8327f9cb6b0cdc9cb9a6006d8038ec71ed2b914e3e1fd6a144f7a55392272",
        "manifest_sha256": "4712f94dc35e1d6781fe6e8c02b57278da9bd0f10ebedaea130c2934f1b5f45b",
        "runtime_image_id": "sha256:" + "a" * 64,
        "mcp_image_id": "sha256:" + "b" * 64,
        "rollback_runtime_image_id": "sha256:" + "c" * 64,
        "rollback_mcp_image_id": "sha256:" + "d" * 64,
        "freeze_sha256": FREEZE,
    }


@pytest.fixture
def mock_source(monkeypatch):
    offer=fake_offer()
    monkeypatch.setattr(p, "repo_revision", lambda repo: MAIN)
    monkeypatch.setattr(p, "load_manifest", lambda repo, main_sha: {
        "rollback_sha": BASE, "freeze_sha256": FREEZE})
    monkeypatch.setattr(p, "historical_receipt_verified", lambda historical, manifest: None)
    monkeypatch.setattr(p, "make_offer", lambda manifest, old, new: offer)
    def read(repo,*args):
        assert args[0] == "show"
        assert args[1].startswith(MAIN + ":")
        return ("reviewed-source:" + args[1]).encode()
    monkeypatch.setattr(p, "source_git", read)
    host={"rollback_host_revision":BASE,"freeze_sha256":FREEZE,
          "root_worker_before_sha256":"1" * 64,
          "pinned_owner_pubkey_file_sha256":"2" * 64,
          "root_state_readback_required":True,
          "live_root_install_verified":False}
    return offer,host


def test_complete_exact_install_plan_and_two_separate_owner_gates(mock_source):
    offer,host=mock_source
    a=p.build_install_plan(Path('/tmp/unused'), {}, {}, host, expected_source_sha=MAIN)
    b=p.build_install_plan(Path('/tmp/unused'), {}, {}, host, expected_source_sha=MAIN)
    assert a==b
    assert a["status"]=="SOURCE_ONLY_ROOT_INSTALL_PREPARED_NOT_AUTHORIZED"
    assert a["source_sha"]==MAIN
    assert a["immutable_candidate_snapshot_sha"]==SNAP
    assert a["rollback_source_sha"]==BASE
    assert len(a["root_file_plan"])==len(FILES)
    assert len(a["directories_after_separate_approval"])==8
    assert a["root_policy_after_separate_approval"]["no_global_owner_elevation"] is True
    assert a["production_mutations"] is False and a["provider_writes"] is False
    assert a["owner_approval_recorded"] is False
    assert a["signed_exact_root_install_approval_required"] is True
    assert a["signed_separate_image_promotion_approval_required"] is True
    assert a["separate_autotask_provider_test_write_approval_required"] is True
    assert a["installation_executable_in_source_only_mode"] is False
    assert a["install_plan_sha256"]==sha256(p.canonical({k:v for k,v in a.items() if k!="install_plan_sha256"})).hexdigest()


def test_root_worker_and_recovery_unit_destinations_are_exact():
    worker=p.target_for_source("tools/release_host_reconcile_worker.py")
    assert worker["destination"]=="/usr/local/lib/jason/release_host_reconcile_worker.py"
    assert worker["mode"]=="0755"
    for name in ("jason-catalog-scoped-recovery.timer", "jason-catalog-scoped-recovery.service"):
        info=p.target_for_source("infrastructure/openclaw-operations/systemd/"+name)
        assert info["destination"]=="/etc/systemd/system/"+name
        assert info["mode"]=="0644"
    control=p.target_for_source("tools/catalog_scoped_promotion_host.py")
    assert control["destination"].startswith("/usr/local/lib/jason/catalog-scoped-promotion/")
    assert control["uid"]=="root" and control["mode"]=="0644"


@pytest.mark.parametrize("relative",[
    "tools/owner-elevation.py", "../../etc/passwd", "/etc/passwd",
    "tools/../etc/passwd", "", "tools/release_host_reconcile_worker.py/extra",
])
def test_unknown_source_path_is_denied(relative):
    with pytest.raises(p.CatalogRootInstallPlanDenied):
        p.target_for_source(relative)


def test_protected_main_source_movement_denied(mock_source,monkeypatch):
    offer,host=mock_source
    monkeypatch.setattr(p,"repo_revision",lambda repo:"e"*40)
    with pytest.raises(p.CatalogRootInstallPlanDenied,match="PROTECTED_MAIN_MOVED"):
        p.build_install_plan(Path('/tmp/unused'),{},{},host,expected_source_sha=MAIN)


@pytest.mark.parametrize("changed", [
    {"rollback_host_revision":"a"*40},
    {"freeze_sha256":"0"*64},
    {"live_root_install_verified":True},
    {"root_state_readback_required":False},
])
def test_changed_live_evidence_denied(mock_source,changed):
    offer,host=mock_source
    bad=dict(host,**changed)
    with pytest.raises(p.CatalogRootInstallPlanDenied):
        p.build_install_plan(Path('/tmp/unused'),{},{},bad,expected_source_sha=MAIN)


def test_policy_exact_key_schema_and_hashes(mock_source):
    offer,host=mock_source
    plan=p.build_install_plan(Path('/tmp/unused'),{},{},host,expected_source_sha=MAIN)
    policy=plan["root_policy_after_separate_approval"]
    assert set(policy)==p.POLICY_FIELDS
    assert policy["source_sha"]==MAIN
    assert policy["root_worker_sha256"]==next(x["sha256"] for x in plan["root_file_plan"] if x["source"]=="tools/release_host_reconcile_worker.py")
    assert policy["automatic_recovery_installed"] is True
    assert policy["native_root_control_supported"] is True


def test_source_blob_missing_fails_before_install(mock_source,monkeypatch):
    offer,host=mock_source
    monkeypatch.setattr(p,"source_git",lambda *args:b"")
    with pytest.raises(p.CatalogRootInstallPlanDenied,match="ROOT_BUNDLE_SOURCE_UNAVAILABLE"):
        p.build_install_plan(Path('/tmp/unused'),{},{},host,expected_source_sha=MAIN)


def test_no_apply_switch_or_execution_helper_exposed():
    import inspect
    source=inspect.getsource(p.main)
    assert "--apply" not in source
    assert "systemctl" not in source
    assert "docker" not in source
    assert "sudo" not in source
