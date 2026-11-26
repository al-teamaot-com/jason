"""Isolated source-only full Windows Time read-only sweep parity acceptance."""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from autonomous_remediation.json_shadow_integration import JsonShadowBoundaryError
from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from jason_runtime.json_windows_time_sweep import WindowsTimeJsonIsolatedSweep
from jason_runtime.windows_time_source_shadow import (
    SQLiteWindowsTimeSourceShadowState, WindowsTimeSourceShadowMaintenance,
)
from implementation.runtime_service.tests.test_windows_time_source_shadow import (
    Reads, Audit, NOW, ALERT, time_alert,
)

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/windows_time_source.v1.json"


class ExactObserveFactory:
    def __init__(self):
        self.calls = []

    def build_observe(self, **kwargs):
        self.calls.append(dict(kwargs))
        assert kwargs["client_id"] == "riggins-company"
        assert kwargs["policy_id"] == "json-migration-readonly-preprod-v1"
        return SimpleNamespace(**kwargs)


class SyntheticOrchestrator:
    def __init__(self, provider):
        self.provider = provider

    def execute(self, request):
        output = self.provider.execute(request.capability_name, request.arguments)
        return SimpleNamespace(
            status=SimpleNamespace(value=output["status"]),
            stage=SimpleNamespace(value="completed"),
            capability_name=request.capability_name,
            provider_id="source-only-synthetic",
            reason_codes=(), error_code=None,
            correlation_id="synthetic-not-production",
            output=output["evidence"],
        )


def build_json(tmp_path, provider, *, clock=lambda: NOW, max_alerts=40):
    tmp_path.mkdir(parents=True, exist_ok=True)
    registry = SQLitePlaybookRegistry(tmp_path / "isolated-json-playbooks.sqlite3")
    registry.stage(json.loads(CANDIDATE.read_text()),
                   actor="source-only-isolated-acceptance")
    registry.close()
    persistence = SQLiteWindowsTimeSourceShadowState(
        tmp_path / "legacy-compatible-classification.sqlite3"
    )
    audit = Audit()
    factory = ExactObserveFactory()
    runner = WindowsTimeJsonIsolatedSweep(
        isolated_root=tmp_path, client_id="riggins-company",
        verified_site="Riggins Company",
        request_factory=factory,
        orchestrator=SyntheticOrchestrator(provider),
        state=persistence, clock=clock,
        max_alerts_per_sweep=max_alerts,
        audit=audit,
    )
    return runner, persistence, factory, audit


@pytest.mark.parametrize("case,current,history,online", [
    ("one_current", [time_alert()], (), True),
    ("recurring", [time_alert()], (
        time_alert("old-1", age_days=2),
        time_alert("old-2", age_days=8),
    ), True),
    ("offline", [time_alert()], (), False),
    ("unrelated", [
        dict(time_alert(), diagnostics="Unrelated monitor")
    ], (), True),
    ("empty", [], (), True),
    ("two_alerts", [time_alert(), time_alert("alert-2")], (), True),
])
def test_json_sweep_summary_and_audit_reconcile_actual_legacy_worker(
    tmp_path, case, current, history, online,
):
    original = Reads(current, history, online=online)
    (tmp_path / "legacy").mkdir(exist_ok=True)
    legacy_state = SQLiteWindowsTimeSourceShadowState(
        tmp_path / "legacy" / "existing-time-state.sqlite3"
    )
    legacy_audit = Audit()
    legacy = WindowsTimeSourceShadowMaintenance(
        reads=original, state=legacy_state, now=lambda: NOW,
        audit=legacy_audit,
    )
    expected = legacy.run_once(now=NOW)
    provider = Reads(current, history, online=online)
    json_sweep, state, factory, audit = build_json(tmp_path / "json", provider)
    try:
        actual = json_sweep.run_once(now=NOW)
        assert actual == expected
        assert audit.events == legacy_audit.events
        assert actual["mutations"] == 0
        assert state.last_run_at() == legacy_state.last_run_at() == NOW
        assert len(factory.calls) >= 1
        assert all(request["client_id"] == "riggins-company" for request in factory.calls)
        assert all(capability in {
            "management.alert.search", "endpoint.device.read",
            "endpoint.alert.history.search",
        } for capability, _ in provider.calls)
        before = len(provider.calls)
        assert json_sweep.tick() is False
        assert len(provider.calls) == before
        assert legacy.tick() is False
    finally:
        state.close()
        legacy_state.close()


def test_json_sweep_restart_15_minute_cadence_matches_legacy(tmp_path):
    at = [NOW]
    provider = Reads([time_alert()])
    runner, state, factory, audit = build_json(
        tmp_path / "json", provider, clock=lambda: at[0],
    )
    try:
        assert runner.tick() is True
        assert runner.tick() is False
        count = len(factory.calls)
    finally:
        state.close()
    at[0] += timedelta(minutes=14)
    persisted = SQLiteWindowsTimeSourceShadowState(
        tmp_path / "json" / "legacy-compatible-classification.sqlite3"
    )
    later = WindowsTimeJsonIsolatedSweep(
        isolated_root=tmp_path / "json",
        client_id="riggins-company", verified_site="Riggins Company",
        request_factory=factory, orchestrator=SyntheticOrchestrator(provider),
        state=persisted, clock=lambda: at[0], audit=audit,
    )
    try:
        assert later.tick() is False
        assert len(factory.calls) == count
        at[0] += timedelta(minutes=1)
        assert later.tick() is True
        # Old exact source+fingerprint still present; no duplicate change.
        assert len(audit.events) == 2
        assert audit.events[-1][1]["changed"] is False
        assert persisted.last_run_at() == at[0]
    finally:
        persisted.close()


def test_untrusted_site_does_not_mutate_and_is_inconclusive(tmp_path):
    alert = time_alert()
    alert["alertSourceInfo"]["siteName"] = "Different Customer"
    provider = Reads([alert])
    runner, state, factory, audit = build_json(tmp_path / "json", provider)
    try:
        summary = runner.run_once(now=NOW)
        assert summary["matched"] == 1
        assert summary["inconclusive"] == 1
        assert summary["identified"] == summary["mutations"] == 0
        assert audit.events == []
        assert [c for c, _ in provider.calls] == ["management.alert.search"]
    finally:
        state.close()


def test_duplicate_alert_uid_does_not_double_project(tmp_path):
    provider = Reads([time_alert(), time_alert()])
    runner, state, factory, audit = build_json(tmp_path / "json", provider)
    try:
        summary = runner.run_once(now=NOW)
        assert summary["matched"] == 2
        assert summary["identified"] == 0
        assert summary["inconclusive"] >= 1
        assert summary["mutations"] == 0
        assert audit.events == []
    finally:
        state.close()


def test_limit_rejects_large_alert_batch_instead_of_truncating(tmp_path):
    provider = Reads([time_alert(), time_alert("alert-2")])
    runner, state, factory, audit = build_json(
        tmp_path / "json", provider, max_alerts=1,
    )
    try:
        with pytest.raises(JsonShadowBoundaryError, match="ALERT_BATCH_LIMIT"):
            runner.run_once(now=NOW)
        assert audit.events == []
        assert state.last_run_at() is None
    finally:
        state.close()


def test_changed_source_after_next_due_reclassifies_not_reuses_stale_checkpoint(tmp_path):
    at = [NOW]
    provider = Reads([time_alert()], online=True)
    runner, state, factory, audit = build_json(
        tmp_path / "json", provider, clock=lambda: at[0],
    )
    try:
        first = runner.run_once(now=at[0])
        assert first["identified"] == 1
        assert first["changed"] == 1
        assert audit.events[-1][1]["classification"] == "CURRENT_TIME_SOURCE_MISMATCH"
        provider.online = False
        at[0] += timedelta(minutes=15)
        second = runner.run_once(now=at[0])
        assert second["identified"] == 1
        assert second["changed"] == 1
        assert second["waiting_device_access"] == 1
        assert audit.events[-1][1]["classification"] == "WAITING_DEVICE_ACCESS"
        assert state.last_run_at() == at[0]
        assert second["mutations"] == 0
    finally:
        state.close()
