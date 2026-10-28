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
    WindowsTimeJsonShadowEvidence,
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
