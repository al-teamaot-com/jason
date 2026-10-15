"""Durable bounded-plan decisions (not a runtime execution authority).

Store decisions only after Microsoft identity and JKD-001 approval have already
been validated. No raw Teams payload may mint grants via this interface.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .approval_plan_scope import ApprovedPlanScope, ProposedPlanStep, require_plan_scope


@dataclass(frozen=True, slots=True)
class VerifiedPlanDecision:
    approval_id: str
    approver_identity_id: str
    authenticated: bool
    authorized: bool
    approved: bool
    plan_fingerprint: str
    decided_at: datetime


class PlanGrantLedger:
    """Append-once SQLite grants; readback always checks explicit scope and fingerprint."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS plan_grants (
                plan_id TEXT PRIMARY KEY, approval_id TEXT NOT NULL UNIQUE,
                approver TEXT NOT NULL, fingerprint TEXT NOT NULL,
                scope_json TEXT NOT NULL, decided_at TEXT NOT NULL)''')

    def _connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA busy_timeout=15000')
        return db

    def record(self, scope: ApprovedPlanScope, decision: VerifiedPlanDecision) -> None:
        if not (decision.authenticated and decision.authorized and decision.approved):
            raise PermissionError('verified authorized affirmative decision required')
        if not decision.approval_id or not decision.approver_identity_id or not decision.plan_fingerprint:
            raise ValueError('verified decision identifiers are mandatory')
        if decision.decided_at.tzinfo is None:
            raise ValueError('decision time must be timezone-aware')
        require_plan_scope(scope, ProposedPlanStep(scope.plan_id, scope.organization_id,
            scope.policy_digest, next(iter(scope.allowed_capabilities)), None, 0, False), now=decision.decided_at)
        data = json.dumps({'plan_id': scope.plan_id, 'organization_id': scope.organization_id,
            'policy_digest': scope.policy_digest, 'allowed_capabilities': sorted(scope.allowed_capabilities),
            'allowed_clients': sorted(scope.allowed_clients), 'max_risk': scope.max_risk,
            'production_allowed': scope.production_allowed, 'expires_at': scope.expires_at.isoformat()}, sort_keys=True)
        with self._connection() as db:
            db.execute('INSERT INTO plan_grants VALUES (?,?,?,?,?,?)', (
                scope.plan_id, decision.approval_id, decision.approver_identity_id,
                decision.plan_fingerprint, data, decision.decided_at.isoformat()))

    def require_grant(self, step: ProposedPlanStep, *, plan_fingerprint: str, now: datetime) -> None:
        with self._connection() as db:
            row = db.execute('SELECT fingerprint, scope_json FROM plan_grants WHERE plan_id=?', (step.plan_id,)).fetchone()
        if row is None or not plan_fingerprint or row[0] != plan_fingerprint:
            raise PermissionError('missing grant or changed plan fingerprint')
        data = json.loads(row[1])
        scope = ApprovedPlanScope(data['plan_id'], data['organization_id'], data['policy_digest'],
            frozenset(data['allowed_capabilities']), frozenset(data['allowed_clients']),
            data['max_risk'], data['production_allowed'], datetime.fromisoformat(data['expires_at']))
        require_plan_scope(scope, step, now=now)
