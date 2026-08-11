from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class OpenClawReturnPathTransport:
    """Stage a governed Teams reply for return on the authenticated HTTP request.

    OpenClaw remains the Teams transport. Jason does not call Teams, Graph, shell,
    nodes, or an OpenClaw agent directly. The runtime is intentionally single-worker,
    so this small in-memory handoff is consumed synchronously by the ingress wrapper.
    """

    _pending: dict[str, tuple[str, str, str]] = field(default_factory=dict)

    def send(
        self,
        *,
        conversation_id: str,
        text: str,
        correlation_id: str,
    ) -> str:
        conversation_id = conversation_id.strip()
        text = text.strip()
        correlation_id = correlation_id.strip()
        if not conversation_id or not text or not correlation_id:
            raise ValueError("return-path Teams handoff requires conversation, text, and correlation")
        handoff_id = f"return-path:{correlation_id}"
        self._pending[correlation_id] = (conversation_id, text, handoff_id)
        return handoff_id

    def take(self, correlation_id: str) -> Mapping[str, str] | None:
        staged = self._pending.pop(correlation_id, None)
        if staged is None:
            return None
        conversation_id, text, handoff_id = staged
        return {
            "conversation_id": conversation_id,
            "text": text,
            "handoff_id": handoff_id,
        }


@dataclass(frozen=True, slots=True)
class OpenClawReturnPathConversationIngress:
    """Add the governed reply text to the synchronous OpenClaw ingress response."""

    ingress: Any
    transport: OpenClawReturnPathTransport

    def handle(self, envelope: Mapping[str, Any]) -> Mapping[str, Any]:
        result = dict(self.ingress.handle(envelope))
        if result.get("status") != "completed":
            return result

        correlation_id = str(result.get("correlation_id", "")).strip()
        reply = self.transport.take(correlation_id)
        if reply is None:
            return {
                **result,
                "status": "failed",
                "error_code": "return_path_reply_missing",
            }

        result["delivery_mode"] = "openclaw_return_path"
        result["reply"] = dict(reply)
        return result
