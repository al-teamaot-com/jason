"""Offline safety tests for the one-use three-file/four-unit catalog fix."""
from __future__ import annotations
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "catalog_root_postinstall_repair.py"


@pytest.fixture
def repair(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("test_scoped_catalog_repair", SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(m, "SELF", SimpleNamespace(
        lstat=lambda: SimpleNamespace(st_mode=stat.S_IFREG | 0o500, st_uid=0),
        is_symlink=lambda: False))
    monkeypatch.setattr(m, "root_dir", lambda *args, **kwargs: None)
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0,
                                        stdout="enabled" if args[0][1] == "is-enabled" else "active"))
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "tools").mkdir()
    monkeypatch.setattr(m, "BUNDLE", bundle)
    monkeypatch.setattr(m, "BUNDLE_DIRS", tuple(bundle / p for p in (
        "infrastructure", "infrastructure/openclaw-operations",
        "infrastructure/openclaw-operations/systemd")))
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(m, "LEDGER", state / "postinstall-repair")
    policy = tmp_path / "desired.json"
    original = {"schema_version": "1.0",
                "allowed_system_units": ["jason-grafana-assurance.service"],
                "required_system_units": ["jason-runtime.service"],
                "unrelated": {"protected": True}}
    policy.write_text(json.dumps(original))
    monkeypatch.setattr(m, "POLICY", policy)
    files = []
    source_bytes = {}
    for rel, _, _ in m.FILES:
        src = tmp_path / ("src-" + Path(rel).name)
        data = ("pinned-file:" + rel).encode()
        src.write_bytes(data)
        files.append((rel, str(src), sha256(data).hexdigest()))
        source_bytes[src] = data
    monkeypatch.setattr(m, "FILES", tuple(files))
    freeze = b"frozen-state"
    worker = b"original-worker"
    owner = b"exact-owner-verifier"
    monkeypatch.setattr(m, "FREEZE_SHA", sha256(freeze).hexdigest())
    monkeypatch.setattr(m, "WORKER_SHA", sha256(worker).hexdigest())
    monkeypatch.setattr(m, "OWNER_SHA", sha256(owner).hexdigest())
    root_policy = {
        "source_sha": m.EXPECTED_SOURCE,
        "root_worker_sha256": m.WORKER_SHA,
        "recovery_service_sha256": files[0][2],
        "recovery_timer_sha256": files[1][2],
    }
    drift = {"status": "drift_detected", "problems": [
        {"kind": "undeclared_installed_system_unit", "unit": u}
        for u in m.UNITS]}
    controller = {"circuit_breaker": {"state": "open"}}
    fake = {
        m.FREEZE: (freeze, 0o600),
        m.WORKER: (worker, 0o755),
        m.OWNER: (owner, 0o555),
        m.ROOT_POLICY: (json.dumps(root_policy).encode(), 0o600),
        m.DRIFT: (json.dumps(drift).encode(), 0o600),
        m.CONTROL: (json.dumps(controller).encode(), 0o600),
        **{p: (data, 0o644) for p, data in source_bytes.items()},
    }

    def protected(path, **kwargs):
        if path == policy:
            return path.read_bytes(), 0o600
        return fake[path]
    monkeypatch.setattr(m, "protected_read", protected)
    return m, policy, original, fake


def test_readonly_preflight_preserves_every_other_config_key(repair):
    m, policy, original, _ = repair
    before, after, mode, copied = m.preflight()
    updated = json.loads(after)
    assert json.loads(before) == original
    assert mode == 0o600
    assert set(updated["allowed_system_units"]) - set(original["allowed_system_units"]) == set(m.UNITS)
    assert all(updated[k] == v for k, v in original.items() if k != "allowed_system_units")
    assert len(copied) == 3
    assert not any(path.exists() for path in copied)


def test_success_only_creates_three_pinned_files_and_four_allowances(repair, monkeypatch):
    m, policy, original, _ = repair
    monkeypatch.setattr(m, "fresh_entra_owner", lambda: "bee80bdc-ffb0-4c50-b453-c09d4d411f5f")
    monkeypatch.setattr("builtins.input", lambda _: m.CONFIRM)
    m.execute()
    updated = json.loads(policy.read_text())
    assert set(updated["allowed_system_units"]) - set(original["allowed_system_units"]) == set(m.UNITS)
    assert all(updated[k] == v for k, v in original.items() if k != "allowed_system_units")
    for rel, source, expected in m.FILES:
        copied = m.BUNDLE / rel
        assert copied.is_file() and sha256(copied.read_bytes()).hexdigest() == expected
    journal = list(m.LEDGER.glob("catalog-postinstall-*.json"))
    assert len(journal) == 2  # one audit plus one byte-exact backup
    audits = [json.loads(p.read_text()) for p in journal if "-before" not in p.name]
    assert len(audits) == 1 and audits[0]["status"] == "exact_three_blob_four_unit_repair_verified"
    with pytest.raises(PermissionError, match="REPAIR_DIRECTORIES_ALREADY_EXIST"):
        m.preflight()


def test_unexpected_drift_denied_before_any_writes(repair):
    m, policy, _, fake = repair
    fake[m.DRIFT] = (json.dumps({"status": "drift_detected",
                                "problems": [{"kind": "failed_system_unit",
                                              "unit": "jason-core.service"}]}).encode(), 0o600)
    with pytest.raises(PermissionError, match="OTHER_PRODUCTION_DRIFT_PRESENT"):
        m.preflight()
    assert not m.LEDGER.exists()
    assert not any(folder.exists() for folder in m.BUNDLE_DIRS)


def test_root_policy_mismatch_denied_before_any_writes(repair):
    m, policy, _, fake = repair
    data = json.loads(fake[m.ROOT_POLICY][0])
    data["root_worker_sha256"] = "0" * 64
    fake[m.ROOT_POLICY] = (json.dumps(data).encode(), 0o600)
    with pytest.raises(PermissionError, match="CATALOG_INSTALLED_POLICY_MISMATCH"):
        m.preflight()
    assert not m.LEDGER.exists()


def test_owner_requires_fresh_exact_phrase(repair, monkeypatch):
    m, _, _, _ = repair
    monkeypatch.setattr(m, "fresh_entra_owner", lambda: "bee80bdc-ffb0-4c50-b453-c09d4d411f5f")
    monkeypatch.setattr("builtins.input", lambda _: "APPROVED")
    with pytest.raises(PermissionError, match="EXACT_OWNER_CONSENT_MISSING"):
        m.execute()
    assert not m.LEDGER.exists()
    assert not any(p.exists() for p in m.BUNDLE_DIRS)
