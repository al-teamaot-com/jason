"""Isolated preproduction composition: real existing observe port, fake provider.

No production registry, Ticket Core service, root policy, release or provider
write is touched by this test.
"""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from autonomous_remediation.json_shadow_integration import JsonShadowBoundaryError
from jason_runtime.json_playbook_readonly_preprod import (
    build_json_readonly_preprod_pilot, PILOT_ID, PILOT_VERSION,
)
from tests.test_json_governed_shadow_integration import (
    FakeGovernedObserve, NOW,
)

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/drmm_recent_alert_readonly_shadow_pilot.v1.json"


class ExactFactory:
    def __init__(self):
        self.calls = []

    def build_observe(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(**kwargs)


class FakeCentralOrchestrator:
    def __init__(self, case):
        self.provider = FakeGovernedObserve(case=case)
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        assert request.client_id == "company-1"
        assert request.policy_id == "json-migration-readonly-preprod-v1"
        output = self.provider.execute(request.capability_name, request.arguments)
        return SimpleNamespace(
            status=SimpleNamespace(value=output["status"]),
            stage=SimpleNamespace(value="completed"),
            capability_name=request.capability_name,
            provider_id="synthetic-only",
            reason_codes=(), error_code=None,
            correlation_id="fixture-correlation",
            output=output["evidence"],
        )


def prep(tmp_path):
    document = json.loads(CANDIDATE.read_text())
    store = SQLitePlaybookRegistry(tmp_path / "isolated-json-playbooks.sqlite3")
    result = store.stage(document, actor="isolated-test-only")
    assert result.state == "draft"
    store.close()


def compose(tmp_path, *, case):
    factory = ExactFactory()
    orchestrator = FakeCentralOrchestrator(case)
    runner = build_json_readonly_preprod_pilot(
        enabled=True, isolated_root=tmp_path, client_id="company-1",
        request_factory=factory, orchestrator=orchestrator,
        clock=lambda: NOW,
    )
    return runner, factory, orchestrator


def execute(runner):
    return runner.run(
        run_id="isolated-preprod-proof", client_id="company-1",
        target_id="alert-1",
        trusted_seed={"client_id": "company-1", "target_id": "alert-1"},
    )


@pytest.mark.parametrize("case,expected,reads", [
    ("unsupported", "unsupported_class", 1),
    ("old", "outside_window", 1),
    ("offline", "waiting_offline", 2),
    ("active", "active_detections", 4),
    ("healthy", "healthy_observed", 4),
])
def test_exact_staged_draft_real_governed_observe_composition(
    tmp_path, case, expected, reads,
):
    prep(tmp_path)
    runner, factory, orchestrator = compose(tmp_path, case=case)
    try:
        result = execute(runner)
        assert result.status == "completed_readonly"
        assert result.step_id == expected
        assert len(factory.calls) == reads
        assert len(orchestrator.calls) == reads
        assert not orchestrator.provider.mutations
        assert all(call["client_id"] == "company-1" for call in factory.calls)
        assert all(call["policy_id"] == "json-migration-readonly-preprod-v1"
                   for call in factory.calls)
        before = len(orchestrator.calls)
        assert execute(runner) == result
        assert len(orchestrator.calls) == before
    finally:
        runner.state.close()
    store = SQLitePlaybookRegistry(
        tmp_path / "isolated-json-playbooks.sqlite3", read_only=True)
    try:
        assert store.get(PILOT_ID, PILOT_VERSION).state == "draft"
        assert store.active(PILOT_ID) is None
        assert store.generation() == 1
    finally:
        store.close()


def test_disabled_preprod_composition_never_touches_disk_or_port(tmp_path):
    absent = tmp_path / "does-not-exist"
    assert build_json_readonly_preprod_pilot(
        enabled=False, isolated_root=absent, client_id="company-1",
        request_factory=None, orchestrator=None, clock=lambda: NOW,
    ) is None
    assert not absent.exists()


def test_isolated_registry_missing_rejected_without_any_execution(tmp_path):
    factory = ExactFactory()
    orchestrator = FakeCentralOrchestrator("healthy")
    with pytest.raises(JsonShadowBoundaryError, match="REGISTRY_MISSING"):
        build_json_readonly_preprod_pilot(
            enabled=True, isolated_root=tmp_path, client_id="company-1",
            request_factory=factory, orchestrator=orchestrator, clock=lambda: NOW,
        )
    assert not factory.calls
    assert not orchestrator.calls


def test_wrong_immutable_pilot_version_or_schema_content_rejected(tmp_path):
    payload = json.loads(CANDIDATE.read_text())
    payload["expected_state"]["only_authoritative_health_classification"] = False
    registry = SQLitePlaybookRegistry(tmp_path / "isolated-json-playbooks.sqlite3")
    registry.stage(payload, actor="isolated-test")
    registry.close()
    factory = ExactFactory()
    orchestrator = FakeCentralOrchestrator("healthy")
    with pytest.raises(JsonShadowBoundaryError, match="FINGERPRINT_CHANGED"):
        build_json_readonly_preprod_pilot(
            enabled=True, isolated_root=tmp_path, client_id="company-1",
            request_factory=factory, orchestrator=orchestrator, clock=lambda: NOW,
        )
    assert not factory.calls
    assert not orchestrator.calls


def test_active_pilot_rejected_even_in_isolated_registry(tmp_path):
    prep(tmp_path)
    store = SQLitePlaybookRegistry(tmp_path / "isolated-json-playbooks.sqlite3")
    entry = store.get(PILOT_ID, PILOT_VERSION)
    store.activate(PILOT_ID, PILOT_VERSION, actor="synthetic-owner",
                   expected_fingerprint=entry.document.fingerprint)
    store.close()
    with pytest.raises(JsonShadowBoundaryError, match="MUST_REMAIN_DRAFT"):
        build_json_readonly_preprod_pilot(
            enabled=True, isolated_root=tmp_path, client_id="company-1",
            request_factory=ExactFactory(),
            orchestrator=FakeCentralOrchestrator("healthy"), clock=lambda: NOW,
        )


def test_same_run_cross_company_or_modified_source_blocked(tmp_path):
    prep(tmp_path)
    runner, factory, orchestrator = compose(tmp_path, case="healthy")
    try:
        execute(runner)
        with pytest.raises(JsonShadowBoundaryError, match="CLIENT_SCOPE_UNVERIFIED"):
            runner.run(run_id="isolated-preprod-proof", client_id="other-company",
                       target_id="alert-1",
                       trusted_seed={"client_id": "other-company",
                                     "target_id": "alert-1"})
    finally:
        runner.state.close()
    assert not orchestrator.provider.mutations
