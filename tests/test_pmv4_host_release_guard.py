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
