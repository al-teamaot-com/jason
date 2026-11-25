"""Non-executing, fail-closed lifecycle prototype for guided sessions.

Never connects to a device or issues authority. Durable server-side sessions,
identity-bound grants and transport-enforced cancellation remain prerequisites.
"""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from .events import SessionEventLedger

@dataclass(frozen=True)
class SessionState:
    tenant_id: str
    session_id: str
    technician_id: str
    target_id: str
    ticket_id: str
    state: str

class SessionLifecycle:
    def __init__(self, ledger: SessionEventLedger):
        self._ledger = ledger
        self._sessions: dict[tuple[str, str], SessionState] = {}
        self._lock = RLock()

    def open(self, *, tenant_id: str, session_id: str, technician_id: str,
             target_id: str, ticket_id: str) -> SessionState:
        if not all((tenant_id, session_id, technician_id, target_id, ticket_id)):
            raise ValueError('missing authoritative session context')
        key = (tenant_id, session_id)
        with self._lock:
            if key in self._sessions:
                raise ValueError('session exists and cannot be reopened')
            self._ledger.append(tenant_id=tenant_id, session_id=session_id,
                kind='session_opened', evidence={'technician_id': technician_id,
                'target_id': target_id, 'ticket_id': ticket_id})
            state = SessionState(tenant_id, session_id, technician_id, target_id, ticket_id, 'active')
            self._sessions[key] = state
            return state

    def transition(self, *, tenant_id: str, session_id: str, technician_id: str,
                   action: str) -> SessionState:
        from dataclasses import replace
        kinds = {'pause': 'session_paused', 'revoke': 'session_revoked', 'close': 'session_closed'}
        if action not in kinds:
            raise ValueError('unsupported session transition')
        key = (tenant_id, session_id)
        with self._lock:
            state = self._sessions.get(key)
            if state is None or not technician_id or technician_id != state.technician_id:
                raise PermissionError('session identity not bound')
            if state.state in ('revoked', 'closed'):
                raise ValueError('terminal session cannot transition')
            if state.state == 'paused' and action == 'pause':
                raise ValueError('session already paused')
            self._ledger.append(tenant_id=tenant_id, session_id=session_id,
                                kind=kinds[action], evidence={'technician_id': technician_id})
            next_state = replace(state, state={'pause': 'paused', 'revoke': 'revoked', 'close': 'closed'}[action])
            self._sessions[key] = next_state
            return next_state

    def inspect(self, *, tenant_id: str, session_id: str, technician_id: str) -> SessionState:
        with self._lock:
            state = self._sessions.get((tenant_id, session_id))
            if state is None or not technician_id or technician_id != state.technician_id:
                raise PermissionError('session identity not bound')
            return state
