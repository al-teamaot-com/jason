from __future__ import annotations

from jason_openclaw import OpenClawConnector


class Dispatcher:
    def dispatch(self, request):
        if request.capability != "autotask.ticket.get":
            raise KeyError(request.capability)
        return {"ticket_id": request.arguments["ticket_id"], "source": "autotask"}


class Authority:
    def __init__(self, decision="allowed"):
        self.decision = decision

    def evaluate(self, request):
        return self.decision


class Audit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


class Replay:
    def __init__(self):
        self.claimed = set()

    def claim(self, request_id):
        if request_id in self.claimed:
            return False
        self.claimed.add(request_id)
        return True


def payload(capability="autotask.ticket.get"):
    return {
        "request_id": "req-1",
        "correlation_id": "corr-1",
        "capability": capability,
        "requested_mode": "observe",
        "arguments": {"ticket_id": "12445279"},
        "principal": {
            "principal_id": "person-al",
            "channel": "teams",
            "external_user_id": "openclaw-user-1",
            "organization_id": "aot",
            "client_id": "client-jbf",
        },
    }


def test_dispatches_registered_capability_without_ai_provider():
    audit = Audit()
    connector = OpenClawConnector(Dispatcher(), Authority(), audit, Replay())

    result = connector.handle(payload())

    assert result["status"] == "completed"
    assert result["result"]["ticket_id"] == "12445279"
    assert [event[0] for event in audit.events] == [
        "openclaw.request_received",
        "openclaw.capability_completed",
    ]


def test_denies_request_before_dispatch():
    connector = OpenClawConnector(Dispatcher(), Authority("denied"), Audit(), Replay())

    result = connector.handle(payload())

    assert result["status"] == "denied"
    assert result["error_code"] == "authority_denied"


def test_rejects_arbitrary_http_target():
    connector = OpenClawConnector(Dispatcher(), Authority(), Audit(), Replay())

    result = connector.handle(payload("https://example.invalid/api"))

    assert result["status"] == "rejected"
    assert result["error_code"] == "invalid_contract"


def test_rejects_replayed_request_id():
    replay = Replay()
    connector = OpenClawConnector(Dispatcher(), Authority(), Audit(), replay)

    assert connector.handle(payload())["status"] == "completed"
    assert connector.handle(payload())["error_code"] == "replay_detected"


def test_unknown_capability_fails_closed():
    connector = OpenClawConnector(Dispatcher(), Authority(), Audit(), Replay())

    result = connector.handle(payload("autotask.ticket.delete"))

    assert result["status"] == "rejected"
    assert result["error_code"] == "capability_not_registered"
