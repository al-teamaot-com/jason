from datetime import datetime, timedelta, timezone

from jason_runtime.daily_drmm_alert_reconciliation import (
    DailyDrmmAlertReconciliationMaintenance,
    SQLiteDailyAlertReconciliationState,
)


NOW = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
DEVICE = "dev-1"
ALERT = "alert-1"


class Reads:
    def __init__(self, alerts, *, active=(), online=True, engine=True, ticket=None):
        self.alerts = alerts
        self.active = list(active)
        self.online = online
        self.engine = engine
        self.ticket = ticket
        self.resolved = set()
        self.calls = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "management.alert.search":
            return {"status":"succeeded","evidence":{"data":{"alerts":self.alerts}}}
        if capability == "endpoint.device.read":
            return {"status":"succeeded","evidence":{"record":{"online":self.online}}}
        if capability == "endpoint.security.status.read":
            return {"status":"succeeded","evidence":{"data":{"resource_matches":[{"agent_id":"agent-1","datto_av":{"enabled":self.engine,"connected":self.engine,"engine_ready":self.engine,"engine_version":"1","vdf_version":"2"}}]}}}
        if capability == "endpoint.security.detection.search":
            return {"status":"succeeded","evidence":{"data":{"alerts":self.active}}}
        if capability == "endpoint.alert.history.search":
            return {"status":"succeeded","evidence":{"data":{"provider_data":{"alerts":[{"alertUid":uid,"resolved":True} for uid in self.resolved]}}}}
        if capability == "service.ticket.search":
            return {"status":"succeeded","evidence":{"data":{"items":[self.ticket] if self.ticket else []}}}
        if capability == "service.ticket.read":
            return {"status":"succeeded","evidence":{"data":{"items":[{"id":self.ticket["id"],"status":5}]}}}
        raise AssertionError(capability)


class Actions:
    def __init__(self, reads):
        self.reads = reads
        self.calls = []

    def execute(self, scope, capability, arguments):
        self.calls.append((scope.playbook_id, capability, dict(arguments)))
        if capability == "endpoint.alert.resolve":
            self.reads.resolved.add(arguments["alert_uid"])
        return {}


class Audit:
    def record(self, event_type, payload):
        pass


def security_alert(*, age_hours=1, ticket="T1"):
    return {
        "alertUid": ALERT,
        "timestamp": int((NOW - timedelta(hours=age_hours)).timestamp() * 1000),
        "ticketNumber": ticket,
        "alertContext":{"@class":"endpoint_security_threat_ctx","esAlertId":"123","description":"Detected threat from Datto AV"},
        "alertSourceInfo":{"deviceUid":DEVICE,"deviceName":"PC1"},
    }


def build(tmp_path, reads):
    return DailyDrmmAlertReconciliationMaintenance(
        reads=reads,
        actions=Actions(reads),
        state=SQLiteDailyAlertReconciliationState(tmp_path / "state.sqlite3"),
        now=lambda: NOW,
        audit=Audit(),
    )


def test_ignores_open_alerts_older_than_24_hours(tmp_path):
    reads = Reads([security_alert(age_hours=25)])
    svc = build(tmp_path, reads)
    summary = svc.run_once(now=NOW)
    assert summary["open_seen"] == 1
    assert summary["in_window"] == 0
    assert summary["resolved"] == 0


def test_unsupported_alert_is_skipped_without_mutation(tmp_path):
    alert = security_alert()
    alert["alertContext"] = {"@class":"eventlog_ctx","code":"1129"}
    reads = Reads([alert])
    svc = build(tmp_path, reads)
    summary = svc.run_once(now=NOW)
    assert summary["unsupported"] == 1
    assert not svc.actions.calls


def test_active_detection_refuses_resolution(tmp_path):
    reads = Reads([security_alert()], active=[{"alert_id":"still-active"}])
    svc = build(tmp_path, reads)
    summary = svc.run_once(now=NOW)
    assert summary["unhealthy"] == 1
    assert summary["resolved"] == 0
    assert not svc.actions.calls


def test_offline_endpoint_waits_without_resolution(tmp_path):
    reads = Reads([security_alert()], online=False)
    svc = build(tmp_path, reads)
    summary = svc.run_once(now=NOW)
    assert summary["waiting"] == 1
    assert not svc.actions.calls


def test_healthy_security_alert_resolves_and_reconciles_ticket(tmp_path):
    reads = Reads([security_alert()], ticket={"id":101,"status":1})
    svc = build(tmp_path, reads)
    summary = svc.run_once(now=NOW)
    assert summary["resolved"] == 1
    assert summary["ticket_reconciled"] == 1
    capabilities = [cap for _, cap, _ in svc.actions.calls]
    assert capabilities == ["endpoint.alert.resolve","service.ticket.note.create","service.ticket.update"]


def test_tick_runs_only_once_per_24_hours_using_durable_state(tmp_path):
    reads = Reads([])
    state_path = tmp_path / "state.sqlite3"
    first = DailyDrmmAlertReconciliationMaintenance(
        reads=reads, actions=Actions(reads), state=SQLiteDailyAlertReconciliationState(state_path), now=lambda: NOW
    )
    assert first.tick() is True
    second = DailyDrmmAlertReconciliationMaintenance(
        reads=reads, actions=Actions(reads), state=SQLiteDailyAlertReconciliationState(state_path), now=lambda: NOW + timedelta(hours=23)
    )
    assert second.tick() is False
