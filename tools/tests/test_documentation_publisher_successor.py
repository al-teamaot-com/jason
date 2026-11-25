"""New Owner decision, not replay of the November 20 approval."""
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import documentation_publisher_successor as s


def test_historical_record_cannot_supply_current_authority(monkeypatch):
    old = {"action": "prior", "scope": "unchanged"}
    monkeypatch.setattr(s, "OLD_SCOPE", s.digest(s.canon(old)))
    approval = {"scope": old, "owner_oid": "old-owner", "approved_at": "2026-11-20T20:46:47Z"}
    failed = {"status": "documentation_repair_requires_readback_recovery",
              "original_service_override_restored": True}
    assert s.historical(approval, failed) == old
    for bad in (dict(approval, scope={"action": "changed"}), {"scope": old}):
        with pytest.raises(PermissionError, match="OLD_SCOPE_CHANGED"):
            s.historical(bad, failed)
    with pytest.raises(PermissionError, match="OLD_FAILURE_CHANGED"):
        s.historical(approval, dict(failed, original_service_override_restored=False))


def test_root_gate_precedes_helper_loading(monkeypatch):
    monkeypatch.setattr(s, "load_helpers", lambda: pytest.fail("loaded before root gate"))
    monkeypatch.setattr(s.os, "geteuid", lambda: 1000)
    with pytest.raises(PermissionError, match="ROOT_ISOLATION_REQUIRED"):
        s.main(["--source-sha", "a" * 40, "--apply"])


def fixture(tmp_path, monkeypatch, fail=None):
    candidate = "a" * 40
    scope = {"action": s.ACTION, "policy": {"candidate_sha": candidate},
             "protected_health": {"peers": "same"}, "dropin_sha256": s.digest(b"exact")}
    calls = []
    base = tmp_path / "base"
    base.mkdir()
    old = base / "approval.json"
    old.write_bytes(b"old-immutable")
    path = tmp_path / "override"
    p = {"stamp": lambda: "now", "GUARD_AFTER_SHA": "pinned",
         "protected_health": lambda **_: {"peers": "same"}}
    d = {"BASE": base, "UNIT": Path("doc.service"), "DROPIN": path,
         "dropin_bytes": lambda _: b"exact"}
    def apply(raw):
        assert not path.exists()
        path.write_bytes(raw)
        calls.append("apply")
    def restore(raw):
        assert path.read_bytes() == raw
        path.unlink()
        calls.append("restore")
    r = {"ORIGINAL_SOURCE": "old", "Override": lambda _: SimpleNamespace(apply=apply, restore=restore)}
    def write(path, data):
        with path.open("xb") as f:
            f.write(data)
    c = {"sync_dir": lambda _: None, "write": write,
         "read": lambda path, *_: path.read_bytes(),
         "systemctl": lambda args: calls.append(tuple(args))}
    def owner(approved):
        assert approved == scope
        calls.append("owner")
        return "new-owner"
    ns = {"locks": nullcontext, "owner": owner}
    monkeypatch.setattr(s, "inspect", lambda *a: dict(scope, changed=True) if fail == "scope" else scope)
    def verify(*args):
        if fail == "publication":
            raise PermissionError("publication failed")
        return "b" * 40
    monkeypatch.setattr(s, "verify_publication", verify)
    return candidate, scope, p, r, d, c, ns, calls, old, path


@pytest.mark.parametrize("fail", [None, "scope", "publication"])
def test_fresh_owner_decision_and_exact_override_rollback(tmp_path, monkeypatch, fail):
    candidate, scope, p, r, d, c, ns, calls, old, path = fixture(tmp_path, monkeypatch, fail)
    record = d["BASE"] / ("successor-" + candidate)
    if fail is None:
        s.execute(candidate, scope, p, r, d, c, ns)
        assert path.read_bytes() == b"exact"
        assert json.loads((record / "result.json").read_bytes())["status"] == "documentation_publisher_operationally_verified"
    else:
        with pytest.raises(PermissionError):
            s.execute(candidate, scope, p, r, d, c, ns)
        assert not path.exists()
        if fail == "scope":
            assert not record.exists() and calls == ["owner"]
        else:
            assert json.loads((record / "result.json").read_bytes())["status"] == "rolled_back"
            assert ("stop", "doc.service") in calls and "restore" in calls
    if record.exists():
        a = json.loads((record / "approval.json").read_bytes())
        assert a["owner_oid"] == "new-owner" and a["scope"] == scope
        assert a["scope_sha256"] == s.digest(s.canon(scope))
    assert old.read_bytes() == b"old-immutable"


def test_publication_requires_fresh_success_and_exact_remote_tip(tmp_path, monkeypatch):
    candidate = "a" * 40
    doc = tmp_path / "docs/control"
    doc.mkdir(parents=True)
    (doc / "AUTOMATED-CHANGE-STATE.json").write_text(json.dumps(
        {"validated_source": {"revision": candidate}}))
    d = {"DROPIN": tmp_path / "override", "WORKTREE": tmp_path, "DOC_REPO": tmp_path}
    state = {"ExecMainStartTimestampMonotonic": "2", "ActiveState": "inactive",
             "Result": "success", "ExecMainStatus": "0", "DropInPaths": str(d["DROPIN"])}
    monkeypatch.setattr(s, "service_readback", lambda *_: state)
    c = {"git": lambda _, arg, *a: "b" * 40 if arg == "rev-parse" else ""}
    p = {"exact_sha": lambda a: len(a) == 40,
         "git": lambda _, arg, *a: (("b" * 40 + " refs/heads/" + s.BRANCH).encode()
                                   if arg == "ls-remote" else b"")}
    assert s.verify_publication(candidate, {"previous_service_start": "1"}, p, d, c) == "b" * 40
    p["git"] = lambda *_: b"foreign refs/heads/automation/documentation-reconcile-current"
    with pytest.raises(PermissionError, match="GENERATED_REMOTE_NOT_CURRENT"):
        s.verify_publication(candidate, {"previous_service_start": "1"}, p, d, c)
