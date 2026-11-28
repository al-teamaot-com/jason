"""Preproduction, in-process read-only ChatGPT app tool adapter.

This is NOT an MCP server or a deployed ChatGPT app. A trusted server-side
adapter supplies the authenticated technician context and a confidential
server-side session credential lookup. The model never supplies or receives
the session credential. Synthetic-only exchange evidence is supported.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from session_gate import Denied, SessionGate
from synthetic_probe import ProbeResponse

@dataclass(frozen=True)
class SafeSessionStatus:
    session_id: str
    device_uid: str
    sequence: int
    result: str
    evidence_sha256: str
    provenance: str = "synthetic-test-only"
    screenshot_analyzed: bool = False
    live_transport_connected: bool = False
    inference_billing: str = "none"

class ChatGPTSessionTool:
    """Read-only adapter contract for a future authenticated ChatGPT MCP tool.

    All authorization checks occur server-side on every call.
    """
    def __init__(
        self, *,
        gate: SessionGate,
        credential_lookup: Callable[[str], str | None],
        synthetic_receipt_lookup: Callable[[str], ProbeResponse | None],
    ):
        self._gate = gate
        self._credential_lookup = credential_lookup
        self._receipt_lookup = synthetic_receipt_lookup

    def read_synthetic_status(
        self, *, authenticated_technician: object,
        session_id: str, device_uid: str,
    ) -> dict:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
            raise Denied("invalid session reference")
        if not isinstance(device_uid, str):
            raise Denied("invalid device reference")
        # Server-owned lookups only. No browser or model-provided token.
        token = self._credential_lookup(session_id)
        if not isinstance(token, str) or not token:
            raise Denied("trusted session credential unavailable")
        self._gate.authorize_read(
            trusted_context=authenticated_technician,
            session_id=session_id,
            token=token,
            device_uid=device_uid,
        )
        receipt = self._receipt_lookup(session_id)
        if not isinstance(receipt, ProbeResponse) or receipt.session_id != session_id:
            raise Denied("synthetic evidence unavailable")
        if receipt.observation != "Synthetic test acknowledged; no screen was analyzed.":
            raise Denied("unsupported evidence type")
        result = SafeSessionStatus(
            session_id=session_id, device_uid=device_uid,
            sequence=receipt.sequence, result=receipt.observation,
            evidence_sha256=receipt.evidence_sha256,
        )
        return asdict(result)
