from __future__ import annotations

from jason_runtime.return_path import (
    OpenClawReturnPathConversationIngress,
    OpenClawReturnPathTransport,
)


class InnerIngress:
    def __init__(self, transport):
        self.transport = transport

    def handle(self, envelope):
        # Production intentionally has two correlation domains: the authenticated
        # OpenClaw envelope carries a transport correlation id, while Jason creates
        # an independent orchestration correlation id after identity/authority
        # binding. They must not be assumed to match.
        orchestration_correlation_id = "corr-jason-orchestration-1"
        handoff_id = self.transport.send(
            conversation_id="conversation-1",
            text="AOT-50282 — last logged in user: AOT\\real.user. Source: datto_rmm.",
            correlation_id=orchestration_correlation_id,
        )
        return {
            "request_id": envelope["request_id"],
            "correlation_id": envelope["correlation_id"],
            "status": "completed",
            "transport_message_id": handoff_id,
            "orchestration_status": "succeeded",
        }


def test_completed_governed_reply_is_returned_by_opaque_handoff_id_when_correlations_differ():
    transport = OpenClawReturnPathTransport()
    ingress = OpenClawReturnPathConversationIngress(
        ingress=InnerIngress(transport),
        transport=transport,
    )

    result = ingress.handle(
        {
            "request_id": "req-1",
            "correlation_id": "openclaw-run-correlation-1",
        }
    )

    assert result["status"] == "completed"
    assert result["correlation_id"] == "openclaw-run-correlation-1"
    assert result["delivery_mode"] == "openclaw_return_path"
    assert result["transport_message_id"] == "return-path:corr-jason-orchestration-1"
    assert result["reply"] == {
        "conversation_id": "conversation-1",
        "text": "AOT-50282 — last logged in user: AOT\\real.user. Source: datto_rmm.",
        "handoff_id": "return-path:corr-jason-orchestration-1",
    }
    assert transport.take("return-path:corr-jason-orchestration-1") is None


def test_completed_result_fails_closed_when_return_path_handoff_is_missing():
    class CompletedWithoutHandoff:
        def handle(self, envelope):
            return {
                "request_id": "req-1",
                "correlation_id": "openclaw-run-correlation-1",
                "status": "completed",
                "transport_message_id": "return-path:missing",
                "orchestration_status": "succeeded",
            }

    transport = OpenClawReturnPathTransport()
    result = OpenClawReturnPathConversationIngress(
        ingress=CompletedWithoutHandoff(),
        transport=transport,
    ).handle({})

    assert result["status"] == "failed"
    assert result["error_code"] == "return_path_reply_missing"
    assert "reply" not in result


def test_non_completed_result_does_not_create_reply_handoff():
    class Rejected:
        def handle(self, envelope):
            return {
                "request_id": "req-1",
                "correlation_id": "corr-1",
                "status": "rejected",
                "error_code": "conversation_unresolved",
            }

    transport = OpenClawReturnPathTransport()
    result = OpenClawReturnPathConversationIngress(
        ingress=Rejected(),
        transport=transport,
    ).handle({})

    assert result["status"] == "rejected"
    assert "reply" not in result
