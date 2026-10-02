from datetime import datetime, timedelta, timezone

from jason_runtime.windows_time_source_shadow import (
    SQLiteWindowsTimeSourceShadowState,
    WindowsTimeSourceShadowMaintenance,
    is_time_source_alert,
    parse_sources,
)


NOW = datetime(2026, 10, 1, 13, 30, tzinfo=timezone.utc)
DEVICE = "ea3b591e-15a4-8e4f-a2a6-59a7793ea2c9"
ALERT = "136898e4-f961-4b34-bd54-fd610bda5163"


def time_alert(uid=ALERT, *, source="Free-running System Clock", age_days=0):
    return {
        "alertUid": uid,
        "timestamp": int((NOW - timedelta(days=age_days)).timestamp() * 1000),
        "diagnostics": (
            "\r\nTime source mismatch. Current source '"
            + source
            + "' is not in approved list: ADSRV.Rigginsco.local\r\n"
        ),
        "alertContext": {"@class": "comp_script_ctx", "samples": {"": source}},
        "alertSourceInfo": {
            "deviceUid": DEVICE,
            "deviceName": "CR412LT",
            "siteName": "Riggins Company",
        },
    }


class Reads:
    def __init__(self, current, history=(), *, online=True):
        self.current = list(current)
        self.history = list(history)
        self.online = online
        self.calls = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "management.alert.search":
            return {"status": "succeeded", "evidence": {"data": {"alerts": self.current}}}
        if capability == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": DEVICE,
                        "hostname": "CR412LT",
                        "online": self.online,
                    }
                },
            }
        if capability == "endpoint.alert.history.search":
            return {
                "status": "succeeded",
                "evidence": {"data": {"provider_data": {"alerts": self.history}}},
            }
        raise AssertionError(capability)


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


def build(tmp_path, reads):
    return WindowsTimeSourceShadowMaintenance(
        reads=reads,
        state=SQLiteWindowsTimeSourceShadowState(tmp_path / "time.sqlite3"),
        now=lambda: NOW,
        audit=Audit(),
    )


def test_signature_and_source_parsing():
    alert = time_alert()
    assert is_time_source_alert(alert) is True
    observed, approved = parse_sources(alert)
    assert observed == "Free-running System Clock"
    assert approved == ("ADSRV.Rigginsco.local",)


def test_unrelated_component_alert_is_rejected():
    alert = time_alert()
    alert["diagnostics"] = "Some other component result"
    assert is_time_source_alert(alert) is False


def test_current_mismatch_is_observed_without_mutation(tmp_path):
    svc = build(tmp_path, Reads([time_alert()]))
    summary = svc.run_once(now=NOW)
    assert summary["matched"] == 1
    assert summary["identified"] == 1
    assert summary["mutations"] == 0


def test_cr412lt_history_crosses_recurrence_threshold(tmp_path):
    history = [
        time_alert("old-1", age_days=2),
        time_alert("old-2", source="Local CMOS Clock", age_days=8),
    ]
    svc = build(tmp_path, Reads([time_alert()], history))
    summary = svc.run_once(now=NOW)
    assert summary["recurring"] == 1
    assert summary["mutations"] == 0
    assert svc.audit.events[0][1]["recurrence_count"] == 3
    assert svc.audit.events[0][1]["classification"] == "RECURRING_FAILURE"


def test_history_outside_30_days_does_not_count(tmp_path):
    history = [time_alert("old-1", age_days=31)]
    svc = build(tmp_path, Reads([time_alert()], history))
    summary = svc.run_once(now=NOW)
    assert summary["recurring"] == 0


def test_identity_mismatch_fails_closed(tmp_path):
    reads = Reads([time_alert()])

    def bad_execute(capability, arguments):
        if capability == "management.alert.search":
            return {"status": "succeeded", "evidence": {"data": {"alerts": reads.current}}}
        if capability == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {"record": {"resource_id": DEVICE, "hostname": "WRONG"}},
            }
        if capability == "endpoint.alert.history.search":
            raise AssertionError("history must not run after identity failure")
        raise AssertionError(capability)

    reads.execute = bad_execute
    svc = build(tmp_path, reads)
    summary = svc.run_once(now=NOW)
    assert summary["inconclusive"] == 1
    assert summary["mutations"] == 0


def test_tick_is_bounded_by_15_minute_cadence(tmp_path):
    reads = Reads([])
    state_path = tmp_path / "time.sqlite3"
    first = WindowsTimeSourceShadowMaintenance(
        reads=reads,
        state=SQLiteWindowsTimeSourceShadowState(state_path),
        now=lambda: NOW,
    )
    assert first.tick() is True
    second = WindowsTimeSourceShadowMaintenance(
        reads=reads,
        state=SQLiteWindowsTimeSourceShadowState(state_path),
        now=lambda: NOW + timedelta(minutes=14),
    )
    assert second.tick() is False


def test_offline_endpoint_enters_waiting_without_history_or_mutation(tmp_path):
    reads = Reads([time_alert()], online=False)
    svc = build(tmp_path, reads)
    summary = svc.run_once(now=NOW)
    assert summary["matched"] == 1
    assert summary["identified"] == 1
    assert summary["waiting_device_access"] == 1
    assert summary["recurring"] == 0
    assert summary["mutations"] == 0
    assert svc.audit.events[0][1]["classification"] == "WAITING_DEVICE_ACCESS"
    assert all(call[0] != "endpoint.alert.history.search" for call in reads.calls)
