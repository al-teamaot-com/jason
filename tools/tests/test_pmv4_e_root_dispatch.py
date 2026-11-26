"""Root dispatcher requires the original signed exact Owner request."""
import copy
from hashlib import sha256
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from implementation.kernel import signed_owner_release as signer
from tools import release_host_reconcile_worker as worker
from tools.tests.test_pmv4_e_forwarded_owner_request import signed_request
from tools.tests.test_pmv4_e_signed_native_ledger import KEY


def envelope():
    _, owner = signed_request()
    candidate = owner["candidate_sha"]
    aid = owner["signed_owner_proof"]["payload"]["approval_id"]
    return {
        "request_id": "pmv4-e-" + candidate[:16] + "-" + aid[10:],
        "source_revision": candidate, "action": "pmv4_e_cutover",
        "owner_request": owner,
    }


def store(tmp_path, request):
    path = tmp_path / (request["request_id"] + ".json")
    path.write_text(json.dumps(request))
    path.chmod(0o600)
    return path


@pytest.fixture
def operator(monkeypatch):
    account_lookup = SimpleNamespace(
        getpwnam=lambda _: SimpleNamespace(pw_uid=os.getuid()),
    )
    monkeypatch.setattr(worker, "pwd", account_lookup)


def test_spool_request_requires_exact_shape_and_owner(operator, tmp_path):
    request = envelope()
    assert worker._read_request(store(tmp_path, request)) == request


@pytest.mark.parametrize("change", [
    "action", "candidate", "rollback", "scope", "extra", "id", "mode", "hardlink",
])
def test_malformed_spool_request_is_denied(operator, tmp_path, change):
    request = envelope()
    if change == "action":
        request["action"] = "other"
    if change == "candidate":
        request["owner_request"]["candidate_sha"] = "f" * 40
    if change == "rollback":
        request["owner_request"]["rollback_sha"] = request["source_revision"]
    if change == "scope":
        request["owner_request"]["scope_sha256"] = "bad"
    if change == "extra":
        request["extra"] = True
    if change == "id":
        request["owner_request"]["request_id"] = "incorrect"
    path = store(tmp_path, request)
    if change == "mode":
        path.chmod(0o644)
    if change == "hardlink":
        os.link(path, tmp_path / "other")
    with pytest.raises(worker.HostReconcileError):
        worker._read_request(path)


def test_duplicate_or_oversized_spool_request_is_denied(operator, tmp_path):
    request = envelope()
    path = store(tmp_path, request)
    path.write_text('{"action":"other","action":"pmv4_e_cutover"}')
    with pytest.raises(worker.HostReconcileError, match="duplicate"):
        worker._read_request(path)
    path.write_bytes(b"x" * 1048577)
    with pytest.raises(worker.HostReconcileError, match="size"):
        worker._read_request(path)


@pytest.fixture
def dispatch(monkeypatch):
    request = envelope()
    owner = request["owner_request"]
    entry = b"pinned bootstrap"
    guard = b"pinned scope guard"
    ci_script = b"pinned ci refresh"
    verifier = b"pinned owner verifier"
    policy = {
        "candidate_sha": owner["candidate_sha"],
        "rollback_sha": owner["rollback_sha"],
        "scope_sha256": owner["scope_sha256"],
        "manifest_sha256": owner["manifest_sha256"],
        "freeze_sha256": owner["freeze_sha256"],
        "bootstrap_sha256": sha256(entry).hexdigest(),
        "scope_guard_sha256": sha256(guard).hexdigest(),
        "ci_refresh_sha256": sha256(ci_script).hexdigest(),
    }
    raw_files = {
        worker.STAGE_E_ENTRY: entry,
        worker.STAGE_E_TRUST / "tools/pmv4_e_source_scope_guard.py": guard,
        worker.STAGE_E_TRUST / "tools/pmv4_e_ci_refresh.py": ci_script,
        worker.ROOT_OWNER_PROOF_VERIFIER: verifier,
    }
    calls = []
    monkeypatch.setattr(worker.os, "geteuid", lambda: 0)
    monkeypatch.setattr(worker, "_stage_e_dispatch_policy", lambda: policy)
    monkeypatch.setattr(worker, "_stage_e_root_directory", lambda *a, **k: None)
    monkeypatch.setattr(worker, "_stage_e_root_file", lambda path, **kw: raw_files[path])
    monkeypatch.setattr(worker, "STAGE_E_SIGNER_SHA256", sha256(verifier).hexdigest())
    monkeypatch.setattr(worker, "_trusted_owner_proof_module", lambda: SimpleNamespace(
        read_pinned_root_owner_public_key=lambda _: KEY.public_key(),
        verify_exact_owner_release=signer.verify_exact_owner_release))
    monkeypatch.setattr(worker, "_root_owner_identity_is_active", lambda *a: True)
    monkeypatch.setattr(worker, "_stage_e_record_verified_request",
                        lambda *a: calls.append(("record", a)))
    monkeypatch.setattr(worker, "_verify_main", lambda sha: calls.append(("main", sha)))

    def run(command, **kwargs):
        if command[3].endswith("/pmv4_e_ci_refresh.py"):
            calls.append(("ci", command, kwargs))
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "status": "fresh_protected_ci_verified",
                "candidate_sha": owner["candidate_sha"],
            }))
        calls.append(("run", command, kwargs))
        aid = owner["signed_owner_proof"]["payload"]["approval_id"]
        receipt = {
            "status": "native_stage_e_six_unit_accepted",
            "candidate_sha": owner["candidate_sha"],
            "rollback_sha": owner["rollback_sha"],
            "approval_id": aid, "protected_services_changed": False,
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "status": "native_stage_e_six_unit_accepted",
            "candidate_sha": owner["candidate_sha"],
            "original_native_receipt": receipt,
        }))
    monkeypatch.setattr(worker.subprocess, "run", run)
    return request, policy, calls


def test_verified_owner_is_recorded_then_same_proof_goes_to_root(dispatch):
    request, policy, calls = dispatch
    result = worker._process_stage_e_request(request)
    assert result["status"] == "native_stage_e_six_unit_accepted"
    assert [c[0] for c in calls] == ["record", "main", "ci", "run"]
    cmd, kw = calls[3][1:]
    assert cmd[:3] == ["/usr/bin/python3", "-I", "-B"]
    assert "--stage-and-promote" in cmd and "--owner-request-stdin" in cmd
    assert json.loads(kw["input"]) == request["owner_request"]
    assert kw["env"] == {"PATH": "/usr/bin:/bin"}


@pytest.mark.parametrize("change", ["policy", "signature", "identity", "bootstrap"])
def test_bad_binding_signature_identity_or_code_never_dispatches(dispatch, monkeypatch, change):
    request, policy, calls = dispatch
    if change == "policy":
        policy["scope_sha256"] = "f" * 64
    if change == "signature":
        request["owner_request"]["signed_owner_proof"]["signature_base64url"] = "A" * 86
    if change == "identity":
        monkeypatch.setattr(worker, "_root_owner_identity_is_active", lambda *a: False)
    if change == "bootstrap":
        policy["bootstrap_sha256"] = "f" * 64
    with pytest.raises((worker.HostReconcileError, PermissionError)):
        worker._process_stage_e_request(request)
    assert calls == []


@pytest.mark.parametrize("field,bad", [
    ("status", "rejected"), ("candidate_sha", "f" * 40),
    ("rollback_sha", "f" * 40), ("approval_id", "owner-mcp-" + "f" * 32),
    ("protected_services_changed", True),
])
def test_native_receipt_must_match_exact_approval(dispatch, monkeypatch, field, bad):
    request, _, calls = dispatch
    owner = request["owner_request"]
    native = {
        "status": "native_stage_e_six_unit_accepted",
        "candidate_sha": owner["candidate_sha"], "rollback_sha": owner["rollback_sha"],
        "approval_id": owner["signed_owner_proof"]["payload"]["approval_id"],
        "protected_services_changed": False,
    }
    native[field] = bad
    output = {"status": "native_stage_e_six_unit_accepted",
              "candidate_sha": owner["candidate_sha"], "original_native_receipt": native}
    def run(command, **kwargs):
        if command[3].endswith("/pmv4_e_ci_refresh.py"):
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "status": "fresh_protected_ci_verified",
                "candidate_sha": owner["candidate_sha"],
            }))
        return SimpleNamespace(returncode=0, stdout=json.dumps(output))
    monkeypatch.setattr(worker.subprocess, "run", run)
    with pytest.raises(worker.HostReconcileError, match="RECEIPT_MISMATCH"):
        worker._process_stage_e_request(request)


def test_verified_root_record_is_idempotent_and_never_overwritten(tmp_path, monkeypatch):
    request = envelope()["owner_request"]
    aid = request["signed_owner_proof"]["payload"]["approval_id"]
    monkeypatch.setattr(worker, "STAGE_E_RECORDS", tmp_path)
    monkeypatch.setattr(worker, "_stage_e_root_directory", lambda *a, **kw: None)
    monkeypatch.setattr(worker, "_stage_e_root_file",
                        lambda path, **kw: Path(path).read_bytes())
    worker._stage_e_record_verified_request(request, aid)
    first = (tmp_path / (aid + ".json")).read_bytes()
    worker._stage_e_record_verified_request(request, aid)
    other = copy.deepcopy(request)
    other["scope_sha256"] = "f" * 64
    with pytest.raises(worker.HostReconcileError, match="CONFLICT"):
        worker._stage_e_record_verified_request(other, aid)
    assert (tmp_path / (aid + ".json")).read_bytes() == first
    assert sorted(p.name for p in tmp_path.iterdir()) == [aid + ".json"]


def test_failed_ci_refresh_keeps_record_but_never_starts_bootstrap(dispatch, monkeypatch):
    request, _, calls = dispatch
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=1, stdout="DENIED", stderr=""))
    with pytest.raises(worker.HostReconcileError, match="CI_REFRESH_FAILED"):
        worker._process_stage_e_request(request)
    assert [c[0] for c in calls] == ["record", "main"]


def test_root_policy_requires_exact_typed_fields_and_hashes(monkeypatch):
    owner = envelope()["owner_request"]
    policy = {"schema_version": "1.0", "action": "pmv4_e_cutover",
              **{k: owner[k] for k in ("candidate_sha", "rollback_sha",
                 "scope_sha256", "manifest_sha256", "freeze_sha256")},
              "bootstrap_sha256": "a" * 64,
              "scope_guard_sha256": "b" * 64,
              "ci_refresh_sha256": "c" * 64}
    monkeypatch.setattr(worker, "_stage_e_root_file",
                        lambda *a, **kw: json.dumps(policy).encode())
    assert worker._stage_e_dispatch_policy() == policy
    policy["ci_refresh_sha256"] = "f" * 63
    with pytest.raises(worker.HostReconcileError, match="POLICY_INVALID"):
        worker._stage_e_dispatch_policy()
    policy["ci_refresh_sha256"] = "f" * 64
    policy["unreviewed"] = True
    with pytest.raises(worker.HostReconcileError, match="POLICY_INVALID"):
        worker._stage_e_dispatch_policy()


@pytest.mark.parametrize("recovery_ok", [True, False])
def test_failed_bootstrap_attempts_only_original_signed_inert_recovery(
        dispatch, monkeypatch, recovery_ok):
    request, _, calls = dispatch
    owner = request["owner_request"]
    commands = []
    def run(command, **kwargs):
        commands.append((command, kwargs))
        if command[3].endswith("/pmv4_e_ci_refresh.py"):
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "status": "fresh_protected_ci_verified",
                "candidate_sha": owner["candidate_sha"],
            }))
        if "--stage-and-promote" in command:
            return SimpleNamespace(returncode=1, stdout="")
        assert "--recover-inert" in command
        assert json.loads(kwargs["input"]) == owner
        return SimpleNamespace(returncode=0 if recovery_ok else 1,
            stdout=json.dumps({"status": "signed_inert_bootstrap_recovered",
                               "candidate_sha": owner["candidate_sha"],
                               "legacy_six_unchanged": True}))
    monkeypatch.setattr(worker.subprocess, "run", run)
    expected = "INERT_RECOVERED" if recovery_ok else "CHECK_ROOT_JOURNAL"
    with pytest.raises(worker.HostReconcileError, match=expected):
        worker._process_stage_e_request(request)
    assert len(commands) == 3
    assert "--recover-inert" in commands[-1][0]
    assert [c[0] for c in calls] == ["record", "main"]


def test_verified_native_rollback_cannot_be_reported_as_cutover(dispatch, monkeypatch):
    request, _, calls = dispatch
    owner = request["owner_request"]
    status = "native_stage_e_six_unit_rollback_verified"

    def run(command, **kwargs):
        if command[3].endswith("/pmv4_e_ci_refresh.py"):
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "status": "fresh_protected_ci_verified",
                "candidate_sha": owner["candidate_sha"],
            }))
        assert "--stage-and-promote" in command
        native = {
            "status": status, "candidate_sha": owner["candidate_sha"],
            "rollback_sha": owner["rollback_sha"],
            "approval_id": owner["signed_owner_proof"]["payload"]["approval_id"],
            "protected_services_changed": False,
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "status": status, "candidate_sha": owner["candidate_sha"],
            "original_native_receipt": native,
        }))

    monkeypatch.setattr(worker.subprocess, "run", run)
    with pytest.raises(worker.HostReconcileError, match="CUTOVER_ROLLBACK_VERIFIED"):
        worker._process_stage_e_request(request)
    assert [c[0] for c in calls] == ["record", "main"]

@pytest.mark.parametrize("failure", ["timeout", "transport"])
def test_transient_ci_failure_retries_once_with_same_owner_proof(dispatch, monkeypatch, failure):
    request, _, calls = dispatch
    owner = request["owner_request"]
    successful_run = worker.subprocess.run
    attempts = []

    def run(command, **kwargs):
        if command[3].endswith("/pmv4_e_ci_refresh.py"):
            attempts.append((command, kwargs["timeout"]))
            if len(attempts) == 1:
                if failure == "timeout":
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                return SimpleNamespace(returncode=1, stdout="",
                                       stderr="GITHUB_ATTESTATION_UNAVAILABLE")
        return successful_run(command, **kwargs)

    monkeypatch.setattr(worker.subprocess, "run", run)
    result = worker._process_stage_e_request(request)
    assert result["status"] == "native_stage_e_six_unit_accepted"
    assert attempts[0][0] == attempts[1][0]
    assert [timeout for _, timeout in attempts] == [480, 240]
    assert [item[0] for item in calls] == ["record", "main", "ci", "run"]
    assert json.loads(calls[-1][2]["input"]) == owner
