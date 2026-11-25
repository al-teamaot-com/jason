"""Current Windows time-source legacy shadow vs canonical JSON read-only parity.

All tests use synthetic existing Datto response fixtures. No live provider,
production JSON registry, endpoint component, Autotask write, or Core change.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from autonomous_remediation.json_shadow_integration import (
    GovernedJsonShadowIntegration, SQLiteJsonShadowState, JsonShadowBoundaryError,
)
from autonomous_remediation.playbook_document import validate_playbook_document
from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from jason_runtime.json_windows_time_facts import reduce_windows_time_shadow
from jason_runtime.windows_time_source_shadow import (
    WindowsTimeSourceShadowMaintenance, SQLiteWindowsTimeSourceShadowState,
    TimeSourceDecision, is_time_source_alert, parse_sources,
)
from implementation.runtime_service.tests.test_windows_time_source_shadow import (
    NOW, ALERT, DEVICE, Reads, time_alert, build,
)

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/windows_time_source.v1.json"
SCHEMA = ROOT / "docs/playbooks/json/playbook-v1.schema.json"
CLIENT_ID = "riggins-company"
SITE_NAME = "Riggins Company"
READS = frozenset({
    "management.alert.search", "endpoint.device.read",
    "endpoint.alert.history.search",
})


class ScopedTimeReads:
    bound_client_id = CLIENT_ID
    def __init__(self, provider):
        self.provider = provider

    def execute(self, capability, arguments):
        return self.provider.execute(capability, arguments)


def isolated(tmp_path, provider, *, at=NOW, site=SITE_NAME, version=None):
    raw = json.loads(CANDIDATE.read_text())
    if version is not None:
        raw["playbook"]["version"] = version
    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(raw)
    document = validate_playbook_document(raw)
    state = SQLiteJsonShadowState(tmp_path / "windows-time-json-run.sqlite3")
    runner = GovernedJsonShadowIntegration(
        document=document, state=state,
        read_port=ScopedTimeReads(provider),
        read_capabilities=READS,
        normalize=lambda cap, result, facts: reduce_windows_time_shadow(
            cap, result, facts, at=at, expected_site=site),
        clock=lambda: at,
    )
    return runner, state


def execute(runner, *, client_id=CLIENT_ID, target=ALERT):
    return runner.run(
        run_id=f"windows-time-{ALERT}", client_id=client_id, target_id=target,
        trusted_seed={"client_id": client_id, "target_id": target},
    )


@pytest.mark.parametrize("case,history,online,expected,expected_calls", [
    ("current", (), True, "classified_current", 3),
    ("recurring", (
        time_alert("old-1", age_days=2),
        time_alert("old-2", source="Local CMOS Clock", age_days=8)
    ), True, "classified_recurring", 3),
    ("old_history", (time_alert("very-old", age_days=31),),
     True, "classified_current", 3),
    ("offline", (), False, "classified_waiting", 2),
])
def test_same_legacy_classification_fingerprint_and_read_intents(
    tmp_path, case, history, online, expected, expected_calls,
):
    current = time_alert()
    legacy_reads = Reads([current], history, online=online)
    legacy = build(tmp_path / "legacy", legacy_reads)
    decision = legacy._classify(current, now=NOW)
    assert isinstance(decision, TimeSourceDecision)

    json_reads = Reads([current], history, online=online)
    runner, state = isolated(tmp_path / "json", json_reads)
    result = execute(runner)
    assert result.status == "completed_readonly"
    assert result.step_id == expected
    assert result.facts["classification"] == decision.classification
    assert result.facts["recurrence_count"] == decision.recurrence_count
    assert result.facts["classification_reason"] == decision.reason
    assert result.facts["decision_fingerprint"] == decision.fingerprint
    assert tuple(result.facts["approved_sources"]) == decision.approved_sources
    assert result.facts["observed_source"] == decision.observed_source
    assert len(json_reads.calls) == expected_calls
    assert [cap for cap, _ in json_reads.calls] == [
        "management.alert.search", *[cap for cap, _ in legacy_reads.calls]
    ]
    assert json_reads.calls[0] == ("management.alert.search", {"status": "open"})
    assert all(cap not in {
        "automation.component.execute", "endpoint.alert.resolve",
        "service.ticket.note.create", "service.ticket.update",
    } for cap, _ in json_reads.calls)
    assert runner.document.autonomy_activation == "shadow"
    state.close()
    legacy.state.close()


def test_unrelated_signature_is_skipped_without_endpoint_read(tmp_path):
    unrelated = time_alert()
    unrelated["diagnostics"] = "Some unrelated component warning"
    provider = Reads([unrelated])
    runner, store = isolated(tmp_path, provider)
    result = execute(runner)
    assert result.status == "completed_readonly"
    assert result.step_id == "unrelated_alert"
    assert provider.calls == [("management.alert.search", {"status": "open"})]
    assert is_time_source_alert(unrelated) is False
    store.close()


def test_legacy_and_json_both_fail_closed_on_hostname_mismatch(tmp_path):
    source = time_alert()
    class WrongHostReads(Reads):
        def execute(self, capability, arguments):
            result = super().execute(capability, arguments)
            if capability == "endpoint.device.read":
                result["evidence"]["record"]["hostname"] = "WRONG-HOST"
            return result
    legacy_reads = WrongHostReads([source])
    legacy = build(tmp_path / "legacy", legacy_reads)
    assert legacy._classify(source, now=NOW) is None
    provider = WrongHostReads([source])
    runner, state = isolated(tmp_path / "json", provider)
    result = execute(runner)
    assert result.status == "failed_closed"
    assert provider.calls[-1][0] == "endpoint.device.read"
    state.close()
    legacy.state.close()


def test_cross_client_site_rejected_before_endpoint_call(tmp_path):
    provider = Reads([time_alert()])
    runner, state = isolated(tmp_path, provider, site="Different Client")
    result = execute(runner)
    assert result.status == "failed_closed"
    assert provider.calls == [("management.alert.search", {"status": "open"})]
    state.close()


def test_multiple_alerts_same_uid_rejected_and_do_not_select_first(tmp_path):
    provider = Reads([time_alert(), time_alert()])
    runner, state = isolated(tmp_path, provider)
    result = execute(runner)
    assert result.status == "failed_closed"
    assert len(provider.calls) == 1
    state.close()


def test_missing_required_diagnostics_legacy_and_json_inconclusive(tmp_path):
    bad = time_alert()
    bad["diagnostics"] = (
        "Time source mismatch. Current source 'Local CMOS Clock' "
        "is not in approved list: "
    )
    legacy = build(tmp_path / "legacy", Reads([bad]))
    assert legacy._classify(bad, now=NOW) is None
    runner, state = isolated(tmp_path / "json", Reads([bad]))
    result = execute(runner)
    assert result.status == "needs_human_review"
    assert result.step_id == "inconclusive"
    state.close()
    legacy.state.close()


def test_invalid_client_seed_cannot_assert_health_or_approval(tmp_path):
    provider = Reads([time_alert()])
    runner, state = isolated(tmp_path, provider)
    with pytest.raises(JsonShadowBoundaryError, match="SEED_FACTS_NOT_TRUSTED"):
        runner.run(
            run_id=f"windows-time-{ALERT}",
            client_id=CLIENT_ID, target_id=ALERT,
            trusted_seed={
                "client_id": CLIENT_ID, "target_id": ALERT,
                "recurring_failure": False,
            },
        )
    assert provider.calls == []
    state.close()


def test_interruption_resume_does_not_repeat_completed_current_read(tmp_path):
    provider = Reads([time_alert()])
    runner, state = isolated(tmp_path, provider)
    first = runner.run(
        run_id=f"windows-time-{ALERT}", client_id=CLIENT_ID, target_id=ALERT,
        trusted_seed={"client_id": CLIENT_ID, "target_id": ALERT},
        max_steps=1,
    )
    assert first.status == "step_budget_exhausted"
    assert len(provider.calls) == 1
    state.close()
    resumed, state = isolated(tmp_path, provider)
    result = execute(resumed)
    assert result.status == "completed_readonly"
    assert len(provider.calls) == 3
    assert [c for c, _ in provider.calls].count("management.alert.search") == 1
    assert execute(resumed) == result
    assert len(provider.calls) == 3
    state.close()


def test_immutable_json_draft_is_staged_only_in_isolated_registry(tmp_path):
    doc = json.loads(CANDIDATE.read_text())
    registry_path = tmp_path / "isolated-json-registry.sqlite3"
    store = SQLitePlaybookRegistry(registry_path)
    stage = store.stage(doc, actor="source-only-migration-fixture")
    assert stage.state == "draft"
    assert store.active("windows_time_source") is None
    assert store.generation() == 1
    store.close()
    reopened = SQLitePlaybookRegistry(registry_path)
    assert reopened.get("windows_time_source", "0.1.0-migration.1").state == "draft"
    assert reopened.active("windows_time_source") is None
    assert reopened.generation() == 1
    reopened.close()


def test_fingerprint_drift_on_resume_fails_closed(tmp_path):
    provider = Reads([time_alert()])
    runner, state = isolated(tmp_path, provider)
    first = runner.run(
        run_id=f"windows-time-{ALERT}", client_id=CLIENT_ID, target_id=ALERT,
        trusted_seed={"client_id": CLIENT_ID, "target_id": ALERT}, max_steps=1,
    )
    assert first.status == "step_budget_exhausted"
    state.close()
    later, state = isolated(tmp_path, provider, version="0.1.1-migration.1")
    with pytest.raises(JsonShadowBoundaryError, match="RUN_RESUME_IDENTITY_OR_VERSION_CHANGED"):
        execute(later)
    state.close()


def test_projection_reuses_existing_shadow_state_and_audit_with_exact_legacy_parity(tmp_path):
    from jason_runtime.json_windows_time_projection import project_windows_time_json_decision
    from implementation.runtime_service.tests.test_windows_time_source_shadow import Audit
    history = [
        time_alert("old-1", age_days=2),
        time_alert("old-2", source="Local CMOS Clock", age_days=8),
    ]
    legacy = build(tmp_path / "legacy", Reads([time_alert()], history))
    legacy_summary = legacy.run_once(now=NOW)
    assert legacy_summary["changed"] == 1
    original_event = legacy.audit.events[0]

    provider = Reads([time_alert()], history)
    runner, checkpoint = isolated(tmp_path / "json", provider)
    result = execute(runner)
    durable = SQLiteWindowsTimeSourceShadowState(
        tmp_path / "json" / "same-legacy-compatible-shadow.sqlite3")
    audit = Audit()
    try:
        assert project_windows_time_json_decision(
            result=result, state=durable, at=NOW, audit=audit
        ) is True
        assert audit.events[0] == original_event
        assert project_windows_time_json_decision(
            result=result, state=durable, at=NOW, audit=audit
        ) is False
        assert audit.events[1][1]["changed"] is False
        row = durable._connection.execute(
            "SELECT * FROM windows_time_source_shadow_state WHERE alert_uid=?",
            (ALERT,),
        ).fetchone()
        assert row is not None
        assert row["fingerprint"] == result.facts["decision_fingerprint"]
        assert row["classification"] == "RECURRING_FAILURE"
        assert row["recurrence_count"] == 3
        assert row["approved_sources_json"] == '["ADSRV.Rigginsco.local"]'
        assert row["first_seen_at"] == row["last_seen_at"] == NOW.isoformat()
        assert "mutated" not in row.keys()  # source stores evidence, not provider actions.
    finally:
        durable.close()
        checkpoint.close()
        legacy.state.close()


@pytest.mark.parametrize("change", [
    {"decision_fingerprint": "0" * 64},
    {"classification": "CURRENT_TIME_SOURCE_MISMATCH"},
    {"recurrence_count": 0},
    {"verified_site_client_binding": False},
    {"endpoint_identity_verified": False},
])
def test_projection_rejects_forged_or_inconsistent_classification_without_write(
    tmp_path, change,
):
    from dataclasses import replace
    from jason_runtime.json_windows_time_projection import project_windows_time_json_decision
    provider = Reads([time_alert()], [
        time_alert("old-1", age_days=2),
        time_alert("old-2", age_days=8),
    ])
    runner, checkpoint = isolated(tmp_path / "json", provider)
    result = execute(runner)
    changed_facts = dict(result.facts, **change)
    forged = replace(result, facts=changed_facts)
    durable = SQLiteWindowsTimeSourceShadowState(
        tmp_path / "json" / "projection-untrusted.sqlite3")
    try:
        with pytest.raises(JsonShadowBoundaryError, match="TIME_SOURCE_PROJECTION_"):
            project_windows_time_json_decision(
                result=forged, state=durable, at=NOW)
        count = durable._connection.execute(
            "SELECT count(*) FROM windows_time_source_shadow_state"
        ).fetchone()[0]
        assert count == 0
    finally:
        checkpoint.close()
        durable.close()


def test_unrelated_alert_does_not_project_or_audit(tmp_path):
    from jason_runtime.json_windows_time_projection import project_windows_time_json_decision
    from implementation.runtime_service.tests.test_windows_time_source_shadow import Audit
    unrelated = time_alert()
    unrelated["diagnostics"] = "Other monitor"
    runner, checkpoint = isolated(tmp_path / "json", Reads([unrelated]))
    result = execute(runner)
    durable = SQLiteWindowsTimeSourceShadowState(
        tmp_path / "json" / "unrelated.sqlite3")
    audit = Audit()
    try:
        assert project_windows_time_json_decision(
            result=result, state=durable, at=NOW, audit=audit
        ) is None
        assert audit.events == []
        assert durable._connection.execute(
            "SELECT count(*) FROM windows_time_source_shadow_state"
        ).fetchone()[0] == 0
    finally:
        checkpoint.close()
        durable.close()
