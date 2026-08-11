from __future__ import annotations

from jason_runtime.return_path import (
    OpenClawReturnPathConversationIngress,
    OpenClawReturnPathTransport,
)


class InnerIngress:
    def __init__(self, transport):
        self.transport = transport

    def handle(self, envelope):
        correlation_id = envelope["correlation_id"]
        handoff_id = self.transport.send(
            conversation_id="conversation-1",
            text="AOT-50282 — last logged in user: AOT\\real.user. Source: datto_rmm.",
            correlation_id=correlation_id,
        )
        return {
            "request_id": envelope["request_id"],
            "correlation_id": correlation_id,
            "status": "completed",
            "transport_message_id": handoff_id,
            "orchestration_status": "succeeded",
        }


def test_completed_governed_reply_is_returned_to_openclaw_transport():
    transport = OpenClawReturnPathTransport()
    ingress = OpenClawReturnPathConversationIngress(
        ingress=InnerIngress(transport),
        transport=transport,
    )

    result = ingress.handle({"request_id": "req-1", "correlation_id": "corr-1"})

    assert result["status"] == "completed"
    assert result["delivery_mode"] == "openclaw_return_path"
    assert result["reply"] == {
        "conversation_id": "conversation-1",
        "text": "AOT-50282 — last logged in user: AOT\\real.user. Source: datto_rmm.",
        "handoff_id": "return-path:corr-1",
    }
    assert transport.take("corr-1") is None


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
