"""Finite continuation of unchanged approved payload; synthetic evidence only."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

import pytest
from tools import documentation_publisher_readback_recovery as r
from tools import documentation_publisher_install as original


def evidence():
    now = datetime.now(timezone.utc)
    scope = {
        "action": original.ACTION,
        "policy": {"candidate_sha": r.ORIGINAL_SOURCE,
                   "rollback_sha": "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"},
        "executor_sha256": r.ORIGINAL_EXECUTOR,
        "queue_cutover": False, "runtime_or_mcp_restart_allowed": False,
        "provider_mutations_allowed": False, "standing_authority": False,
    }
    approval = {"scope": scope, "owner_oid": "fixture-owner",
                "approved_at": (now - timedelta(minutes=3)).isoformat()}
    failed = {"status": "documentation_repair_requires_readback_recovery",
              "original_service_override_restored": True}
    return now, approval, failed


def verify(now, approval, failed, digest=None):
    return r.validate_approval(approval, failed,
        scope_sha256=digest or r.digest(r.canon(approval["scope"])),
        owners={"fixture-owner"}, now=now)


def test_original_sealed_decision_allows_only_unchanged_failed_phase():
    now, approval, failed = evidence()
    assert verify(now, approval, failed) is approval["scope"]


@pytest.mark.parametrize("fault", ["scope", "owner", "expired", "future", "not_rolled_back",
                                  "different_source", "different_executor", "runtime_restart",
                                  "provider_write", "standing_authority"])
def test_changed_authority_payload_or_phase_denies(fault):
    now, approval, failed = evidence()
    expected = r.digest(r.canon(approval["scope"]))
    if fault == "scope": approval["scope"]["extra_target"] = "foreign"
    if fault == "owner": approval["owner_oid"] = "foreign"
    if fault == "expired": approval["approved_at"] = (now - timedelta(hours=3)).isoformat()
    if fault == "future": approval["approved_at"] = (now + timedelta(minutes=1)).isoformat()
    if fault == "not_rolled_back": failed["original_service_override_restored"] = False
    if fault == "different_source": approval["scope"]["policy"]["candidate_sha"] = "a" * 40
    if fault == "different_executor": approval["scope"]["executor_sha256"] = "b" * 64
    if fault == "runtime_restart": approval["scope"]["runtime_or_mcp_restart_allowed"] = True
    if fault == "provider_write": approval["scope"]["provider_mutations_allowed"] = True
    if fault == "standing_authority": approval["scope"]["standing_authority"] = True
    # Semantic boundary checks must deny even if a caller supplies the changed digest.
    if fault != "scope":
        expected = r.digest(r.canon(approval["scope"]))
    with pytest.raises(r.DocumentationRecoveryDenied):
        verify(now, approval, failed, expected)


def test_foreign_worktree_is_denied_before_clean_status_or_mutation(tmp_path):
    def git(repo, *args):
        if args[-1] == "--git-common-dir":
            return "/publisher/.git" if repo == tmp_path / "repo" else "/different/.git"
        pytest.fail("continued after foreign worktree linkage")
    with pytest.raises(r.DocumentationRecoveryDenied, match="DIFFERENT_REPOSITORY"):
        r.require_worktree_owner({"git": git}, tmp_path / "repo", tmp_path / "work")


def test_non_root_or_unisolated_cli_denies_before_loading_private_evidence(monkeypatch):
    monkeypatch.setattr(r, "original", lambda: pytest.fail("authority loaded before root gate"))
    with pytest.raises(r.DocumentationRecoveryDenied, match="AUTHENTICATED_AL_ROOT_REQUIRED"):
        r.main(["--source-sha", "a" * 40, "--approval-scope-sha256", "b" * 64, "--apply"])


def test_original_installer_and_payload_remain_byte_identical():
    assert r.digest(Path(original.__file__).read_bytes()) == r.ORIGINAL_EXECUTOR



@pytest.fixture
def override(tmp_path):
    if os.geteuid() != 0:
        pytest.skip("disposable UID0 filesystem fixture")
    c, _ = original.primitives()
    return r.Override(c, path=tmp_path / "service.d" / "reviewed.conf", production=False)


def test_exact_override_resume_and_rollback(override):
    raw = original.dropin_bytes(r.ORIGINAL_SOURCE)
    override.apply(raw)
    assert override.path.read_bytes() == raw and override.path.stat().st_uid == 0
    override.restore(raw)
    assert not override.path.exists() and not override.path.parent.exists()


def test_foreign_override_is_preserved_on_rollback(override):
    raw = original.dropin_bytes(r.ORIGINAL_SOURCE)
    override.apply(raw)
    override.path.write_bytes(b"foreign")
    with pytest.raises(r.DocumentationRecoveryDenied, match="FOREIGN_OVERRIDE"):
        override.restore(raw)
    assert override.path.read_bytes() == b"foreign"


def recovery_cli(monkeypatch, tmp_path, inspections):
    from contextlib import nullcontext
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(r, "os", SimpleNamespace(
        geteuid=lambda: 0, environ={"SUDO_USER": "al", "SUDO_UID": "1000"}))
    monkeypatch.setattr(r, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    d = {"BASE": tmp_path, "UNIT": Path("publisher.service"),
         "dropin_bytes": lambda sha: b"original-exact-override"}
    def write(path, raw):
        with path.open("xb") as stream:
            stream.write(raw)
        calls.append(("write", path.name))
    c = {"write": write,
         "systemctl": lambda args: calls.append(("systemctl", args)),
         "props": lambda *a: {"ActiveState": "inactive"},
         "run": lambda *a: "Result=exit-code\nExecMainStatus=1\n"}
    ns = {"locks": nullcontext}
    monkeypatch.setattr(r, "original", lambda: (d, c, ns))
    monkeypatch.setattr(r, "inspect", lambda *a, **kw: next(inspections))
    monkeypatch.setattr(r, "Override", lambda *a: SimpleNamespace(
        apply=lambda raw: calls.append(("apply", raw)),
        restore=lambda raw: calls.append(("restore", raw))))
    return calls


def test_read_only_recovery_never_reaches_configuration_or_service_mutation(monkeypatch, tmp_path):
    calls = recovery_cli(monkeypatch, tmp_path, iter([({}, {})]))
    r.main(["--source-sha", "a" * 40, "--approval-scope-sha256", "b" * 64])
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_second_inspection_change_never_writes_nonce_or_stops_service(monkeypatch, tmp_path):
    calls = recovery_cli(monkeypatch, tmp_path, iter([({}, {}), ({"changed": True}, {})]))
    with pytest.raises(r.DocumentationRecoveryDenied, match="CHANGED_DURING_RECOVERY"):
        r.main(["--source-sha", "a" * 40, "--approval-scope-sha256", "b" * 64, "--apply"])
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_failed_job_restores_override_and_preserves_original_approval_and_attempt(monkeypatch, tmp_path):
    for name in ("approval.json", "verification-failed.json"):
        (tmp_path / name).write_bytes(b"original-root-sealed-evidence")
    approval = {"owner_oid": "fixture-owner"}
    calls = recovery_cli(monkeypatch, tmp_path, iter([({}, approval), ({}, approval)]))
    with pytest.raises(r.DocumentationRecoveryDenied, match="PUBLISHER_JOB_FAILED"):
        r.main(["--source-sha", "a" * 40, "--approval-scope-sha256", "b" * 64, "--apply"])
    assert calls == [
        ("write", "recovery-started.json"),
        ("apply", b"original-exact-override"),
        ("systemctl", ["daemon-reload"]),
        ("systemctl", ["reset-failed", "publisher.service"]),
        ("systemctl", ["start", "--no-block", "publisher.service"]),
        ("systemctl", ["stop", "publisher.service"]),
        ("restore", b"original-exact-override"),
        ("systemctl", ["daemon-reload"]),
    ]
    assert (tmp_path / "recovery-started.json").exists()
    assert not (tmp_path / "accepted.json").exists()
    for name in ("approval.json", "verification-failed.json"):
        assert (tmp_path / name).read_bytes() == b"original-root-sealed-evidence"
