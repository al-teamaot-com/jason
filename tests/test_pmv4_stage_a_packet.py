"""PMv4 Stage A signed-scope preparation: no live host writes or shortcuts."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest

from tools import pmv4_stage_a_lab as lab
from tools import pmv4_stage_a_packet as packet

REPO = Path(__file__).resolve().parents[1]
SHA = "d" * 40


def scope():
    return packet.build_scope(REPO, SHA)


def labroot(tmp_path):
    # pytest fixture lives in /tmp; a second private, marked sandbox is used
    # by the offline simulator.
    destination = tmp_path / "isolated-host"
    return lab.sandbox_setup(destination)


def test_exact_stage_a_write_allowlist_and_digest_are_stable():
    a = scope()
    b = scope()
    assert a == b
    assert a["rollback_sha"] == "0" * 40
    assert a["scope_sha256"] == packet._digest(packet._canonical(
        {k: v for k, v in a.items() if k != "scope_sha256"}
    ))
    assert len(a["files"]) == len(packet.BUNDLE_FILES) + len(packet.STATIC_DOCS) + 1
    assert all(item["path"].startswith((packet.ROOT + "/", packet.HOST_CODE + "/",
                                       packet.ETC + "/")) for item in a["files"])
    assert not any(path in [x["path"] for x in a["files"]]
                   for path in packet.NO_TOUCH)
    assert a["production_services_restart"] is False
    assert a["production_freeze_change"] is False
    assert a["breaker_mutation"] is False
    assert a["owner_issuer_enabled"] is False
    assert a["provider_writes"] is False
    assert a["install_approval_required"] is True


@pytest.mark.parametrize("bad", ["", "f"*39, "A"*40, "zzz"*15, None])
def test_candidate_must_be_exact_sha(bad):
    with pytest.raises(ValueError, match="EXACT_SOURCE_SHA_REQUIRED"):
        packet.build_scope(REPO, bad)


def test_synthetic_full_install_and_empty_baseline_rollback(tmp_path):
    root = labroot(tmp_path)
    a = scope()
    sentinel = root / "var/lib/jason/openclaw/unchanged-client-ledger"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("DO_NOT_TOUCH")
    before = packet._digest(sentinel.read_bytes())
    result = lab.stage(REPO, root, a)
    assert result["status"] == "lab_installed_verified"
    assert lab.verify(REPO, root, a)["status"] == "verified"
    assert lab._mapped(root, packet.CURRENT).is_symlink()
    assert os.readlink(lab._mapped(root, packet.CURRENT)) == packet.CURRENT_TARGET
    assert lab._mapped(root, packet.ROOT + "/control/signed-owner-decisions").is_dir()
    assert not lab._mapped(root, packet.ROOT + "/control/approved-manifest.json").exists()
    assert not lab._mapped(root, packet.ROOT + "/control/gateway-token").exists()
    result = lab.rollback(REPO, root, a)
    assert result["status"] == "empty_baseline_restored"
    assert result["rollback_sha"] == "0"*40
    assert packet._digest(sentinel.read_bytes()) == before
    for forbidden in (packet.TRUST, packet.SIGNER, "/opt/jason/current"):
        assert not (root / forbidden.lstrip("/")).exists()


def test_interrupted_install_recovers_only_owned_new_objects(tmp_path):
    root = labroot(tmp_path)
    a = scope()
    with pytest.raises(InterruptedError, match="SYNTHETIC_INTERRUPTION"):
        lab.stage(REPO, root, a, stop_after_files=3)
    assert lab.verify(REPO, root, a, allow_partial=True)["status"] == "verified"
    restored = lab.rollback(REPO, root, a, allow_partial=True)
    assert restored["status"] == "empty_baseline_restored"
    assert lab._mapped(root, packet.ROOT).exists() is False


@pytest.mark.parametrize("damage", ["wrong_bytes", "extra_file", "foreign_symlink", "changed_mode"])
def test_rollback_denies_tamper_or_foreign_object_before_removal(tmp_path, damage):
    root = labroot(tmp_path)
    a = scope()
    lab.stage(REPO, root, a)
    first = lab._mapped(root, a["files"][0]["path"])
    first.chmod(0o600)
    if damage == "wrong_bytes":
        first.write_bytes(b"DIFFERENT")
        first.chmod(int(a["files"][0]["mode"], 8))
    elif damage == "extra_file":
        first.chmod(int(a["files"][0]["mode"], 8))
        lab._mapped(root, packet.ROOT + "/control/foreign").write_bytes(b"foreign")
    elif damage == "foreign_symlink":
        first.chmod(int(a["files"][0]["mode"], 8))
        lab._mapped(root, packet.ROOT + "/control/foreign").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="STAGE_A_LAB_"):
        lab.rollback(REPO, root, a)
    assert lab._mapped(root, packet.ROOT).is_dir()


def test_rollback_rejects_modified_current_pointer(tmp_path):
    root = labroot(tmp_path)
    a = scope()
    lab.stage(REPO, root, a)
    current = lab._mapped(root, packet.CURRENT)
    current.unlink()
    current.symlink_to("releases/forged")
    with pytest.raises(ValueError, match="POINTER_TAMPERED"):
        lab.rollback(REPO, root, a)


def test_lab_cannot_target_live_root_or_follow_symlink(tmp_path):
    with pytest.raises(ValueError, match="NONPRODUCTION_SANDBOX"):
        lab._sandbox(Path(packet.ROOT))
    outside = tmp_path / "link"
    outside.symlink_to(packet.ROOT)
    with pytest.raises(ValueError, match="NONPRODUCTION_SANDBOX"):
        lab._sandbox(outside)
    root = labroot(tmp_path)
    with pytest.raises(ValueError, match="PROTECTED_BOUNDARY"):
        lab._mapped(root, packet.TRUST)


@pytest.fixture
def mock_recovery(tmp_path, monkeypatch):
    root = tmp_path / "release"
    view = root / "protected-readback"
    view.mkdir(parents=True)
    source = "a" * 40
    opt = tmp_path / "opt/jason"
    (opt / "releases" / source).mkdir(parents=True)
    (opt / "current").symlink_to("releases/" + source)
    controls = {
        "schema_version": "1.0",
        "last_revalidation": {"complete": True, "revision": source},
        "last_known_good": {"manifest": {
            "complete": True, "revision": source,
            "runtime_revision": source, "mcp_revision": source,
        }},
        "circuit_breaker": {
            "state": "closed", "revalidated_revision": source,
            "updated_at": "2026-11-12T09:29:42+00:00",
        },
    }
    drift = {
        "schema_version": "1.0", "status": "pass", "problems": [],
        "observed_at": "2026-11-12T09:44:15+00:00",
    }
    history = {
        "schema_version": "1.0", "status": "root_verified_closed",
        "lkg_revision": source,
        "clean_observations": [
            "2026-11-12T09:25:29+00:00",
            "2026-11-12T09:27:29+00:00",
            "2026-11-12T09:29:30+00:00",
        ],
        "last_revalidation_attempt": {
            "result": "root_verified_closed", "revision": source,
        },
    }
    (view / "production-control-state.json").write_text(json.dumps(controls))
    (view / "production-drift.json").write_text(json.dumps(drift))
    recovery = tmp_path / "recovery.json"
    recovery.write_text(json.dumps(history))
    freeze = root / "production-deployment-freeze"
    freeze.write_text("frozen")
    hold = root / "auto-promotion-incident-hold"
    hold.write_text("held")
    (root / "production-transaction.lock").touch()
    monkeypatch.setattr(packet, "RELEASE_STATE", root)
    monkeypatch.setattr(packet, "RECOVERY", recovery)
    monkeypatch.setattr(packet, "LIVE_LKG", opt / "current")
    monkeypatch.setattr(packet, "FREEZE", freeze)
    monkeypatch.setattr(packet, "HOLD", hold)
    monkeypatch.setattr(packet, "_trusted_root_file", lambda path: True)
    monkeypatch.setattr(packet, "_root_trust_acceptable", lambda: True)
    monkeypatch.setattr(packet, "_service_signer_metadata_acceptable", lambda: True)
    monkeypatch.setattr(packet, "_existing_target_state", lambda: {
        packet.HOST_CODE: "absent", packet.ROOT: "absent",
        packet.ETC: "absent",
    })
    class FakeGuard:
        def protected_release_status(self):
            return {"ready": True, "reason": "verified"}
    monkeypatch.setattr(packet, "IndependentHostGuard", FakeGuard)
    now = datetime.fromisoformat("2026-11-12T09:45:00+00:00")
    return controls, drift, history, now, view, recovery


def test_valid_three_distinct_root_observations_and_closed_breaker(mock_recovery):
    *_, at, _, _ = mock_recovery
    proof = packet.recovery_readback(now=at)
    assert proof["preflight_evidence_satisfied"] is True
    assert proof["breaker_state"] == "closed"
    assert proof["recovery_observation_count"] == 3
    assert proof["freeze_present"] is True
    assert proof["production_install_authorized"] is False
    assert proof["needs_fresh_native_root_revalidation_before_install"] is True


@pytest.mark.parametrize("change", [
    "opened", "wrong_revalidated_sha", "stale_drift",
    "fewer_samples", "replayed_sample", "failed_root_attempt",
    "bad_lkg", "native_revalidation_unverified", "freeze_absent",
])
def test_root_preflight_does_not_confuse_drift_pass_with_governed_closure(
    mock_recovery, change,
):
    ctrl, drift, history, at, view, recovery = mock_recovery
    if change == "opened": ctrl["circuit_breaker"]["state"] = "open"
    if change == "wrong_revalidated_sha":
        ctrl["circuit_breaker"]["revalidated_revision"] = "f" * 40
    if change == "stale_drift": drift["observed_at"] = "2026-11-12T09:35:00+00:00"
    if change == "fewer_samples": history["clean_observations"] = history["clean_observations"][:2]
    if change == "replayed_sample": history["clean_observations"][1] = history["clean_observations"][0]
    if change == "failed_root_attempt":
        history["last_revalidation_attempt"]["result"] = "root_revalidation_rejected"
    if change == "bad_lkg":
        ctrl["last_known_good"]["manifest"]["mcp_revision"] = "b" * 40
    if change == "native_revalidation_unverified":
        ctrl["last_revalidation"]["complete"] = False
    if change == "freeze_absent": packet.FREEZE.unlink()
    (view / "production-control-state.json").write_text(json.dumps(ctrl))
    (view / "production-drift.json").write_text(json.dumps(drift))
    recovery.write_text(json.dumps(history))
    assert packet.recovery_readback(now=at)["preflight_evidence_satisfied"] is False


def test_lab_rejects_symlinked_parent_to_production(tmp_path):
    root = labroot(tmp_path)
    (root / "var").symlink_to("/var")
    with pytest.raises(ValueError, match="PATH_TRAVERSAL"):
        lab._mapped(root, packet.ROOT + "/control/shadow-freeze.json")
    with pytest.raises(ValueError, match="PATH_TRAVERSAL"):
        lab.stage(REPO, root, scope())


def test_source_package_requires_exact_clean_git_head(monkeypatch):
    calls = []
    def checked(args, **kwargs):
        calls.append(args)
        return SHA + "\n" if "rev-parse" in args else ""
    monkeypatch.setattr(packet.subprocess, "check_output", checked)
    packet.verify_exact_repository_head(REPO, SHA)
    assert len(calls) == 2
    monkeypatch.setattr(
        packet.subprocess, "check_output",
        lambda args, **kwargs: "changed.py\n" if "status" in args else SHA + "\n",
    )
    with pytest.raises(ValueError, match="NOT_PINNED_AND_CLEAN"):
        packet.verify_exact_repository_head(REPO, SHA)
    monkeypatch.setattr(
        packet.subprocess, "check_output",
        lambda args, **kwargs: "a" * 40 + "\n" if "rev-parse" in args else "",
    )
    with pytest.raises(ValueError, match="NOT_PINNED_AND_CLEAN"):
        packet.verify_exact_repository_head(REPO, SHA)


def test_new_native_release_can_supersede_historical_recovery_sha(
    mock_recovery, monkeypatch, tmp_path,
):
    control, drift, history, at, view, recovery = mock_recovery
    new = "b" * 40
    root = packet.LIVE_LKG.parent
    (root / "releases" / new).mkdir(parents=True)
    packet.LIVE_LKG.unlink()
    packet.LIVE_LKG.symlink_to("releases/" + new)
    control["last_known_good"]["manifest"].update({
        "revision": new, "runtime_revision": new, "mcp_revision": new,
    })
    control["circuit_breaker"]["revalidated_revision"] = new
    control["last_revalidation"]["revision"] = new
    (view / "production-control-state.json").write_text(json.dumps(control))
    result = packet.recovery_readback(now=at)
    assert result["preflight_evidence_satisfied"] is True
    assert result["historical_recovery_matches_current_lkg"] is False
    assert result["historical_recovery_revision"] == "a" * 40


def test_recovery_history_does_not_accept_spoofed_prior_revision(mock_recovery):
    control, drift, history, at, view, recovery = mock_recovery
    history["last_revalidation_attempt"]["revision"] = "f" * 40
    recovery.write_text(json.dumps(history))
    result = packet.recovery_readback(now=at)
    assert result["recovery_observations_valid"] is False
    assert result["preflight_evidence_satisfied"] is False


def test_root_source_attestation_never_uses_developer_checkout():
    with pytest.raises(ValueError, match="STAGE_A_ROOT_IMMUTABLE_SOURCE_REQUIRED"):
        packet.verify_immutable_host_release_source(REPO, SHA)
    root_worker = (REPO / "tools/release_host_reconcile_worker.py").read_text()
    assert 'sys.path.insert(0, str(REPO))' not in root_worker
    assert '"PMV4_NATIVE_ROOT_DEPENDENCY_SOURCE_DRIFT"' in root_worker
    assert 'receipt = module.execute_native_stage_a0_request(' in root_worker
    assert 'repo=Path("/opt/jason/releases") / candidate' in root_worker
