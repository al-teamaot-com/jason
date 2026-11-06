"""Offline-only non-executing governed session simulation.

Runs no shell, vendor, network or endpoint commands. This cannot authorize
runtime execution and must never be routed to an operational transport.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .events import SessionEventLedger
from .grants import GrantScope, SingleUseGrantPrototype
from .lifecycle import SessionLifecycle
from .policy import SessionPolicy, SessionRequest

@dataclass(frozen=True)
class SimulationResult:
    authorized_for_simulation: bool
    reason: str
    executed: bool = False

class OfflineSessionSimulator:
    def __init__(self, *, policy: SessionPolicy, grants: SingleUseGrantPrototype,
                 ledger: SessionEventLedger, lifecycle: SessionLifecycle):
        self.policy, self.grants = policy, grants
        self.ledger, self.lifecycle = ledger, lifecycle

    def propose(self, *, session_id: str, request: SessionRequest, command_text: str, token: str) -> SimulationResult:
        """Only record a proposal and decision. Never send commands anywhere."""
        if type(command_text) is not str or not command_text.strip() or len(command_text) > 8192:
            return SimulationResult(False, 'invalid_command')
        try:
            current = self.lifecycle.inspect(tenant_id=request.tenant_id,
                session_id=session_id, technician_id=request.technician_id)
        except (PermissionError, ValueError, TypeError):
            return SimulationResult(False, 'session_unverified')
        if current.state != 'active' or current.target_id != request.target_id or current.ticket_id != request.ticket_id:
            return SimulationResult(False, 'session_inactive_or_target_mismatch')
        digest = sha256(command_text.encode('utf-8')).hexdigest()
        scope = GrantScope(request.tenant_id, request.client_id, request.target_id,
                           request.technician_id, request.ticket_id, request.transport, digest)
        decision = self.policy.decide(request)
        # Never record raw command text; it may contain credentials or sensitive content.
        self.ledger.append(tenant_id=request.tenant_id,session_id=session_id,
                           kind='command_proposed',evidence={'command_digest':digest})
        if not decision.allowed:
            self.ledger.append(tenant_id=request.tenant_id,session_id=session_id,
                kind='decision_recorded',evidence={'admitted':False,'reason':decision.reason})
            return SimulationResult(False,decision.reason)
        valid_grant = self.grants.consume(token,scope)
        self.ledger.append(tenant_id=request.tenant_id,session_id=session_id,
            kind='decision_recorded',evidence={'admitted':valid_grant,'reason':
                'offline_simulation_only' if valid_grant else 'grant_missing_invalid_expired_or_used'})
        return SimulationResult(valid_grant,
            'offline_simulation_only' if valid_grant else 'grant_missing_invalid_expired_or_used')
