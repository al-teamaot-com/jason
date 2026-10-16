"""Immutable in-memory session event ledger for isolated non-executing validation.

No network calls, live transport, credential material, or authority issuance.
Persistence and signed event streaming are required before runtime integration.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import RLock
from typing import Any

EVENT_TYPES = frozenset({
    'session_opened', 'command_proposed', 'decision_recorded',
    'command_started', 'output_observed', 'command_finished',
    'session_paused', 'session_revoked', 'session_closed',
})

@dataclass(frozen=True)
class SessionEvent:
    session_id: str
    tenant_id: str
    sequence: int
    kind: str
    occurred_at: str
    evidence: dict[str, Any]
    previous_digest: str
    digest: str

class SessionEventLedger:
    """Append-only, tenant-bound, ordered events; prototype, NOT durable audit."""
    def __init__(self):
        self._events: dict[tuple[str, str], list[SessionEvent]] = {}
        self._lock = RLock()

    def append(self, *, tenant_id: str, session_id: str, kind: str, evidence: dict[str, Any]) -> SessionEvent:
        if not tenant_id or not session_id or kind not in EVENT_TYPES:
            raise ValueError('invalid session identity or event type')
        if not isinstance(evidence, dict):
            raise ValueError('evidence must be a mapping')
        # Event payloads are JSON-compatible evidence only; reject malformed/nonserializable data.
        with self._lock:
            key = (tenant_id, session_id)
            history = self._events.setdefault(key, [])
            if history and history[-1].kind in ('session_revoked', 'session_closed'):
                raise ValueError('terminal session cannot accept further events')
            if not history and kind != 'session_opened':
                raise ValueError('session must open first')
            if history and kind == 'session_opened':
                raise ValueError('session already opened')
            sequence = len(history) + 1
            previous = history[-1].digest if history else 'GENESIS'
            stamp = datetime.now(timezone.utc).isoformat()
            # Defensive JSON copy ensures callers cannot mutate previously recorded evidence.
            copied = json.loads(json.dumps(evidence, sort_keys=True, allow_nan=False))
            canonical = json.dumps([tenant_id, session_id, sequence, kind, stamp, copied, previous],
                                   sort_keys=True, separators=(',', ':'), allow_nan=False)
            digest = sha256(canonical.encode('utf-8')).hexdigest()
            event = SessionEvent(session_id, tenant_id, sequence, kind, stamp, copied, previous, digest)
            history.append(event)
            return event

    def history(self, *, tenant_id: str, session_id: str) -> tuple[SessionEvent, ...]:
        if not tenant_id or not session_id:
            raise ValueError('tenant and session are required')
        with self._lock:
            return tuple(self._events.get((tenant_id, session_id), ()))
