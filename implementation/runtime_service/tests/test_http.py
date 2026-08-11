from __future__ import annotations

import json

from jason_runtime.http import RuntimeHttpApplication


class Ingress:
    def __init__(self, result=None):
        self.requests = []
        self.result = result or {
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "status": "completed",
            "transport_message_id": "msg-1",
            "orchestration_status": "succeeded",
        }

    def handle(self, envelope):
        self.requests.append(dict(envelope))
        return dict(self.result)


def request_body():
    return json.dumps(
        {
            "kind": "conversation.turn",
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "text": "Who is logged into AOT-50282?",
            "signature": "opaque",
        }
    ).encode()


def test_health_does_not_execute_ingress():
    ingress = Ingress()
    response = RuntimeHttpApplication(ingress).dispatch(
        method="GET",
        path="/healthz",
        headers={},
        body=b"",
    )
    assert response.status_code == 200
    assert response.body["status"] == "ok"
    assert response.body["authority"] == "central-orchestrator"
    assert ingress.requests == []


def test_conversation_json_is_passed_unchanged_to_governed_ingress():
    ingress = Ingress()
    body = request_body()
    response = RuntimeHttpApplication(ingress).dispatch(
        method="POST",
        path="/v1/openclaw/teams/conversation",
        headers={"Content-Type": "application/json; charset=utf-8"},
        body=body,
    )
    assert response.status_code == 200
    assert response.body["status"] == "completed"
    assert ingress.requests == [json.loads(body)]


def test_http_layer_cannot_turn_rejection_into_success():
    ingress = Ingress(
        {
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "status": "rejected",
            "error_code": "transport_authentication_failed",
        }
    )
    response = RuntimeHttpApplication(ingress).dispatch(
        method="POST",
        path="/v1/openclaw/teams/conversation",
        headers={"Content-Type": "application/json"},
        body=request_body(),
    )
    assert response.status_code == 401
    assert response.body["status"] == "rejected"


def test_replay_rejection_is_conflict_not_success():
    ingress = Ingress(
        {
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "status": "rejected",
            "error_code": "replay_detected",
        }
    )
    response = RuntimeHttpApplication(ingress).dispatch(
        method="POST",
        path="/v1/openclaw/teams/conversation",
        headers={"Content-Type": "application/json"},
        body=request_body(),
    )
    assert response.status_code == 409


def test_non_json_and_oversized_requests_fail_before_ingress():
    ingress = Ingress()
    app = RuntimeHttpApplication(ingress, max_body_bytes=8)

    oversized = app.dispatch(
        method="POST",
        path="/v1/openclaw/teams/conversation",
        headers={"Content-Type": "application/json"},
        body=b"123456789",
    )
    assert oversized.status_code == 413

    wrong_type = RuntimeHttpApplication(ingress).dispatch(
        method="POST",
        path="/v1/openclaw/teams/conversation",
        headers={"Content-Type": "text/plain"},
        body=b"{}",
    )
    assert wrong_type.status_code == 415
    assert ingress.requests == []


def test_unknown_ingress_status_fails_closed():
    ingress = Ingress({"status": "mystery"})
    response = RuntimeHttpApplication(ingress).dispatch(
        method="POST",
        path="/v1/openclaw/teams/conversation",
        headers={"Content-Type": "application/json"},
        body=request_body(),
    )
    assert response.status_code == 500
