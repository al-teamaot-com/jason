"""SQLite-backed event chain prototype for offline/nonexecuting session tests.

A single SQLite database supports atomic append and replay across process
restarts. It is not a distributed production audit service or a signature system.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from .events import EVENT_TYPES, SessionEvent

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS session_events (
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL CHECK(seq > 0),
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    previous_digest TEXT NOT NULL,
    digest TEXT NOT NULL,
    PRIMARY KEY (tenant_id, session_id, seq)
);
'''

class SqliteSessionEventLedger:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path == ':memory:':
            raise ValueError('durable ledger requires on-disk path')
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA busy_timeout=10000')
        return db

    @staticmethod
    def _row_to_event(row: tuple) -> SessionEvent:
        tenant_id, session_id, sequence, kind, occurred_at, evidence_json, previous, digest = row
        return SessionEvent(session_id,tenant_id,sequence,kind,occurred_at,
                            json.loads(evidence_json),previous,digest)

    def append(self, *, tenant_id: str, session_id: str, kind: str, evidence: dict) -> SessionEvent:
        if any(type(x) is not str or not x.strip() for x in (tenant_id,session_id)) or kind not in EVENT_TYPES:
            raise ValueError('invalid identity or kind')
        if type(evidence) is not dict:
            raise ValueError('invalid evidence')
        canonical_evidence = json.dumps(evidence,sort_keys=True,separators=(',',':'),allow_nan=False)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cursor = db.execute('''SELECT tenant_id,session_id,seq,kind,occurred_at,evidence_json,
                         previous_digest,digest FROM session_events WHERE tenant_id=? AND session_id=?
                         ORDER BY seq DESC LIMIT 1''',(tenant_id,session_id))
            last = cursor.fetchone()
            if last and last[3] in ('session_revoked','session_closed'):
                raise ValueError('terminal session')
            if not last and kind != 'session_opened':
                raise ValueError('session must open first')
            if last and kind == 'session_opened':
                raise ValueError('duplicate opening')
            sequence = 1 if not last else last[2] + 1
            previous = 'GENESIS' if not last else last[7]
            stamp = datetime.now(timezone.utc).isoformat()
            digest = sha256(json.dumps([tenant_id,session_id,sequence,kind,stamp,
                json.loads(canonical_evidence),previous],sort_keys=True,
                separators=(',',':'),allow_nan=False).encode()).hexdigest()
            db.execute('''INSERT INTO session_events VALUES (?,?,?,?,?,?,?,?)''',
                       (tenant_id,session_id,sequence,kind,stamp,canonical_evidence,previous,digest))
        return SessionEvent(session_id,tenant_id,sequence,kind,stamp,
                            json.loads(canonical_evidence),previous,digest)

    def history(self, *, tenant_id: str, session_id: str) -> tuple[SessionEvent,...]:
        if any(type(x) is not str or not x.strip() for x in (tenant_id,session_id)):
            raise ValueError('invalid identity')
        with self._connect() as db:
            rows = db.execute('''SELECT tenant_id,session_id,seq,kind,occurred_at,evidence_json,
                      previous_digest,digest FROM session_events WHERE tenant_id=? AND session_id=?
                      ORDER BY seq''',(tenant_id,session_id)).fetchall()
        return tuple(self._row_to_event(row) for row in rows)

    def verify(self, *, tenant_id: str, session_id: str) -> bool:
        previous='GENESIS'
        for index, event in enumerate(self.history(tenant_id=tenant_id,session_id=session_id),start=1):
            if event.sequence != index or event.previous_digest != previous:
                return False
            check = sha256(json.dumps([tenant_id,session_id,index,event.kind,event.occurred_at,
                event.evidence,previous],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            if check != event.digest:
                return False
            previous=event.digest
        return True
