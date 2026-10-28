"""Isolated governed-read simulation for the Windows Time JSON migration pilot."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
IMPLEMENTATION = ROOT / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from autonomous_remediation.playbook_document import validate_playbook_document
from jason_runtime.windows_time_json_shadow_evidence import (
    SQLiteWindowsTimeJsonShadowState,
    WindowsTimeJsonShadowEvidence,
)
from jason_runtime.windows_time_source_shadow_composition import (
    build_windows_time_json_shadow_observer,
)
from jason_runtime.windows_time_source_shadow import (
    SQLiteWindowsTimeSourceShadowState,
    WindowsTimeSourceShadowMaintenance,
)

NOW = datetime(2026, 10, 28, 18, 30, tzinfo=timezone.utc)
ALERT_UID = "136898e4-f961-4b34-bd54-fd610bda5163"
DEVICE_UID = "ea3b591e-15a4-8e4f-a2a6-59a7793ea2c9"
SITE_UID = "a3f7b170-1fbb-4d0f-97d7-3623d21992cd"
HOSTNAME = "TEST-WIN11-001"
SITE = "Test Organization"
PATH = ROOT / "docs/playbooks/json/candidates/windows_time_source-0.1.0-jsonpreview.json"


def alert(uid=ALERT_UID, *, age_minutes=10, device_uid=DEVICE_UID, site_uid=SITE_UID):
    return {
        "alertUid": uid,
        "resolved": False,
        "timestamp": int((NOW - timedelta(minutes=age_minutes)).timestamp() * 1000),
        "diagnostics": (
            "\r\nTime source mismatch. Current source 'Local CMOS Clock' "
            "is not in approved list: dc1.example.test\r\n"
        ),
        "alertContext": {"@class": "comp_script_ctx"},
        "alertSourceInfo": {
            "deviceUid": device_uid,
            "deviceName": HOSTNAME,
            "siteUid": site_uid,
            "siteName": SITE,
        },
    }


def envelope(capability, evidence, *, status="succeeded", provider="datto_rmm"):
    return {
        "status": status,
        "stage": "completed",
        "capability": capability,
        "provider": provider,
        "reason_codes": ["capability_completed"],
        "error_code": None,
        "correlation_id": "corr-test-" + capability.replace(".", "-"),
        "evidence": evidence,
    }


class GovernedReadsFixture:
    def __init__(
        self, *, current=None, history=None, online=True, record_overrides=None,
        bad_capability=None, fail_capability=None, truncated_history=False,
    ):
        self.current = list(current if current is not None else [alert()])
        self.history = list(history or [])
        self.online = online
        self.record_overrides = record_overrides or {}
        self.bad_capability = bad_capability
        self.fail_capability = fail_capability
        self.truncated_history = truncated_history
        self.calls = []

    def execute(self, capability, arguments):
        assert capability in {
            "management.alert.search", "endpoint.device.read", "endpoint.alert.history.search"
        }, "No other provider operation is permitted"
        self.calls.append((capability, dict(arguments)))
        if self.fail_capability == capability:
            raise ConnectionError("simulated provider read failure")
        if capability == "management.alert.search":
            assert arguments == {"status": "open"}
            payload = {"data": {"pageDetails": {"count": len(self.current)},
                                "alerts": self.current}}
        elif capability == "endpoint.device.read":
            assert arguments == {"resource_id": DEVICE_UID}
            record = {
                "resource_id": DEVICE_UID,
                "hostname": HOSTNAME,
                "site_id": SITE_UID,
                "site": SITE,
                "online": self.online,
            }
            record.update(self.record_overrides)
            payload = {"record": record}
        else:
            assert arguments == {"resource_id": DEVICE_UID}
            count = len(self.history) + (1 if self.truncated_history else 0)
            payload = {"data": {"pageDetails": {"count": count},
                                "alerts": self.history}}
        env = envelope(capability, payload)
        if self.bad_capability == capability:
            env["provider"] = "unverified_provider"
        return env


def candidate_document():
    return validate_playbook_document(
        json.loads(PATH.read_text(encoding="utf-8")),
        known_capabilities=set(),
    )


def assess(reads, *, now=NOW):
    return WindowsTimeJsonShadowEvidence(
        reads=reads, document=candidate_document()
    ).assess(alert_uid=ALERT_UID, now=now)


def assert_inert(verdict, reads):
    assert verdict.side_effects == 0
    assert verdict.staged is False
    assert verdict.activated is False
    assert verdict.terminal_step.startswith("review_")
    assert all(capability in {
        "management.alert.search", "endpoint.device.read", "endpoint.alert.history.search"
    } for capability, _ in reads.calls)
    assert all(value not in str(reads.calls) for value in [
        "automation.component.execute", "service.ticket.update",
        "endpoint.alert.resolve", "service.ticket.note.create",
    ])


def test_read_only_verified_identity_but_unproven_diagnostic_fails_closed():
    reads = GovernedReadsFixture()
    verdict = assess(reads)
    assert verdict.terminal_step == "review_inconclusive"
    assert verdict.reason_code == "DEDICATED_TIME_DIAGNOSTIC_AND_SITE_POLICY_NOT_VERIFIED"
    assert verdict.recurrence_count == 1
    assert verdict.alert_uid == ALERT_UID
    assert verdict.device_uid == DEVICE_UID
    assert verdict.site_uid == SITE_UID
    assert verdict.source_fingerprint and len(verdict.source_fingerprint) == 64
    assert len(verdict.correlation_ids) == 3
    assert reads.calls == [
        ("management.alert.search", {"status": "open"}),
        ("endpoint.device.read", {"resource_id": DEVICE_UID}),
        ("endpoint.alert.history.search", {"resource_id": DEVICE_UID}),
    ]
    assert_inert(verdict, reads)


def test_recurring_failure_from_exact_device_history_is_human_review(tmp_path):
    history = [alert("prior1", age_minutes=3 * 24 * 60),
               alert("prior2", age_minutes=8 * 24 * 60)]
    reads = GovernedReadsFixture(history=history)
    verdict = assess(reads)
    assert verdict.terminal_step == "review_recurring"
    assert verdict.recurrence_count == 3
    assert_inert(verdict, reads)

    # Compare the same provider-shaped evidence through the existing legacy
    # governed shadow path, not an independently invented classification.
    legacy = WindowsTimeSourceShadowMaintenance(
        reads=GovernedReadsFixture(history=history),
        state=SQLiteWindowsTimeSourceShadowState(tmp_path / "legacy.sqlite3"),
        now=lambda: NOW,
    )
    legacy_summary = legacy.run_once(now=NOW)
    assert legacy_summary["recurring"] == 1
    assert legacy_summary["mutations"] == 0
    legacy.state.close()


def test_stale_open_alert_is_not_treated_as_current_healthy_or_repairable():
    reads = GovernedReadsFixture(current=[alert(age_minutes=60 * 24 * 60)])
    verdict = assess(reads)
    assert verdict.terminal_step == "review_stale_alert"
    assert verdict.reason_code == "ALERT_STALE_OR_TIMESTAMP_UNVERIFIED"
    assert verdict.recurrence_count is None
    assert all(cap != "endpoint.alert.history.search" for cap, _ in reads.calls)
    assert_inert(verdict, reads)


def test_offline_endpoint_returns_waiting_review_without_history_reads():
    reads = GovernedReadsFixture(online=False)
    verdict = assess(reads)
    assert verdict.terminal_step == "review_waiting_endpoint"
    assert all(cap != "endpoint.alert.history.search" for cap, _ in reads.calls)
    assert_inert(verdict, reads)


@pytest.mark.parametrize("case", ["missing", "wrong_site", "wrong_host", "no_site"])
def test_exact_object_and_site_binding_fail_closed(case):
    if case == "missing":
        reads = GovernedReadsFixture(current=[])
    elif case == "wrong_site":
        reads = GovernedReadsFixture(record_overrides={"site_id": "other-company-site"})
    elif case == "wrong_host":
        reads = GovernedReadsFixture(record_overrides={"hostname": "OTHER-HOST"})
    else:
        reads = GovernedReadsFixture(record_overrides={"site_id": ""})
    verdict = assess(reads)
    assert verdict.terminal_step == "review_identity_blocked"
    assert all(cap != "endpoint.alert.history.search" for cap, _ in reads.calls)
    assert_inert(verdict, reads)


@pytest.mark.parametrize(
    "failed_capability,expected",
    [
        ("management.alert.search", "review_identity_blocked"),
        ("endpoint.device.read", "review_identity_blocked"),
        ("endpoint.alert.history.search", "review_inconclusive"),
    ],
)
def test_failed_or_unavailable_reads_never_infer_healthy(failed_capability, expected):
    reads = GovernedReadsFixture(fail_capability=failed_capability)
    verdict = assess(reads)
    assert verdict.terminal_step == expected
    assert_inert(verdict, reads)


def test_history_pagination_or_unknown_timestamp_cannot_disprove_recurrence():
    reads = GovernedReadsFixture(truncated_history=True)
    verdict = assess(reads)
    assert verdict.terminal_step == "review_inconclusive"
    assert verdict.reason_code == "RECURRENCE_HISTORY_PAGINATION_UNVERIFIED"
    assert verdict.recurrence_count is None
    assert_inert(verdict, reads)


def test_prior_history_cannot_cross_site_boundaries():
    reads = GovernedReadsFixture(history=[
        alert("prior1", site_uid="different-site", age_minutes=60),
    ])
    verdict = assess(reads)
    assert verdict.terminal_step == "review_inconclusive"
    assert verdict.reason_code == "RECURRENCE_HISTORY_CROSS_CLIENT"
    assert verdict.recurrence_count is None
    assert_inert(verdict, reads)


def test_duplicate_prior_alert_uids_are_counted_once():
    prior = alert("prior1", age_minutes=120)
    reads = GovernedReadsFixture(history=[prior, deepcopy(prior)])
    verdict = assess(reads)
    assert verdict.terminal_step == "review_inconclusive"
    assert verdict.recurrence_count == 2
    assert_inert(verdict, reads)


def test_wrong_provider_envelope_fails_closed():
    reads = GovernedReadsFixture(bad_capability="endpoint.device.read")
    verdict = assess(reads)
    assert verdict.terminal_step == "review_identity_blocked"
    assert_inert(verdict, reads)


def test_review_only_guards_reject_executable_preview_without_read():
    doc = candidate_document()
    payload = deepcopy(doc.payload)
    payload["steps"][0]["capability"] = "endpoint.alert.resolve"
    # The canonical validator accepts the syntactically valid capability field
    # on a decision; the shadow bridge is intentionally stricter.
    manipulated = validate_playbook_document(payload)
    reads = GovernedReadsFixture()
    with pytest.raises(ValueError, match="EXECUTION_AUTHORITY_FORBIDDEN|EXECUTABLE_STEP_FORBIDDEN"):
        WindowsTimeJsonShadowEvidence(reads=reads, document=manipulated)
    assert reads.calls == []


def test_no_arbitrary_fact_or_endpoint_argument_is_accepted():
    reads = GovernedReadsFixture()
    bridge = WindowsTimeJsonShadowEvidence(reads=reads, document=candidate_document())
    with pytest.raises(ValueError, match="EXACT_ALERT_UID_REQUIRED"):
        bridge.assess(alert_uid="", now=NOW)
    with pytest.raises(ValueError, match="AWARE_TIME_REQUIRED"):
        bridge.assess(alert_uid=ALERT_UID, now=datetime(2026, 10, 28))
    assert reads.calls == []


class MemoryAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, data):
        self.events.append((event_type, dict(data)))


def test_json_shadow_runs_inside_existing_legacy_cadence_without_second_alert_list(tmp_path):
    reads = GovernedReadsFixture()
    observer, json_state = build_windows_time_json_shadow_observer(
        reads=reads,
        document_path=PATH,
        state_db=tmp_path / "json-shadow.sqlite3",
    )
    audit = MemoryAudit()
    legacy_state = SQLiteWindowsTimeSourceShadowState(tmp_path / "legacy.sqlite3")
    worker = WindowsTimeSourceShadowMaintenance(
        reads=reads,
        state=legacy_state,
        now=lambda: NOW,
        audit=audit,
        json_shadow=observer,
        json_shadow_state=json_state,
        json_shadow_allowed_site_uids=frozenset({SITE_UID}),
    )
    first = worker.run_once(now=NOW)
    assert first["matched"] == 1
    assert first["identified"] == 1
    assert first["mutations"] == 0
    assert first["json_shadow_changed"] == 1
    assert first["json_shadow_selected"] == 1
    assert first["json_shadow_failures"] == 0
    assert [cap for cap, _ in reads.calls].count("management.alert.search") == 1
    assert len([x for x in reads.calls if x[0] == "endpoint.device.read"]) == 2
    assert len([x for x in reads.calls if x[0] == "endpoint.alert.history.search"]) == 2
    persisted = json_state.read_one(ALERT_UID)
    assert persisted["terminal_step"] == "review_inconclusive"
    assert persisted["reason_code"] == "DEDICATED_TIME_DIAGNOSTIC_AND_SITE_POLICY_NOT_VERIFIED"
    assert len(persisted["decision_fingerprint"]) == 64
    assert len(persisted["correlation_ids"]) == 3
    assert len([e for e in audit.events if e[0] == "autonomy.windows_time_json_shadow"]) == 1

    next_result = worker.run_once(now=NOW + timedelta(minutes=15))
    assert next_result["json_shadow_changed"] == 0
    assert next_result["json_shadow_failures"] == 0
    assert next_result["identified"] == 1
    assert len([e for e in audit.events if e[0] == "autonomy.windows_time_json_shadow"]) == 1
    persisted_later = json_state.read_one(ALERT_UID)
    assert persisted_later["decision_fingerprint"] == persisted["decision_fingerprint"]
    assert persisted_later["first_seen_at"] == persisted["first_seen_at"]
    assert persisted_later["last_seen_at"] != persisted["last_seen_at"]
    json_state.close()
    legacy_state.close()


def test_json_shadow_state_survives_restart_without_duplicate_change(tmp_path):
    reads = GovernedReadsFixture()
    first_observer, first_store = build_windows_time_json_shadow_observer(
        reads=reads, document_path=PATH, state_db=tmp_path / "json-shadow.sqlite3"
    )
    first = first_observer.assess(alert_uid=ALERT_UID, now=NOW)
    assert first_store.record(first, document_fingerprint=first_observer.document.fingerprint, when=NOW) is True
    first_store.close()

    second_observer, second_store = build_windows_time_json_shadow_observer(
        reads=reads, document_path=PATH, state_db=tmp_path / "json-shadow.sqlite3"
    )
    second = second_observer.assess(alert_uid=ALERT_UID, now=NOW + timedelta(minutes=15))
    assert second_store.record(
        second, document_fingerprint=second_observer.document.fingerprint,
        when=NOW + timedelta(minutes=15)
    ) is False
    assert second_store.read_one(ALERT_UID)["first_seen_at"] == NOW.isoformat()
    second_store.close()


def test_existing_legacy_worker_keeps_operating_when_json_observer_fails(tmp_path):
    class FaultyObserver:
        def assess(self, **_kwargs):
            raise RuntimeError("synthetic JSON-only failure")

    reads = GovernedReadsFixture()
    audit = MemoryAudit()
    state = SQLiteWindowsTimeSourceShadowState(tmp_path / "legacy.sqlite3")
    worker = WindowsTimeSourceShadowMaintenance(
        reads=reads,
        state=state,
        now=lambda: NOW,
        audit=audit,
        json_shadow=FaultyObserver(),
        json_shadow_state=object(),
        json_shadow_allowed_site_uids=frozenset({SITE_UID}),
    )
    result = worker.run_once(now=NOW)
    assert result["matched"] == 1
    assert result["identified"] == 1
    assert result["json_shadow_failures"] == 1
    assert result["mutations"] == 0
    assert any(event == "autonomy.windows_time_json_shadow_failure" for event, _ in audit.events)
    state.close()


def test_bounded_json_shadow_rotation_does_not_starve_matching_alerts(tmp_path):
    reads = GovernedReadsFixture(current=[alert("alert-a"), alert("alert-b")])
    observer, json_state = build_windows_time_json_shadow_observer(
        reads=reads, document_path=PATH, state_db=tmp_path / "json-shadow.sqlite3"
    )
    state = SQLiteWindowsTimeSourceShadowState(tmp_path / "legacy.sqlite3")
    worker = WindowsTimeSourceShadowMaintenance(
        reads=reads,
        state=state,
        now=lambda: NOW,
        json_shadow=observer,
        json_shadow_state=json_state,
        json_shadow_allowed_site_uids=frozenset({SITE_UID}),
        json_shadow_max_alerts_per_tick=1,
    )
    result1 = worker.run_once(now=NOW)
    result2 = worker.run_once(now=NOW + timedelta(minutes=15))
    assert result1["matched"] == 2
    assert result2["matched"] == 2
    assert result1["json_shadow_selected"] == 1
    assert result2["json_shadow_selected"] == 1
    assert result1["json_shadow_deferred"] == 1
    assert result2["json_shadow_deferred"] == 1
    assert json_state.read_one("alert-a") is not None
    assert json_state.read_one("alert-b") is not None
    json_state.close()
    state.close()


def test_opt_in_requires_inert_document_and_exact_version(tmp_path):
    reads = GovernedReadsFixture()
    _, state = build_windows_time_json_shadow_observer(
        reads=reads, document_path=PATH, state_db=tmp_path / "valid.sqlite3"
    )
    state.close()

    bad = json.loads(PATH.read_text(encoding="utf-8"))
    bad["playbook"]["version"] = "0.1.1-jsonpreview"
    path = tmp_path / "invalid-version.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="EXACT_VERSION_REQUIRED"):
        build_windows_time_json_shadow_observer(
            reads=reads, document_path=path,
            state_db=tmp_path / "should-not-exist.sqlite3",
        )
    assert not (tmp_path / "should-not-exist.sqlite3").exists()

    bad["playbook"]["version"] = "0.1.0-jsonpreview"
    bad["autonomy"]["activation"] = "autonomous"
    bad["autonomy"]["allowed_capabilities"] = ["endpoint.alert.resolve"]
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        build_windows_time_json_shadow_observer(
            reads=reads, document_path=path,
            state_db=tmp_path / "should-still-not-exist.sqlite3",
        )
    assert not (tmp_path / "should-still-not-exist.sqlite3").exists()


def test_json_shadow_runtime_build_contract_and_default_off():
    docker = (ROOT / "infrastructure/jason-runtime/Dockerfile").read_text(encoding="utf-8")
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    compose = (ROOT / "infrastructure/jason-runtime/compose.yaml").read_text(encoding="utf-8")
    candidate_path = "docs/playbooks/json/candidates/windows_time_source-0.1.0-jsonpreview.json"
    installed_path = "/app/config/json-playbooks/windows_time_source-0.1.0-jsonpreview.json"
    assert f"COPY {candidate_path} {installed_path}" in docker
    assert f"!{candidate_path}" in ignore
    assert "JASON_WINDOWS_TIME_JSON_SHADOW_ENABLED:-false" in compose
    assert installed_path in compose
    assert "JASON_WINDOWS_TIME_JSON_SHADOW_MAX_ALERTS_PER_TICK:-25" in compose
    assert "JASON_WINDOWS_TIME_JSON_SHADOW_SITE_UID_ALLOWLIST:-" in compose



def test_out_of_scope_site_is_not_observed_by_json_but_legacy_continues(tmp_path):
    reads = GovernedReadsFixture(
        current=[alert("outside", site_uid="another-site"), alert("inside")]
    )
    observer, json_state = build_windows_time_json_shadow_observer(
        reads=reads, document_path=PATH, state_db=tmp_path / "json.sqlite3"
    )
    state = SQLiteWindowsTimeSourceShadowState(tmp_path / "legacy.sqlite3")
    worker = WindowsTimeSourceShadowMaintenance(
        reads=reads, state=state, now=lambda: NOW,
        json_shadow=observer, json_shadow_state=json_state,
        json_shadow_allowed_site_uids=frozenset({SITE_UID}),
    )
    summary = worker.run_once(now=NOW)
    assert summary["matched"] == 2
    assert summary["identified"] == 2
    assert summary["json_shadow_selected"] == 1
    assert summary["json_shadow_outside_site_allowlist"] == 1
    assert json_state.read_one("outside") is None
    assert json_state.read_one("inside") is not None
    assert summary["mutations"] == 0
    json_state.close()
    state.close()


def test_json_shadow_rejects_missing_canary_scope_before_any_reads(tmp_path):
    reads = GovernedReadsFixture()
    observer, json_state = build_windows_time_json_shadow_observer(
        reads=reads, document_path=PATH, state_db=tmp_path / "json.sqlite3"
    )
    state = SQLiteWindowsTimeSourceShadowState(tmp_path / "legacy.sqlite3")
    try:
        with pytest.raises(ValueError, match="exact site UID allowlist"):
            WindowsTimeSourceShadowMaintenance(
                reads=reads, state=state,
                json_shadow=observer,
                json_shadow_state=json_state,
            )
        assert reads.calls == []
    finally:
        state.close()
        json_state.close()
