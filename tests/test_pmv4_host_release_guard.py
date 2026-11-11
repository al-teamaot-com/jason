"""Read-only PMv4 host gate and cross-PMv3/PMv4 release lock acceptance."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from tools.pmv4_host_release_guard import (
    IndependentHostGuard, HostGateDenied, CURRENT, LEDGER,
)
from tools.pmv4_shadow_host_runtime import pending_rollback_acceptance
from tools.pmv4_shadow_release import EMPTY_BASELINE


SHA = "a" * 40


def _fixture(tmp_path):
    releases = tmp_path / "releases"
    (releases / SHA).mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(releases / SHA)
    ledger = tmp_path / "ticket.sqlite3"
    now = datetime.now(timezone.utc)
    with sqlite3.connect(ledger) as c:
        c.execute(
            "CREATE TABLE autonomy_ticket_worker_heartbeat "
            "(singleton_id INTEGER PRIMARY KEY, last_started_at TEXT, "
            "last_completed_at TEXT, state TEXT)"
        )
        c.execute(
            "INSERT INTO autonomy_ticket_worker_heartbeat VALUES(1,?,?,?)",
            (now.isoformat(), now.isoformat(), "completed"),
        )
    old = tmp_path / "old.lock"
    new = tmp_path / "new.lock"
    old.touch(mode=0o600)
    new.touch(mode=0o600)
    for p in (old, new):
        p.chmod(0o600)
    fake = {
        name: {
            "Name": "/" + name,
            "Config": {"Labels": {"com.teamaot.jason.source_revision": SHA}},
            "State": {"Running": True, "Health": (
                {"Status": "healthy"} if name == "jason-runtime" else None)},
        }
        for name in ("jason-runtime", "jason-mcp-pilot")
    }
    seen = []
    def runner(args, **_kwargs):
        seen.append(tuple(args))
        name = args[-1]
        return SimpleNamespace(returncode=0, stdout=json.dumps([fake[name]]))
    guard = IndependentHostGuard(
        current=current, releases=releases, ledger=ledger,
        old_lock=old, new_lock=new, runner=runner,
        now=lambda: now, production=False,
    )
    return guard, fake, seen, now


def test_fresh_independently_verified_core_without_pmv3_report(tmp_path):
    guard, _, seen, _ = _fixture(tmp_path)
    result = guard.core_health_evidence()
    assert result["status"] == "verified"
    assert result["worker_scan_fresh"]
    assert result["source_sha"] == SHA
    assert seen == [
        ("/usr/bin/docker", "inspect", "jason-runtime"),
        ("/usr/bin/docker", "inspect", "jason-mcp-pilot"),
    ]


def test_stale_heartbeat_refuses_release_even_if_containers_running(tmp_path):
    guard, _, _, now = _fixture(tmp_path)
    with sqlite3.connect(guard.ledger) as c:
        c.execute("UPDATE autonomy_ticket_worker_heartbeat SET last_completed_at=?",
                  ((now - timedelta(minutes=12)).isoformat(),))
    assert not guard.preexisting_core_health()
    with pytest.raises(HostGateDenied, match="TICKET_SCAN_STALE"):
        guard.core_health_evidence()


@pytest.mark.parametrize("field", ("runtime_stopped", "runtime_unhealthy",
                                   "runtime_drift", "mcp_stopped", "name_wrong"))
def test_container_status_or_source_drift_denied(tmp_path, field):
    guard, fake, _, _ = _fixture(tmp_path)
    if field == "runtime_stopped":
        fake["jason-runtime"]["State"]["Running"] = False
    elif field == "runtime_unhealthy":
        fake["jason-runtime"]["State"]["Health"]["Status"] = "unhealthy"
    elif field == "runtime_drift":
        fake["jason-runtime"]["Config"]["Labels"]["com.teamaot.jason.source_revision"] = "b" * 40
    elif field == "mcp_stopped":
        fake["jason-mcp-pilot"]["State"]["Running"] = False
    else:
        fake["jason-mcp-pilot"]["Name"] = "/jason-runtime"
    assert guard.preexisting_core_health() is False


def test_hold_both_release_locks_for_whole_transaction(tmp_path):
    guard, _, _, _ = _fixture(tmp_path)
    assert guard.host_mutation_quiescent()
    with guard.host_release_transaction():
        assert guard.host_mutation_quiescent()
        with pytest.raises(HostGateDenied, match="NESTED_HOST_TRANSACTION"):
            with guard.host_release_transaction():
                pass
        for lock in (guard.old_lock, guard.new_lock):
            fd = os.open(lock, os.O_RDONLY)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
    assert guard.host_mutation_quiescent()


def test_existing_publisher_lock_denies_pmv4_promotion(tmp_path):
    guard, _, _, _ = _fixture(tmp_path)
    fd = os.open(guard.old_lock, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not guard.host_mutation_quiescent()
        with pytest.raises(HostGateDenied, match="HOST_TRANSACTION_BUSY"):
            with guard.host_release_transaction():
                pass
    finally:
        os.close(fd)
    assert guard.host_mutation_quiescent()


def test_unprovisioned_new_control_denies_without_creating_it(tmp_path):
    guard, _, _, _ = _fixture(tmp_path)
    guard.new_lock.unlink()
    assert not guard.host_mutation_quiescent()
    assert not guard.new_lock.exists()


def test_untrusted_lock_mode_denied(tmp_path):
    guard, _, _, _ = _fixture(tmp_path)
    guard.new_lock.chmod(0o666)
    with pytest.raises(HostGateDenied, match="LOCK_UNTRUSTED"):
        with guard.host_release_transaction():
            pass


def test_no_override_of_production_trust_paths(tmp_path):
    with pytest.raises(HostGateDenied, match="TRUSTED_HOST_PATH_OVERRIDE"):
        IndependentHostGuard(ledger=tmp_path / "not-production.sqlite3",
                             production=True)


def test_readback_does_not_execute_provider_or_external_ai(tmp_path):
    guard, _, seen, _ = _fixture(tmp_path)
    assert guard.preexisting_core_health()
    assert all(arg[0:2] == ("/usr/bin/docker", "inspect") for arg in seen)


def test_baseline_recovery_checks_both_absence_and_ticket_core(tmp_path):
    guard, _, _, _ = _fixture(tmp_path)
    prior = tmp_path / EMPTY_BASELINE
    prior.mkdir()
    (prior / "baseline.json").write_text(json.dumps({
        "schema_version": "1.0", "service": "jason-pmv4-shadow",
        "baseline": "no_prior_shadow_runtime",
    }))
    adapter = SimpleNamespace(_owned_or_absent=lambda: None)
    assert pending_rollback_acceptance(adapter, guard, prior)
    adapter = SimpleNamespace(_owned_or_absent=lambda: {"Name": "stale-shadow"})
    assert not pending_rollback_acceptance(adapter, guard, prior)


def test_open_root_breaker_blocks_release_even_with_fresh_clean_drift(tmp_path):
    guard, _, _, now = _fixture(tmp_path)
    control = tmp_path / "protected-control.json"
    drift = tmp_path / "protected-drift.json"
    control.write_text(json.dumps({
        "last_known_good": {"manifest": {
            "revision": SHA, "runtime_revision": SHA,
            "mcp_revision": SHA, "complete": True,
        }},
        "circuit_breaker": {"state": "open", "revalidated_revision": None},
    }))
    drift.write_text(json.dumps({
        "status": "pass", "problems": [], "observed_at": now.isoformat(),
    }))
    guard.control_path = control
    guard.drift_path = drift
    guard.enforce_protected_control = True
    assert guard.preexisting_core_health() is True
    assert guard.protected_release_status() == {
        "ready": False, "reason": "PMV4_PROTECTED_PRODUCTION_BREAKER_OPEN",
    }
    assert not guard.host_mutation_quiescent()
    with guard.host_release_transaction():
        assert not guard.host_mutation_quiescent()

    # Only a *separately governed*, recorded breaker revalidation can
    # change this root evidence. This simulated fixture is NOT host repair.
    doc = json.loads(control.read_text())
    doc["circuit_breaker"] = {
        "state": "closed", "revalidated_revision": SHA,
    }
    control.write_text(json.dumps(doc))
    assert guard.host_mutation_quiescent()
    assert guard.protected_release_status()["ready"] is True

    bad_drift = json.loads(drift.read_text())
    bad_drift["status"] = "fail"
    drift.write_text(json.dumps(bad_drift))
    assert not guard.host_mutation_quiescent()
    assert guard.protected_release_status()["reason"] == "PMV4_PRODUCTION_DRIFT_NOT_CLEAR"


def test_production_guard_cannot_disable_breaker_review():
    with pytest.raises(HostGateDenied, match="PROTECTED_BREAKER_CANNOT_BE_DISABLED"):
        IndependentHostGuard(production=True, enforce_protected_control=False)


def test_stale_protected_drift_denies_even_with_closed_breaker(tmp_path):
    guard, _, _, now = _fixture(tmp_path)
    guard.control_path = tmp_path / "control.json"
    guard.drift_path = tmp_path / "drift.json"
    guard.enforce_protected_control = True
    guard.control_path.write_text(json.dumps({
        "last_known_good": {"manifest": {
            "revision": SHA, "runtime_revision": SHA,
            "mcp_revision": SHA, "complete": True,
        }},
        "circuit_breaker": {"state": "closed", "revalidated_revision": SHA},
    }))
    guard.drift_path.write_text(json.dumps({
        "status": "pass", "problems": [],
        "observed_at": (now - timedelta(minutes=5)).isoformat(),
    }))
    assert guard.host_mutation_quiescent() is False
    assert guard.protected_release_status()["reason"] == "PMV4_PRODUCTION_DRIFT_NOT_FRESH"


def test_trusted_host_assembly_rechecks_breaker_after_shadow_activation(monkeypatch):
    from tools import pmv4_shadow_host_runtime as host
    state = {"breaker_ok": True}
    assembled = {}

    class FakeGuard:
        def preexisting_core_health(self): return True
        def host_mutation_quiescent(self): return state["breaker_ok"]
        def host_release_transaction(self): return None

    class FakeAdapter:
        def __init__(self, **kwargs):
            assert callable(kwargs["core_continuity_probe"])
        def activate_shadow(self, path): pass
        def restore_shadow(self, path): pass
        def verify_shadow_and_core(self, path): return True

    class FakeController:
        def __init__(self, *args, **kwargs):
            assembled.update(kwargs)

    monkeypatch.setattr(host, "IndependentHostGuard", FakeGuard)
    monkeypatch.setattr(host, "DockerShadowAdapter", FakeAdapter)
    monkeypatch.setattr(host, "ShadowController", FakeController)
    host.trusted_controller()
    checker = assembled["verify_shadow_and_core"]
    assert checker(Path("/synthetic-shadow")) is True
    state["breaker_ok"] = False
    assert checker(Path("/synthetic-shadow")) is False


def test_live_legacy_and_new_root_lock_ownership_policies_differ():
    import stat as statmod
    from tools.pmv4_host_release_guard import LEGACY_MANAGER_UID
    legacy = SimpleNamespace(
        st_mode=statmod.S_IFREG | 0o664, st_nlink=1, st_uid=LEGACY_MANAGER_UID
    )
    assert IndependentHostGuard._trusted_lock_metadata(
        legacy, expected_uid=LEGACY_MANAGER_UID, pmv4_root_lock=False
    )
    assert not IndependentHostGuard._trusted_lock_metadata(
        legacy, expected_uid=0, pmv4_root_lock=True
    )
    root = SimpleNamespace(
        st_mode=statmod.S_IFREG | 0o600, st_nlink=1, st_uid=0
    )
    assert IndependentHostGuard._trusted_lock_metadata(
        root, expected_uid=0, pmv4_root_lock=True
    )
    for untrusted_mode in (0o664, 0o666, 0o644):
        untrusted = SimpleNamespace(
            st_mode=statmod.S_IFREG | untrusted_mode, st_nlink=1, st_uid=0
        )
        assert not IndependentHostGuard._trusted_lock_metadata(
            untrusted, expected_uid=0, pmv4_root_lock=True
        )
