"""Durable bounded-plan decisions (not a runtime execution authority).

Store decisions only after Microsoft identity and JKD-001 approval have already
been validated. No raw Teams payload may mint grants via this interface.
"""
from __future__ import annotations

import hashlib
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
            db.execute('''CREATE TABLE IF NOT EXISTS revoked_plan_grants (
                plan_id TEXT PRIMARY KEY, revoked_at TEXT NOT NULL, reason TEXT NOT NULL)''')

    def _connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA busy_timeout=15000')
        return db

    @staticmethod
    def _decision_values(scope: ApprovedPlanScope, decision: VerifiedPlanDecision) -> tuple:
        if not (decision.authenticated and decision.authorized and decision.approved):
            raise PermissionError('verified authorized affirmative decision required')
        if not decision.approval_id or not decision.approver_identity_id or not decision.plan_fingerprint:
            raise ValueError('verified decision identifiers are mandatory')
        if decision.decided_at.tzinfo is None:
            raise ValueError('decision time must be timezone-aware')
        require_plan_scope(scope, ProposedPlanStep(scope.plan_id, scope.organization_id,
            scope.policy_digest, next(iter(scope.allowed_capabilities)),
            next(iter(scope.allowed_clients)) if scope.allowed_clients else None, 0, False), now=decision.decided_at)
        data = json.dumps({'plan_id': scope.plan_id, 'organization_id': scope.organization_id,
            'policy_digest': scope.policy_digest, 'allowed_capabilities': sorted(scope.allowed_capabilities),
            'allowed_clients': sorted(scope.allowed_clients), 'max_risk': scope.max_risk,
            'production_allowed': scope.production_allowed, 'expires_at': scope.expires_at.isoformat()}, sort_keys=True)
        return (scope.plan_id, decision.approval_id, decision.approver_identity_id,
                decision.plan_fingerprint, data, decision.decided_at.isoformat())

    def record(self, scope: ApprovedPlanScope, decision: VerifiedPlanDecision) -> None:
        values = self._decision_values(scope, decision)
        with self._connection() as db:
            db.execute('INSERT INTO plan_grants VALUES (?,?,?,?,?,?)', values)

    def require_matching_decision(self, scope: ApprovedPlanScope,
                                  decision: VerifiedPlanDecision) -> None:
        """Verify an identical prior publication without accepting another decision.

        Used only after the authenticated callback and recovery worker race to
        publish the same accepted receipt. The original append-once record API
        stays strict; changed scope, actor, time, fingerprint or revocation fails.
        This method neither changes the ledger nor grants execution authority.
        """
        values = self._decision_values(scope, decision)
        with self._connection() as db:
            row = db.execute(
                'SELECT p.plan_id,p.approval_id,p.approver,p.fingerprint,p.scope_json,p.decided_at,r.revoked_at '
                'FROM plan_grants p LEFT JOIN revoked_plan_grants r ON r.plan_id=p.plan_id '
                'WHERE p.approval_id=?', (decision.approval_id,)).fetchone()
        if row is None or tuple(row[:6]) != values or row[6] is not None:
            raise PermissionError('existing plan decision differs from the verified receipt or is revoked')

    def revoke(self, plan_id: str, *, at: datetime, reason: str) -> None:
        if not plan_id or not reason.strip() or at.tzinfo is None:
            raise ValueError('revocation needs plan, reason, and aware timestamp')
        with self._connection() as db:
            if db.execute('SELECT 1 FROM plan_grants WHERE plan_id=?', (plan_id,)).fetchone() is None:
                raise PermissionError('unknown plan cannot be revoked')
            db.execute('INSERT INTO revoked_plan_grants VALUES (?,?,?)', (plan_id, at.isoformat(), reason))

    def require_grant(self, step: ProposedPlanStep, *, plan_fingerprint: str, now: datetime) -> None:
        with self._connection() as db:
            row = db.execute('SELECT fingerprint, scope_json FROM plan_grants WHERE plan_id=?', (step.plan_id,)).fetchone()
            revoked = db.execute('SELECT 1 FROM revoked_plan_grants WHERE plan_id=?', (step.plan_id,)).fetchone()
        if revoked:
            raise PermissionError('plan authorization revoked')
        if row is None or not plan_fingerprint or row[0] != plan_fingerprint:
            raise PermissionError('missing grant or changed plan fingerprint')
        data = json.loads(row[1])
        scope = ApprovedPlanScope(data['plan_id'], data['organization_id'], data['policy_digest'],
            frozenset(data['allowed_capabilities']), frozenset(data['allowed_clients']),
            data['max_risk'], data['production_allowed'], datetime.fromisoformat(data['expires_at']))
        require_plan_scope(scope, step, now=now)


    def decision_receipt(self, approval_id: str) -> dict | None:
        """Return stored decision facts, not authority from caller-supplied fields."""
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT p.plan_id, p.approval_id, p.approver, p.fingerprint, p.decided_at, r.revoked_at "
                "FROM plan_grants p LEFT JOIN revoked_plan_grants r ON r.plan_id=p.plan_id "
                "WHERE p.approval_id=?", (approval_id,)).fetchone()
        if row is None:
            return None
        return dict(zip(('plan_id','approval_id','approver_identity_id','plan_fingerprint','decided_at','revoked_at'),row))


    def record_authenticated_owner_objective(
        self, scope: ApprovedPlanScope, decision: VerifiedPlanDecision,
        signed_receipt: dict,
    ) -> dict:
        """Atomically store one verified plan grant and its signed Owner proof.

        A trusted authenticated issuer must verify Entra identity/consent and the
        Ed25519 signature before calling this. This is storage, never authority.
        Existing Teams grant recording is unaffected until this opt-in call.
        A crashed response may recover EXACTLY the same stored signed receipt;
        a changed/revoked grant is never republished.
        """
        values = self._decision_values(scope, decision)
        if (not isinstance(signed_receipt, dict)
                or set(signed_receipt) != {'payload', 'signature_base64url'}
                or not isinstance(signed_receipt.get('payload'), dict)
                or signed_receipt['payload'].get('parent_plan_id') != scope.plan_id
                or signed_receipt['payload'].get('parent_approval_id') != decision.approval_id
                or signed_receipt['payload'].get('parent_plan_fingerprint') != decision.plan_fingerprint):
            raise PermissionError('signed objective does not match recorded grant')
        encoded = json.dumps(signed_receipt, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        if len(encoded.encode('utf-8')) > 32768:
            raise ValueError('bounded owner proof maximum length exceeded')
        digest = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
        with self._connection() as db:
            # Serialize duplicate callers before the initial existence check:
            # a competing request must see and read back the original receipt.
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS signed_owner_objective_receipts (
                plan_id TEXT PRIMARY KEY, approval_id TEXT NOT NULL UNIQUE,
                proof_json TEXT NOT NULL, proof_sha256 TEXT NOT NULL,
                decided_at TEXT NOT NULL)''')
            existing = db.execute(
                '''SELECT p.plan_id,p.approval_id,p.approver,p.fingerprint,p.scope_json,
                          p.decided_at,r.revoked_at,o.proof_json,o.proof_sha256
                   FROM plan_grants p
                   LEFT JOIN revoked_plan_grants r ON r.plan_id=p.plan_id
                   LEFT JOIN signed_owner_objective_receipts o ON o.plan_id=p.plan_id
                   WHERE p.plan_id=?''', (scope.plan_id,),
            ).fetchone()
            if existing is not None:
                if (tuple(existing[:6]) != values
                        or existing[6] is not None or existing[7] != encoded
                        or existing[8] != digest):
                    raise PermissionError('existing signed Owner objective differs or was revoked')
                return json.loads(existing[7])
            db.execute('INSERT INTO plan_grants VALUES (?,?,?,?,?,?)', values)
            db.execute(
                'INSERT INTO signed_owner_objective_receipts VALUES (?,?,?,?,?)',
                (scope.plan_id, decision.approval_id, encoded, digest,
                 decision.decided_at.isoformat()),
            )
        return dict(signed_receipt)

    def authenticated_owner_objective_receipt(
        self, *, plan_id: str, approval_id: str,
    ) -> dict | None:
        """Exact durable readback; separate crypto/identity authorization required."""
        if not plan_id or not approval_id:
            raise ValueError('both plan and approval id are required')
        with self._connection() as db:
            available = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='signed_owner_objective_receipts'"
            ).fetchone()
            if available is None:
                return None
            row = db.execute(
                '''SELECT p.approval_id,p.fingerprint,r.revoked_at,
                          o.proof_json,o.proof_sha256
                   FROM plan_grants p
                   JOIN signed_owner_objective_receipts o ON o.plan_id=p.plan_id
                   LEFT JOIN revoked_plan_grants r ON r.plan_id=p.plan_id
                   WHERE p.plan_id=? AND o.approval_id=?''',
                (plan_id, approval_id),
            ).fetchone()
        if row is None:
            return None
        if row[2] is not None:
            raise PermissionError('signed Owner objective grant was revoked')
        if hashlib.sha256(row[3].encode('utf-8')).hexdigest() != row[4]:
            raise PermissionError('signed Owner objective stored proof altered')
        proof = json.loads(row[3])
        if (proof['payload']['parent_approval_id'] != row[0]
                or proof['payload']['parent_plan_fingerprint'] != row[1]):
            raise PermissionError('signed Owner objective stored proof mismatched')
        return proof
