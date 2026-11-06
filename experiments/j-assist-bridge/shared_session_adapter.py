"""Preproduction compatibility adapter to Jason shared-session foundation.

No production registration, screen ingestion, or endpoint control. Session
authority remains the source of truth; the shared lifecycle records durable
metadata events. Do not promote before lifecycle durability/recovery acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass

from implementation.shared_sessions.lifecycle import SessionLifecycle
from session_gate import Denied, SessionGate, SessionReceipt, VerifiedTechnician


@dataclass(frozen=True)
class SharedSessionStart:
    receipt: SessionReceipt
    session_credential: str


class SharedSessionAdapter:
    """Couple exact session authority with the provider-neutral lifecycle."""

    def __init__(self, *, gate: SessionGate, lifecycle: SessionLifecycle):
        self._gate = gate
        self._lifecycle = lifecycle

    def start(
        self, *, technician: VerifiedTechnician, device_uid: str,
        ticket_id: str, consent: bool,
    ) -> SharedSessionStart:
        if not isinstance(technician, VerifiedTechnician):
            raise Denied("trusted technician required")
        if not isinstance(ticket_id, str) or not ticket_id.strip():
            raise Denied("linked ticket required")
        receipt, credential = self._gate.start(
            trusted_context=technician,
            device_uid=device_uid,
            consent=consent,
        )
        try:
            self._lifecycle.open(
                tenant_id=technician.tenant_id,
                session_id=receipt.session_id,
                technician_id=technician.subject,
                target_id=device_uid,
                ticket_id=ticket_id,
            )
        except Exception:
            self._gate.stop(
                trusted_context=technician,
                session_id=receipt.session_id,
                token=credential,
                device_uid=device_uid,
            )
            raise
        return SharedSessionStart(receipt, credential)

    def inspect(
        self, *, technician: VerifiedTechnician, session_id: str,
        credential: str, device_uid: str,
    ) -> dict:
        self._gate.authorize_read(
            trusted_context=technician, session_id=session_id,
            token=credential, device_uid=device_uid,
        )
        state = self._lifecycle.inspect(
            tenant_id=technician.tenant_id,
            session_id=session_id, technician_id=technician.subject,
        )
        if state.target_id != device_uid or state.state != "active":
            raise Denied("shared session is not active for this target")
        return {
            "session_id": session_id,
            "device_uid": device_uid,
            "state": state.state,
            "screen_analyzed": False,
            "transport": "preproduction-synthetic-only",
        }

    def close(
        self, *, technician: VerifiedTechnician, session_id: str,
        credential: str, device_uid: str,
    ) -> None:
        self.inspect(
            technician=technician, session_id=session_id,
            credential=credential, device_uid=device_uid,
        )
        self._lifecycle.transition(
            tenant_id=technician.tenant_id,
            session_id=session_id,
            technician_id=technician.subject,
            action="close",
        )
        self._gate.stop(
            trusted_context=technician, session_id=session_id,
            token=credential, device_uid=device_uid,
        )
