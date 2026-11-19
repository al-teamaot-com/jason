"""Existing runtime-service governed Observe integration for Windows Time."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from autonomous_remediation.json_shadow_integration import JsonShadowBoundaryError
from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from jason_runtime.json_windows_time_preprod import (
    build_windows_time_json_readonly_preprod, PLAYBOOK_ID, PLAYBOOK_VERSION
)
from implementation.runtime_service.tests.test_windows_time_source_shadow import (
    Reads, time_alert, NOW, ALERT, DEVICE,
)

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/windows_time_source.v1.json"
CLIENT = "riggins-company"
SITE = "Riggins Company"


class ServiceIdentityRequestFactory:
    def __init__(self):
        self.requests = []

    def build_observe(self, **kwargs):
        self.requests.append(dict(kwargs))
        return SimpleNamespace(
            capability_name=kwargs["capability_name"],
            arguments=kwargs["arguments"], client_id=kwargs["client_id"],
            policy_id=kwargs["policy_id"],
        )


class MockExistingCentralOrchestrator:
    def __init__(self, original_provider):
        self.provider = original_provider
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        assert request.client_id == CLIENT
        assert request.policy_id == "json-migration-readonly-preprod-v1"
        response = self.provider.execute(request.capability_name, request.arguments)
        return SimpleNamespace(
            status=SimpleNamespace(value=response["status"]),
            stage=SimpleNamespace(value="completed"),
            capability_name=request.capability_name,
            provider_id="synthetic-provider-no-live-access",
            reason_codes=(), error_code=None,
            correlation_id="synthetic-only",
            output=response["evidence"],
        )


def stage(tmp_path, *, payload=None):
    store = SQLitePlaybookRegistry(tmp_path / "isolated-json-playbooks.sqlite3")
    result = store.stage(payload or json.loads(CANDIDATE.read_text()),
                         actor="synthetic-source-only")
    assert result.state == "draft"
    store.close()


def construct(tmp_path, *, provider):
    factory = ServiceIdentityRequestFactory()
    orchestrator = MockExistingCentralOrchestrator(provider)
    runner = build_windows_time_json_readonly_preprod(
        enabled=True, isolated_root=tmp_path, client_id=CLIENT,
        client_site_binding=SITE, request_factory=factory,
        orchestrator=orchestrator, clock=lambda: NOW,
    )
    return runner, factory, orchestrator


def execute(runner):
    return runner.run(
        run_id="isolated-windows-time-1",
        client_id=CLIENT, target_id=ALERT,
        trusted_seed={"client_id": CLIENT, "target_id": ALERT},
    )


@pytest.mark.parametrize("history,online,terminal,classification,calls", [
    ((), True, "classified_current", "CURRENT_TIME_SOURCE_MISMATCH", 3),
    ((time_alert("old-1", age_days=3), time_alert("old-2", age_days=9)),
     True, "classified_recurring", "RECURRING_FAILURE", 3),
    ((), False, "classified_waiting", "WAITING_DEVICE_ACCESS", 2),
])
def test_same_existing_governed_observe_port_preprod_draft(
    tmp_path, history, online, terminal, classification, calls
):
    stage(tmp_path)
    source = Reads([time_alert()], history, online=online)
    runner, factory, orchestrator = construct(tmp_path, provider=source)
    try:
        result = execute(runner)
        assert result.status == "completed_readonly"
        assert result.step_id == terminal
        assert result.facts["classification"] == classification
        assert len(factory.requests) == calls
        assert len(orchestrator.requests) == calls
        assert [r["capability_name"] for r in factory.requests] == [
            capability for capability, _ in source.calls
        ]
        assert all(r["client_id"] == CLIENT for r in factory.requests)
        assert all(r["policy_id"] == "json-migration-readonly-preprod-v1"
                   for r in factory.requests)
        assert execute(runner) == result
        assert len(source.calls) == calls
    finally:
        runner.state.close()
    registry = SQLitePlaybookRegistry(
        tmp_path / "isolated-json-playbooks.sqlite3", read_only=True)
    try:
        assert registry.get(PLAYBOOK_ID, PLAYBOOK_VERSION).state == "draft"
        assert registry.active(PLAYBOOK_ID) is None
        assert registry.generation() == 1
    finally:
        registry.close()


def test_exact_client_site_binding_required_before_any_provider_read(tmp_path):
    stage(tmp_path)
    factory = ServiceIdentityRequestFactory()
    orchestrator = MockExistingCentralOrchestrator(Reads([time_alert()]))
    with pytest.raises(JsonShadowBoundaryError, match="SITE_BINDING_REQUIRED"):
        build_windows_time_json_readonly_preprod(
            enabled=True, isolated_root=tmp_path, client_id=CLIENT,
            client_site_binding="", request_factory=factory,
            orchestrator=orchestrator, clock=lambda: NOW,
        )
    assert factory.requests == []
    assert orchestrator.requests == []


def test_changed_source_fingerprint_fails_before_any_provider_read(tmp_path):
    source = json.loads(CANDIDATE.read_text())
    source["expected_state"]["match_window_days"] = 31
    stage(tmp_path, payload=source)
    factory = ServiceIdentityRequestFactory()
    orchestrator = MockExistingCentralOrchestrator(Reads([time_alert()]))
    with pytest.raises(JsonShadowBoundaryError, match="FINGERPRINT_CHANGED"):
        build_windows_time_json_readonly_preprod(
            enabled=True, isolated_root=tmp_path, client_id=CLIENT,
            client_site_binding=SITE, request_factory=factory,
            orchestrator=orchestrator, clock=lambda: NOW,
        )
    assert factory.requests == []
    assert orchestrator.requests == []


def test_active_other_version_fails_closed(tmp_path):
    stage(tmp_path)
    store = SQLitePlaybookRegistry(tmp_path / "isolated-json-playbooks.sqlite3")
    alternate = json.loads(CANDIDATE.read_text())
    alternate["playbook"]["version"] = "0.1.1-migration.1"
    staged = store.stage(alternate, actor="synthetic-other-version")
    store.activate(
        staged.document.playbook_id, staged.document.version,
        actor="synthetic-only", expected_fingerprint=staged.document.fingerprint,
    )
    store.close()
    with pytest.raises(JsonShadowBoundaryError, match="ACTIVE_VERSION_FORBIDDEN"):
        construct(tmp_path, provider=Reads([time_alert()]))


def test_disabled_builder_creates_no_files_or_calls(tmp_path):
    missing = tmp_path / "absent"
    assert build_windows_time_json_readonly_preprod(
        enabled=False, isolated_root=missing, client_id=CLIENT,
        client_site_binding="", request_factory=None, orchestrator=None,
        clock=lambda: NOW,
    ) is None
    assert not missing.exists()
