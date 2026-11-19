"""Governed ObservePort composition for the offline read-only JSON candidate."""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from autonomous_remediation.json_shadow_integration import JsonShadowBoundaryError
from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from jason_runtime.json_offline_context_preprod import (
    build_offline_context_json_readonly_preprod,
    PLAYBOOK_ID, PLAYBOOK_VERSION,
)
from implementation.runtime_service.tests.test_json_offline_context_shadow import (
    Provider, peer, NOW,
)

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/offline_ticket_context_augmentation.v1.json"


class Factory:
    def __init__(self):
        self.calls = []
    def build_observe(self, **kwargs):
        self.calls.append(dict(kwargs))
        assert kwargs["client_id"] == "777"
        assert kwargs["policy_id"] == "json-migration-readonly-preprod-v1"
        return SimpleNamespace(**kwargs)


class Orchestrator:
    def __init__(self, provider):
        self.provider = provider
        self.calls = []
    def execute(self, request):
        self.calls.append(request)
        evidence = self.provider.execute(request.capability_name, request.arguments)
        return SimpleNamespace(
            status=SimpleNamespace(value=evidence["status"]),
            stage=SimpleNamespace(value="completed"),
            capability_name=request.capability_name,
            provider_id="synthetic-only",
            reason_codes=(), error_code=None,
            correlation_id="isolated-fixture",
            output=evidence["evidence"],
        )


def stage(root, *, payload=None):
    store = SQLitePlaybookRegistry(root / "isolated-json-playbooks.sqlite3")
    draft = store.stage(payload or json.loads(CANDIDATE.read_text()),
                        actor="synthetic-offline-shadow")
    assert draft.state == "draft"
    store.close()


def make(root, provider):
    factory = Factory()
    orchestrator = Orchestrator(provider)
    engine = build_offline_context_json_readonly_preprod(
        enabled=True, isolated_root=root, client_id="777",
        request_factory=factory, orchestrator=orchestrator,
        clock=lambda: NOW,
    )
    return engine, factory, orchestrator


def execute(engine):
    return engine.run(
        run_id="offline-fixture", client_id="777", target_id="123",
        trusted_seed={"client_id": "777", "target_id": "123"},
    )


@pytest.mark.parametrize("peers,classification", [
    ([], "site_status_unknown"),
    ([peer("a", "DESKTOP-A", "Windows Desktop", True),
      peer("b", "DESKTOP-B", "Windows Desktop", True)], "site_likely_up"),
    ([peer("a", "DESKTOP-A", "Windows Desktop", False),
      peer("b", "DESKTOP-B", "Windows Desktop", False)], "site_likely_down"),
    ([peer("a", "LAPTOP-A", "Windows Laptop", True),
      peer("b", "LAPTOP-B", "Windows Laptop", True)], "site_status_unknown"),
])
def test_isolated_existing_governed_port_and_staged_draft(
    tmp_path, peers, classification,
):
    stage(tmp_path)
    provider = Provider(peers)
    engine, factory, orchestrator = make(tmp_path, provider)
    try:
        result = execute(engine)
        assert result.status == "completed_readonly"
        assert result.facts["classification"] == classification
        assert len(factory.calls) == len(orchestrator.calls) == len(provider.calls) == 5
        assert provider.mutations == []
        assert execute(engine) == result
        assert len(provider.calls) == 5
    finally:
        engine.state.close()
    registry = SQLitePlaybookRegistry(
        tmp_path / "isolated-json-playbooks.sqlite3", read_only=True)
    try:
        assert registry.active(PLAYBOOK_ID) is None
        assert registry.get(PLAYBOOK_ID, PLAYBOOK_VERSION).state == "draft"
    finally:
        registry.close()


def test_wrong_fingerprint_rejected_before_any_governed_read(tmp_path):
    altered = json.loads(CANDIDATE.read_text())
    altered["expected_state"]["cannot_infer_site_from_icmp"] = False
    stage(tmp_path, payload=altered)
    provider = Provider()
    with pytest.raises(JsonShadowBoundaryError, match="FINGERPRINT_CHANGED"):
        make(tmp_path, provider)
    assert provider.calls == []


def test_disabled_builder_is_inert(tmp_path):
    path = tmp_path / "absent"
    assert build_offline_context_json_readonly_preprod(
        enabled=False, isolated_root=path,
        client_id="777", request_factory=None,
        orchestrator=None, clock=lambda: NOW,
    ) is None
    assert not path.exists()
