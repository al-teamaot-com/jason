"""Low-privilege scoped-backport release request is never release authority."""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from tools import scoped_backport_release as core
from tools import scoped_backport_release_request as req
from tools import scoped_backport_root_install as installer
from tools import scoped_backport_native_root as native

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / core.RELEASE_MANIFEST).read_text())
MAIN = "b44772f78fd71bc054f952967e1bd78bccf0b17c"


def o():
    return core.make_offer(MANIFEST, main_sha=MAIN)


@pytest.fixture(autouse=True)
def simulated_aot_host_user(monkeypatch):
    # GitHub Actions runners do not have the Jason host's 'al' account.
    # The real native request path still requires that account to exist.
    monkeypatch.setattr(req, "aot_operator_uid", os.getuid)


def test_staging_request_is_non_authoritative_and_exact():
    x = req.request("scoped_backport_stage", o())
    assert x["release_id"] == "release-87dfd07ae67d2d99"
    assert x["candidate_sha"] == MANIFEST["candidate_sha"]
    assert x["rollback_sha"] == MANIFEST["rollback_sha"]
    assert "signed_owner_proof" not in x
    assert "offer_sha256" not in x
    assert "production_mutations" not in x


@pytest.mark.parametrize("action", ("scoped_backport_promote", "scoped_backport_recover"))
def test_promotion_and_recovery_require_exact_offer_hash(action):
    with pytest.raises(core.ScopedBackportDenied, match="EXACT_OFFER_SHA256_REQUIRED"):
        req.request(action, o())
    assert req.request(action, o(), offer_sha256="a" * 64)["offer_sha256"] == "a" * 64


def test_stage_cannot_preapprove_offer():
    with pytest.raises(core.ScopedBackportDenied, match="STAGE_HAS_NO_PREAPPROVED_OFFER"):
        req.request("scoped_backport_stage", o(), offer_sha256="b" * 64)


def test_unknown_root_action_denied():
    with pytest.raises(core.ScopedBackportDenied, match="ROOT_ACTION_NOT_ALLOWED"):
        req.request("run_arbitrary_code", o())


def test_default_host_without_installed_root_handler_fails_closed(tmp_path):
    x = req.request("scoped_backport_stage", o())
    spool = tmp_path / "requests"
    spool.mkdir(mode=0o700)
    with pytest.raises(core.ScopedBackportDenied, match="ROOT_HANDLER_OR_POLICY_UNAVAILABLE"):
        req.submit(x, spool=spool,
                   handler=tmp_path / "uninstalled-handler.py",
                   policy=tmp_path / "uninstalled-policy.json")
    assert tuple(spool.iterdir()) == ()


def test_unprivileged_forged_policy_is_denied(tmp_path):
    policy = tmp_path / "root-policy.json"
    script = tmp_path / "fake-worker.py"
    script.write_text("print('fake')")
    policy.write_text(json.dumps({
        "schema_version": "1.0", "profile": "governed-scoped-backport-v1",
        "trusted_source_sha": "a" * 40, "root_handler_sha256": "b" * 64,
        "native_root_control_supported": True,
        "automatic_rollback_recovery_installed": True,
        "exact_signed_owner_approval_required": True,
    }))
    with pytest.raises(core.ScopedBackportDenied, match="ROOT_ATTESTATION_PARENT_UNTRUSTED"):
        req.installed_attestation(handler=script, policy=policy)


def test_typed_request_enqueue_requires_independent_trust(monkeypatch, tmp_path):
    x = req.request("scoped_backport_stage", o())
    spool = tmp_path / "requests"
    spool.mkdir(mode=0o700)
    monkeypatch.setattr(req, "installed_attestation", lambda **kw: {
        "schema_version": "1.0", "trusted_source_sha": MAIN})
    result = req.submit(x, spool=spool)
    assert result["status"] == "queued_for_independent_root_validation_not_approved"
    assert result["owner_approval_recorded"] is False
    assert result["native_release_record_created"] is False
    assert result["production_mutations"] is False
    items = tuple(spool.glob("*.json"))
    assert len(items) == 1
    assert json.loads(items[0].read_text()) == x
    assert items[0].stat().st_mode & 0o777 == 0o600
    with pytest.raises(core.ScopedBackportDenied, match="ROOT_REQUEST_REPLAY"):
        req.submit(x, spool=spool)


def test_unsafe_spool_and_modified_payload_fail_closed(monkeypatch, tmp_path):
    x = req.request("scoped_backport_stage", o())
    monkeypatch.setattr(req, "installed_attestation", lambda **kw: {})
    bad = dict(x)
    bad["command"] = "docker rm -f jason-runtime"
    with pytest.raises(core.ScopedBackportDenied, match="ROOT_REQUEST_SCHEMA"):
        req.submit(bad, spool=tmp_path)
    tmp_path.chmod(0o755)
    with pytest.raises(core.ScopedBackportDenied, match="ROOT_REQUEST_SPOOL_UNTRUSTED"):
        req.submit(x, spool=tmp_path)


@pytest.mark.parametrize("field", ("candidate_sha", "rollback_sha", "protected_main_sha",
                                   "manifest_sha256", "scope_sha256", "release_id"))
def test_forged_request_fields_rejected_before_worker(field, monkeypatch, tmp_path):
    monkeypatch.setattr(req, "installed_attestation", lambda **kw: {})
    x = req.request("scoped_backport_stage", o())
    x[field] = "NOT_AN_EXACT_ID"
    spool = tmp_path / "requests"
    spool.mkdir(mode=0o700)
    with pytest.raises(core.ScopedBackportDenied, match="ROOT_REQUEST_SCHEMA_OR_BINDING_INVALID"):
        req.submit(x, spool=spool)
    assert list(spool.iterdir()) == []



def test_installer_public_attestation_native_request_end_to_end_no_release(monkeypatch, tmp_path):
    """Published installer receipt must match operator client and root worker.

    This deliberately tests the real three-module contract, with only
    root-owned filesystem reads simulated. No production mutation occurs.
    """
    worker_bytes = b"immutable root worker test fixture\n"
    private_policy = {
        "schema_version": "1.0", "profile": "governed-scoped-backport-v1",
        "trusted_source_sha": MAIN, "reviewed_ci_sha": "3" * 40,
        "root_handler_sha256": sha256(worker_bytes).hexdigest(),
        "native_root_control_supported": True,
        "automatic_rollback_recovery_installed": True,
        "exact_signed_owner_approval_required": True,
        "no_global_owner_elevation": True,
    }
    public = installer.build_public_attestation(private_policy)
    assert set(public) == {
        "schema_version", "profile", "trusted_source_sha", "reviewed_ci_sha",
        "root_handler_sha256", "native_root_control_supported",
        "automatic_rollback_recovery_installed",
        "exact_signed_owner_approval_required",
    }
    assert "no_global_owner_elevation" not in public
    assert req.ROOT_HANDLER == installer.INSTALL_ROOT / "tools/scoped_backport_native_root.py"
    assert req.ROOT_POLICY == installer.ROOT_PUBLIC_ATTEST

    def read_root(path, **kwargs):
        if path == req.ROOT_POLICY:
            return json.dumps(public).encode()
        if path == req.ROOT_HANDLER:
            return worker_bytes
        pytest.fail("unreviewed root path in request verifier")
    monkeypatch.setattr(req, "_root_file", read_root)
    assert req.installed_attestation() == public
    spool = tmp_path / "requests"
    spool.mkdir(mode=0o700)
    payload = req.request("scoped_backport_stage", o())
    assert native._verify_typed_request(payload, o()) == "scoped_backport_stage"
    queued = req.submit(payload, spool=spool)
    assert queued["status"] == "queued_for_independent_root_validation_not_approved"
    assert queued["native_release_record_created"] is False
    assert queued["owner_approval_recorded"] is False
    assert queued["production_mutations"] is False
    assert json.loads((spool / (payload["request_id"] + ".json")).read_text()) == payload


def test_root_public_attestation_must_match_exact_installed_worker(monkeypatch):
    worker_bytes = b"scoped worker fixture\n"
    private_policy = {
        "profile": "governed-scoped-backport-v1",
        "trusted_source_sha": MAIN, "reviewed_ci_sha": "3" * 40,
        "root_handler_sha256": sha256(worker_bytes).hexdigest(),
        "native_root_control_supported": True,
        "automatic_rollback_recovery_installed": True,
        "exact_signed_owner_approval_required": True,
    }
    public = installer.build_public_attestation(private_policy)
    def read_root(path, **kwargs):
        if path == req.ROOT_POLICY:
            return json.dumps(public).encode()
        if path == req.ROOT_HANDLER:
            return worker_bytes + b"tampered"
        pytest.fail("unreviewed root path")
    monkeypatch.setattr(req, "_root_file", read_root)
    with pytest.raises(core.ScopedBackportDenied, match="ROOT_HANDLER_SHA256_DRIFT"):
        req.installed_attestation()


def test_root_private_policy_not_exposed_by_public_attestation():
    policy = {
        "profile": "governed-scoped-backport-v1",
        "trusted_source_sha": MAIN, "reviewed_ci_sha": "3" * 40,
        "root_handler_sha256": "4" * 64,
        "native_root_control_supported": True,
        "automatic_rollback_recovery_installed": True,
        "exact_signed_owner_approval_required": True,
        "native_deploy_sha256": "5" * 64,
        "core_sha256": "6" * 64,
    }
    public = installer.build_public_attestation(policy)
    assert "native_deploy_sha256" not in public
    assert "core_sha256" not in public
    assert public["reviewed_ci_sha"] == "3" * 40


def test_source_install_directories_world_readable_not_writable():
    import inspect
    src = inspect.getsource(installer.install)
    for leaf in ("INSTALL_ROOT", 'INSTALL_ROOT / "tools"',
                 'INSTALL_ROOT / "implementation"',
                 'INSTALL_ROOT / "implementation/kernel"'):
        assert f"_root_dir({leaf}, mode=0o755)" in src
    assert "_root_dir(ROOT_STATE)" in src
    assert "_write_exclusive(ROOT_PUBLIC_ATTEST" in src
    assert "mode=0o644" in src
