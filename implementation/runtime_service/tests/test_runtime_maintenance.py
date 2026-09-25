from __future__ import annotations

from jason_runtime.http import RuntimeHttpApplication
from jason_runtime.server import JasonRuntimeHttpServer


class Ingress:
    def handle(self, envelope):
        return {"status": "completed"}


class Maintenance:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def tick(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic maintenance failure")
        return True


def test_service_actions_noop_when_maintenance_disabled():
    app = RuntimeHttpApplication(Ingress())
    with JasonRuntimeHttpServer(("127.0.0.1", 0), app) as server:
        server.service_actions()


def test_service_actions_runs_maintenance_on_server_thread():
    maintenance = Maintenance()
    app = RuntimeHttpApplication(Ingress(), maintenance=maintenance)
    with JasonRuntimeHttpServer(("127.0.0.1", 0), app) as server:
        server.service_actions()
    assert maintenance.calls == 1


def test_maintenance_failure_cannot_terminate_runtime_server():
    maintenance = Maintenance(fail=True)
    app = RuntimeHttpApplication(Ingress(), maintenance=maintenance)
    with JasonRuntimeHttpServer(("127.0.0.1", 0), app) as server:
        server.service_actions()
        server.service_actions()
    assert maintenance.calls == 2
