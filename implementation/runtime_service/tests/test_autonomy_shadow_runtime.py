from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from jason_runtime.autonomy_shadow_runtime import (
    GovernedAutonomyReadPort,
    ShadowAutonomyMaintenance,
    SQLiteShadowAssessmentStore,
)


class Factory:
    def __init__(self):
        self.calls = []

    def build_observe(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(capability_name=kwargs["capability_name"])


class Orchestrator:
    def __init__(self, output=None):
        self.requests = []
        self.output = output or {"items": [{"id": 1}]}

    def execute(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            status=SimpleNamespace(value="succeeded"),
            stage=SimpleNamespace(value="completed"),
            capability_name=request.capability_name,
            provider_id="autotask",
            reason_codes=("capability_completed",),
            error_code=None,
            correlation_id="corr-1",
            output=self.output,
        )


def test_governed_read_port_uses_workload_request_factory_and_orchestrator():
    factory = Factory()
    orchestrator = Orchestrator()
    port = GovernedAutonomyReadPort(
        request_factory=factory,
        orchestrator=orchestrator,
    )
    result = port.execute("service.ticket.search", {"status": "New"})
    assert result["status"] == "succeeded"
    assert result["provider"] == "autotask"
    assert result["evidence"]["items"] == [{"id": 1}]
    assert factory.calls[0]["capability_name"] == "service.ticket.search"
    assert len(orchestrator.requests) == 1


@dataclass(frozen=True)
class Item:
    resource_id: str
    source_queue: str = "Jason"
    priority_score: int = 10
    owned_by_jason: bool = True
    playbook_id: str = "shadow"
    match_state: str = "candidate_investigation"
    standing_authority_active: bool = False
    reasons: tuple[str, ...] = ("shadow",)


class Assessor:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def assess(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("ticket body should never be persisted: SECRET")
        return SimpleNamespace(
            candidate_count=3,
            configured_active_limit=2,
            selected_for_attention=(Item("1"), Item("2")),
        )


def test_shadow_maintenance_runs_startup_then_respects_interval(tmp_path):
    now = [100.0]
    store = SQLiteShadowAssessmentStore(tmp_path / "shadow.sqlite3")
    assessor = Assessor()
    maintenance = ShadowAutonomyMaintenance(
        assessor=assessor,
        store=store,
        interval_seconds=600,
        failure_retry_seconds=60,
        monotonic=lambda: now[0],
    )
    assert maintenance.tick() is True
    assert assessor.calls == 1
    assert maintenance.tick() is False
    now[0] += 600
    assert maintenance.tick() is True
    assert assessor.calls == 2
    latest = store.latest()
    assert latest["status"] == "succeeded"
    assert latest["payload"]["candidate_count"] == 3
    assert len(latest["payload"]["selected_for_attention"]) == 2
    store.close()


def test_explicit_reconcile_wakes_before_staleness_deadline(tmp_path):
    now = [100.0]
    store = SQLiteShadowAssessmentStore(tmp_path / "shadow.sqlite3")
    assessor = Assessor()
    maintenance = ShadowAutonomyMaintenance(
        assessor=assessor,
        store=store,
        interval_seconds=600,
        failure_retry_seconds=60,
        monotonic=lambda: now[0],
    )
    maintenance.tick()
    maintenance.request_reconcile("ticket_changed")
    assert maintenance.tick() is True
    latest = store.latest()
    assert "ticket_changed" in latest["payload"]["reconcile_reasons"]
    store.close()


def test_shadow_failure_is_bounded_and_runtime_safe(tmp_path):
    now = [100.0]
    store = SQLiteShadowAssessmentStore(tmp_path / "shadow.sqlite3")
    maintenance = ShadowAutonomyMaintenance(
        assessor=Assessor(fail=True),
        store=store,
        interval_seconds=600,
        failure_retry_seconds=60,
        monotonic=lambda: now[0],
    )
    assert maintenance.tick() is True
    latest = store.latest()
    assert latest["status"] == "failed"
    assert latest["payload"]["error_type"] == "RuntimeError"
    assert len(latest["payload"]["error_message"]) <= 500
    store.close()
