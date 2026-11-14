"""Narrow initial-root-trust bootstrap acceptance. Disposable paths only.

CI runs these tests as root INSIDE A TEMPORARY GITHUB RUNNER, never Jason.
"""
import json
from pathlib import Path
import stat

import pytest

from tools import pmv4_a0_initial_root_trust_consumer as m


@pytest.fixture
def lab(tmp_path, monkeypatch):
    parent = tmp_path / "host"
    parent.mkdir(mode=0o700)
    root = parent / "etc"
    root.mkdir(mode=0o700)
    source = parent / "usr"
    source.mkdir(mode=0o700)
    files = {str(source / ("f" + str(i) + ".py")): b"file" + bytes([i])
             for i in range(4)}
    files.update({str(root / ("p" + str(i) + ".json")): b'{"policy":false}'
                  for i in range(2)})
    directories = {str(root / "ledger1"), str(root / "ledger2")}
    modes = {f: 0o444 if f.endswith(".py") else 0o400 for f in files}
    monkeypatch.setattr(m, "REQUIRED_MODES", modes)
    monkeypatch.setattr(m, "REQUIRED_DIRS", directories)
    journal = parent / "journal"
    monkeypatch.setattr(m, "JOURNAL", journal)
    plan = {
        "new_root_files": [{"destination": f, "mode": format(mode, "04o")}
                           for f, mode in modes.items()],
        "new_root_directories": [{"path": path, "mode": "0700"}
                                 for path in sorted(directories)],
    }
    return plan, files, directories, journal


def test_installs_exact_files_and_empty_directories(lab, monkeypatch):
    plan, files, directories, journal = lab
    monkeypatch.setattr(m, "preflight_production", lambda: None)
    audit = {"status": "start"}
    m.audit_write(audit, first=True)
    m.publish_targets(plan, files, audit)
    assert json.loads(journal.read_text())["status"] == "verified_installed"
    for path, raw in files.items():
        object_path = Path(path)
        assert object_path.read_bytes() == raw
        assert stat.S_IMODE(object_path.stat().st_mode) == m.REQUIRED_MODES[path]
    for path in directories:
        assert Path(path).is_dir() and not list(Path(path).iterdir())


def test_failed_postcheck_rolls_back_created_objects(lab, monkeypatch):
    plan, files, directories, journal = lab

    def fail():
        raise RuntimeError("synthetic postreadback failure")

    monkeypatch.setattr(m, "preflight_production", fail)
    audit = {"status": "start"}
    m.audit_write(audit, first=True)
    with pytest.raises(m.Denied, match="ROLLBACK_VERIFIED"):
        m.publish_targets(plan, files, audit)
    assert json.loads(journal.read_text())["status"] == "verified_empty_rollback"
    assert not any(Path(path).exists() for path in files)
    assert not any(Path(path).exists() for path in directories)


def test_foreign_object_not_deleted_during_failed_install(lab, monkeypatch):
    plan, files, directories, journal = lab
    foreign = Path(sorted(directories)[0]) / "foreign"

    def fail():
        foreign.write_text("foreign protected content")
        raise RuntimeError("synthetic foreign object")

    monkeypatch.setattr(m, "preflight_production", fail)
    audit = {"status": "start"}
    m.audit_write(audit, first=True)
    with pytest.raises(m.Denied, match="REQUIRES_REVIEW"):
        m.publish_targets(plan, files, audit)
    assert foreign.read_text() == "foreign protected content"
    assert json.loads(journal.read_text())["status"] == "rollback_requires_review"


def test_untrusted_execution_path_rejected():
    with pytest.raises(m.Denied, match="ROOT_STAGING_PATH_NOT_PINNED|LOCAL_ROOT_SESSION_REQUIRED"):
        m.check_trusted_execution()


def test_no_unapproved_signed_owner_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "PROOF", tmp_path / "absent")
    with pytest.raises(FileNotFoundError):
        m.verify_signed_approval({"plan_sha256": m.SCOPE_SHA})


def test_consumed_action_cannot_replay(lab):
    _, _, _, journal = lab
    journal.write_text("prior one-use approval consumed")
    with pytest.raises(m.Denied, match="ACTION_ALREADY_CLAIMED"):
        m.check_absent()


def test_exact_scope_is_only_six_files_two_dirs():
    assert len(m.REQUIRED_MODES) == 6
    assert len(m.REQUIRED_DIRS) == 2
    assert m.STAGING.as_posix().startswith("/run/")
    assert m.SHA != m.LKG
    assert m.APPROVED_ACTION == "pmv4-stage-a0-initial-root-trust-v1"


def test_launcher_has_only_local_root_stage_and_exact_owner_auth():
    launcher = Path(__file__).parents[1] / "pmv4_a0_initial_root_trust_launcher.sh"
    data = launcher.read_text()
    assert "python3 -B \"$OWNER\" --authorize" in data
    assert "sudo /usr/bin/python3 -I \"$STAGED\" --execute" in data
    assert "sudo /usr/bin/sha256sum -c -" in data
    assert "sudo /usr/bin/install -d -o root -g root -m 0700" in data
    assert "sudo /usr/bin/install -o root -g root -m 0400" in data
    assert "rm -rf" not in data and "systemctl restart" not in data
