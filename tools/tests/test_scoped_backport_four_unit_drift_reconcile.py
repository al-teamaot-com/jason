"""Exact four-name desired-state repair; no implicit service or release authority."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import scoped_backport_four_unit_drift_reconcile as fix

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / "config/production-desired-state.json").read_text())


def candidate(original=None):
    before = json.dumps(original or BASE, sort_keys=True, indent=2).encode()
    return fix.candidate_policy(before)


def test_exact_four_allowlist_not_required_or_exemption():
    policy, raw = candidate()
    expected = sorted(BASE["allowed_system_units"] + list(fix.UNIT_NAMES))
    assert policy["allowed_system_units"] == expected
    assert policy["required_system_units"] == BASE["required_system_units"]
    for k in BASE:
        if k != "allowed_system_units":
            assert policy[k] == BASE[k]
    assert len(fix.UNIT_NAMES) == 4
    assert set(fix.ROOT_UNIT_DIGESTS) == set(fix.UNIT_NAMES)
    assert json.loads(raw) == policy


@pytest.mark.parametrize("unit", fix.UNIT_NAMES)
def test_replay_or_one_preexisting_name_denied(unit):
    modified = deepcopy(BASE)
    modified["allowed_system_units"].append(unit)
    with pytest.raises(fix.DriftCorrectionDenied,
                       match="POLICY_EXACT_FOUR_UNIT_GAP_NOT_PRESENT"):
        candidate(modified)


def test_candidate_policy_idempotent_second_run_denied():
    proposed, b = candidate()
    with pytest.raises(fix.DriftCorrectionDenied,
                       match="POLICY_EXACT_FOUR_UNIT_GAP_NOT_PRESENT"):
        fix.candidate_policy(b)


def test_unrelated_key_is_not_normalized():
    modified = deepcopy(BASE)
    modified["custom_extension"] = {"z": ["delta", "other"]}
    policy, _ = candidate(modified)
    assert policy["custom_extension"] == modified["custom_extension"]


def test_drift_requires_exact_four_missing():
    allowed = [{"kind": "undeclared_installed_system_unit", "unit": u,
                "state": "inactive"} for u in fix.UNIT_NAMES]
    fix.check_only_expected_drift({"status": "drift_detected", "problems": allowed})


def test_drift_allows_known_watchdog_failure_only():
    allowed = [{"kind": "undeclared_installed_system_unit", "unit": u,
                "state": "inactive"} for u in fix.UNIT_NAMES]
    allowed.append({"kind": "failed_system_unit",
                    "unit": "jason-production-drift-watchdog.service",
                    "state": "failed"})
    fix.check_only_expected_drift({"status": "drift_detected", "problems": allowed})


@pytest.mark.parametrize("problem", [
    {"kind": "undeclared_installed_system_unit", "unit": "jason-unrelated.service"},
    {"kind": "failed_system_unit", "unit": "jason-runtime.service"},
    {"kind": "required_system_unit_not_active", "unit": "jason-core.service"},
])
def test_unrelated_production_drift_is_never_masked(problem):
    current = [{"kind": "undeclared_installed_system_unit", "unit": u}
               for u in fix.UNIT_NAMES]
    current.append(problem)
    with pytest.raises(fix.DriftCorrectionDenied,
                       match="UNRELATED_PRODUCTION_DRIFT_PRESENT"):
        fix.check_only_expected_drift({"status": "drift_detected", "problems": current})


def test_clean_drift_is_not_excuse_for_write():
    with pytest.raises(fix.DriftCorrectionDenied):
        fix.check_only_expected_drift({"status": "pass", "problems": []})


def test_root_inspection_requires_authenticated_sudo_before_git(monkeypatch):
    monkeypatch.setattr(fix.os, "geteuid", lambda: 1000)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(fix, "verify_source",
                        lambda *a, **kw: pytest.fail("must not inspect Git"))
    with pytest.raises(fix.DriftCorrectionDenied, match="LOCAL_AUTHENTICATED_ROOT_REQUIRED"):
        fix.inspect(source_sha="a"*40, reviewed_sha="b"*40)


def test_root_source_verifier_requires_matching_main(monkeypatch):
    main = "a" * 40
    reviewed = "b" * 40
    def fake(*args):
        if args == ("rev-parse", "HEAD"):
            return (main + "\n").encode()
        if args == ("status", "--porcelain"):
            return b""
        if args == ("ls-remote", "origin", "refs/heads/main"):
            return (("c"*40) + "\trefs/heads/main").encode()
        pytest.fail("must not read source if main drifted")
    monkeypatch.setattr(fix, "git", fake)
    with pytest.raises(fix.DriftCorrectionDenied, match="PROTECTED_MAIN_MOVED"):
        fix.verify_source(main, reviewed)


def test_ci_gate_requires_all_five_green(monkeypatch):
    req = ["repository-hygiene", "documentation", "runtime-service",
           "governed-security-regressions", "GitGuardian Security Checks"]
    class Response:
        def __init__(self, data): self.data = data
        def __enter__(self): return BytesIO(json.dumps(self.data).encode())
        def __exit__(self, *args): return None
    checks = [{"name": n, "id": i, "status": "completed", "conclusion": "success"}
              for i,n in enumerate(req)]
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *args, **kw: Response({"check_runs": checks}))
    fix.require_ci_green("a"*40)
    checks[-1]["conclusion"] = "failure"
    with pytest.raises(fix.DriftCorrectionDenied, match="REQUIRED_CI_NOT_GREEN"):
        fix.require_ci_green("a"*40)


def test_exact_filename_and_unit_targets_are_distinct_from_existing_services():
    assert set(fix.UNIT_NAMES).isdisjoint({
        "jason-runtime.service", "jason-core.service",
        "jason-catalog-scoped-recovery.service",
        "jason-production-drift-watchdog.service",
        "jason-production-drift-watchdog.timer",
    })
    assert fix.ROOT_POLICY.as_posix().startswith("/etc/jason/release-readback-recovery/")
    assert fix.ROOT_AUDIT.as_posix().startswith("/etc/jason-owner-release/")
    assert fix.CONFIRM == "APPROVE-FOUR-UNIT-SCOPED-BACKPORT-DRIFT-RECONCILE"


def test_public_only_default_config_is_never_root_repair_target():
    assert fix.ROOT_POLICY != Path("/opt/jason/current/config/production-desired-state.json")
    assert fix.GUARD == Path("/opt/jason/current/tools/production_drift_guard.py")


def test_root_policy_change_hash_exactly_differs_from_original():
    raw = json.dumps(BASE, indent=2, sort_keys=True).encode()
    _, candidate_raw = fix.candidate_policy(raw)
    assert sha256(raw).hexdigest() != sha256(candidate_raw).hexdigest()
    assert not any("Graph" in name or "Ticket" in name for name in fix.UNIT_NAMES)


def test_root_upgrade_changes_exactly_two_installed_files_and_trust_receipts(
        monkeypatch, tmp_path):
    old_files = {rel: ("old:" + rel).encode() for rel in fix.ROOT_PATCH}
    new_files = {rel: ("new:" + rel).encode() for rel in fix.ROOT_PATCH}
    base = {
        "schema_version": "1.0", "profile": "governed-scoped-backport-v1",
        "trusted_source_sha": fix.INSTALLED_SHA,
        "reviewed_ci_sha": "a" * 40,
        "automatic_rollback_recovery_installed": True,
        "exact_signed_owner_approval_required": True,
        "native_root_control_supported": True,
    }
    for rel, field in fix.ROOT_PATCH.items():
        base[field] = sha256(old_files[rel]).hexdigest()
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new_files[rel])
    monkeypatch.setattr(fix, "SOURCE_REPO", tmp_path)
    def file_reader(path, **kwargs):
        if path == fix.ROOT_INSTALL:
            return (json.dumps(base) + "\n").encode()
        if path == fix.ROOT_PUBLIC_ATTEST:
            return json.dumps(fix.public_attestation(base)).encode()
        for rel in fix.ROOT_PATCH:
            if path == fix.ROOT_INSTALL_DIR / rel:
                return old_files[rel]
        pytest.fail("unexpected source path: " + str(path))
    monkeypatch.setattr(fix, "read_root", file_reader)
    monkeypatch.setattr(
        fix, "git", lambda *args:
        next(new_files[rel] for rel in fix.ROOT_PATCH if args[1].endswith(":" + rel)))
    next_main = "b" * 40
    result = fix.root_control_upgrade(base, source_sha=next_main,
                                      reviewed_sha="c" * 40)
    assert set(result["before_files"]) == {
        fix.ROOT_INSTALL_DIR / rel for rel in fix.ROOT_PATCH
    }
    assert result["new_private"]["trusted_source_sha"] == next_main
    assert result["new_private"]["reviewed_ci_sha"] == "c" * 40
    for rel, field in fix.ROOT_PATCH.items():
        assert result["new_private"][field] == sha256(new_files[rel]).hexdigest()
    assert result["new_public"]["trusted_source_sha"] == next_main
    assert result["new_public"]["root_handler_sha256"] == result["new_private"]["root_handler_sha256"]
    assert "core_sha256" not in result["new_public"]


def test_exact_root_replacement_plan_has_only_five_reviewed_paths():
    change = {
        "upgrade": {
            "before_files": {fix.ROOT_INSTALL_DIR / p: b"old"
                             for p in fix.ROOT_PATCH},
            "after_files": {fix.ROOT_INSTALL_DIR / p: b"new"
                            for p in fix.ROOT_PATCH},
            "old_private_raw": b"private-old",
            "new_private_raw": b"private-new",
            "old_public_raw": b"public-old",
            "new_public_raw": b"public-new",
        },
        "baseline": b"desired-old", "candidate": b"desired-new",
    }
    changes = fix.approved_root_file_changes(change)
    assert len(changes) == 5
    assert [x[0] for x in changes[-3:]] == [
        fix.ROOT_INSTALL, fix.ROOT_PUBLIC_ATTEST, fix.ROOT_POLICY
    ]
    assert {mode for _,_,_,mode in changes} == {0o444, 0o600, 0o644}
    assert all(not path.as_posix().startswith("/opt/jason/current/")
               for path,*_ in changes)


def test_partial_root_patch_rolls_back_every_exact_file(monkeypatch):
    paths = [Path("/root/one"), Path("/root/two")]
    old = [b"old-a", b"old-b"]
    new = [b"new-a", b"new-b"]
    disk = {paths[0]: new[0], paths[1]: new[1]}
    order = []
    monkeypatch.setattr(
        fix, "read_root",
        lambda path, **kwargs: disk[path])
    def update(path, before, after, mode):
        assert disk[path] == before
        disk[path] = after
        order.append(path)
    monkeypatch.setattr(fix, "atomic_exact_root_file", update)
    fix.restore_attempted_root_files(
        [(paths[i], old[i], new[i], 0o444) for i in range(2)])
    assert disk == {paths[0]: old[0], paths[1]: old[1]}
    assert order == list(reversed(paths))


def test_foreign_root_change_prevents_unsafe_rollback(monkeypatch):
    path = Path("/root/one")
    monkeypatch.setattr(fix, "read_root", lambda *args, **kwargs: b"foreign")
    monkeypatch.setattr(
        fix, "atomic_exact_root_file",
        lambda *args: pytest.fail("must never overwrite foreign bytes"))
    with pytest.raises(fix.DriftCorrectionDenied,
                       match="FOREIGN_ROOT_CHANGE_PREVENTS_ROLLBACK"):
        fix.restore_attempted_root_files(
            [(path, b"old", b"new", 0o600)])


def test_scoped_listeners_only_paused_not_existing_production_services():
    assert fix.SCOPED_PATH == "jason-scoped-backport-requests.path"
    assert fix.SCOPED_TIMER == "jason-scoped-backport-recovery.timer"
    assert fix.SCOPED_PATH not in fix.PROTECTED
    assert fix.SCOPED_TIMER not in fix.PROTECTED
    assert "jason-production-drift-watchdog.timer" not in (fix.SCOPED_PATH, fix.SCOPED_TIMER)
