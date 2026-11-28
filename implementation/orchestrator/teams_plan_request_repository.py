"""Immutable, retained-by-policy orchestration material for plan approvals.

No current execution context or approval flag is persisted. A callback can only
load the exact reviewed plan; each step must obtain fresh JKD-001 authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from .approval_plan_scope import ApprovedPlanScope, ProposedPlanStep, require_plan_scope
from .contracts import ArtifactReference, OrchestrationMode, OrchestrationRequest
from .teams_plan_grant_bridge import ServerOwnedPlanProposal

_RISK = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
_SENSITIVE = re.compile(r'(^|_)(password|secret|token|credential|authorization|api_key|private_key)($|_)', re.I)


def _safe_material(value, *, depth=0):
    if depth > 16:
        raise ValueError('approval request material nesting exceeds limit')
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or _SENSITIVE.search(key):
                raise ValueError('credential-bearing request material cannot be retained for approval')
            _safe_material(child, depth=depth+1)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _safe_material(child, depth=depth+1)
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise ValueError('approval request must contain bounded JSON values')
    elif isinstance(value, str) and (re.search(r'(?i)\bbearer\s+\S+', value) or re.search(r'\bsk-[A-Za-z0-9_-]{16,}', value)):
        raise ValueError('credential-bearing request value cannot be retained for approval')


def request_material(request: OrchestrationRequest) -> dict:
    if not request.data_handling.retention_allowed:
        raise PermissionError('explicit request-material retention policy is required for durable approval')
    if request.risk not in _RISK:
        raise ValueError('unrecognized plan request risk')
    material = asdict(request)
    material.update(authority_allowed=False, approval_present=False,
                    authority_context_id=None, approval_id=None)
    material['orchestration_mode'] = request.orchestration_mode.value
    material['budget']['maximum_estimated_cost'] = str(request.budget.maximum_estimated_cost)
    _safe_material(material['arguments'])
    _safe_material(material['principal_attributes'])
    encoded = json.dumps(material, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(encoded.encode('utf-8')) > 65536:
        raise ValueError('approval request material exceeds retention bound')
    return json.loads(encoded)


def scope_material(scope: ApprovedPlanScope) -> dict:
    return dict(plan_id=scope.plan_id, organization_id=scope.organization_id,
        policy_digest=scope.policy_digest, allowed_capabilities=sorted(scope.allowed_capabilities),
        allowed_clients=sorted(scope.allowed_clients), max_risk=scope.max_risk,
        production_allowed=scope.production_allowed, expires_at=scope.expires_at.isoformat())


def plan_fingerprint(requests: tuple[OrchestrationRequest, ...], scope: ApprovedPlanScope) -> str:
    body = {'requests': [request_material(r) for r in requests], 'scope': scope_material(scope)}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _restore(material: dict) -> OrchestrationRequest:
    data = dict(material)
    data['orchestration_mode'] = OrchestrationMode(data['orchestration_mode'])
    data['data_handling'] = DataHandlingPolicy(**data['data_handling'])
    budget = dict(data['budget'])
    budget['maximum_estimated_cost'] = Decimal(budget['maximum_estimated_cost'])
    data['budget'] = ExecutionBudget(**budget)
    data['policy_ids'] = tuple(data['policy_ids'])
    data['artifact_references'] = tuple(ArtifactReference(**a) for a in data['artifact_references'])
    data.update(authority_allowed=False, approval_present=False, authority_context_id=None, approval_id=None)
    return OrchestrationRequest(**data)


class PlanRequestRepository:
    def __init__(self, path: str | Path, *, current_policy_digest: str | Callable[[], str]):
        self.path = str(path)
        self._policy_digest_source = current_policy_digest
        if not current_policy_digest:
            raise ValueError('current approval policy digest required')
        Path(self.path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS universal_plan_requests ('
                       'approval_id TEXT PRIMARY KEY, material_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS universal_plan_progress ('
                       'approval_id TEXT PRIMARY KEY, state TEXT NOT NULL, progress_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS universal_approval_transport_evidence ('
                       'evidence_hash TEXT PRIMARY KEY, signed_envelope_json TEXT NOT NULL)')
            # Scheduling pointer only. The signed original is stored in the
            # existing transport evidence table, never in a new authority store.
            db.execute('CREATE TABLE IF NOT EXISTS universal_objective_decision_handoffs ('
                       'approval_id TEXT PRIMARY KEY, evidence_hash TEXT NOT NULL, '
                       'state TEXT NOT NULL, updated_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS universal_plan_step_results ('
                       'approval_id TEXT NOT NULL, execution_id TEXT NOT NULL, result_json TEXT NOT NULL, '
                       'PRIMARY KEY(approval_id, execution_id))')
            db.execute('CREATE TABLE IF NOT EXISTS universal_plan_status_deliveries ('
                       'approval_id TEXT NOT NULL, state TEXT NOT NULL, recipient TEXT NOT NULL, '
                       'delivery_status TEXT NOT NULL, receipt TEXT, updated_at TEXT NOT NULL, '
                       'PRIMARY KEY(approval_id,state,recipient))')
        os.chmod(self.path, 0o600)

    @property
    def current_policy_digest(self) -> str:
        source = self._policy_digest_source
        return source() if callable(source) else source

    def store(self, proposal: ServerOwnedPlanProposal, requests: tuple[OrchestrationRequest, ...], *, now: datetime) -> None:
        if not 1 <= len(requests) <= 32:
            raise ValueError('plan requires between one and 32 explicit steps')
        if len({r.execution_id for r in requests}) != len(requests):
            raise ValueError('each plan step requires a unique execution identity')
        if any(r.principal_id != proposal.requester_id or r.organization_id != proposal.organization_id for r in requests):
            raise PermissionError('all plan requests must share the reviewed requester and organization')
        if requests[0].capability_name != proposal.capability or requests[0].client_id != proposal.client_id:
            raise PermissionError('root request does not match plan proposal')
        scope = proposal.scope
        if scope.policy_digest != self.current_policy_digest:
            raise PermissionError('approval policy changed')
        if scope.allowed_capabilities != frozenset(r.capability_name for r in requests):
            raise PermissionError('plan capabilities must exactly match its concrete steps')
        clients = frozenset(r.client_id for r in requests if r.client_id is not None)
        if scope.allowed_clients != clients or (clients and any(r.client_id is None for r in requests)):
            raise PermissionError('plan client scope must exactly match its concrete steps')
        for r in requests:
            require_plan_scope(scope, ProposedPlanStep(scope.plan_id, r.organization_id, scope.policy_digest,
                r.capability_name, r.client_id, _RISK[r.risk], scope.production_allowed), now=now)
        if proposal.plan_fingerprint != plan_fingerprint(requests, scope):
            raise PermissionError('plan fingerprint does not bind reviewed request material')
        payload = json.dumps({'requests': [request_material(r) for r in requests],
                              'scope': scope_material(scope)}, sort_keys=True, separators=(',', ':'))
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO universal_plan_requests VALUES (?,?)', (proposal.approval_id, payload))

    def _payload(self, approval_id: str) -> dict:
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT material_json FROM universal_plan_requests WHERE approval_id=?', (approval_id,)).fetchone()
        if row is None:
            raise PermissionError('no immutable server-owned request for this approval')
        return json.loads(row[0])

    def contains(self, approval_id: str) -> bool:
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT 1 FROM universal_plan_requests WHERE approval_id=?",
                              (approval_id,)).fetchone() is not None

    def require(self, approval_id: str) -> OrchestrationRequest:
        return self.steps(approval_id)[0]

    def steps(self, approval_id: str) -> tuple[OrchestrationRequest, ...]:
        payload = self._payload(approval_id)
        if payload['scope']['policy_digest'] != self.current_policy_digest:
            raise PermissionError('approval policy changed')
        return tuple(_restore(m) for m in payload['requests'])

    def verify_proposal(self, proposal: ServerOwnedPlanProposal) -> None:
        payload = self._payload(proposal.approval_id)
        requests = self.steps(proposal.approval_id)
        if (payload['scope'] != scope_material(proposal.scope)
                or plan_fingerprint(requests, proposal.scope) != proposal.plan_fingerprint):
            raise PermissionError('stored plan material changed after proposal')


    def candidate_ids(self, *, limit: int = 32, prefix: str = "",
                      include_indeterminate: bool = False) -> tuple[str, ...]:
        # Receipt presence is scheduling evidence only. The worker independently
        # validates the receipt, plan fingerprint, identity, grants and policy.
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT r.approval_id FROM universal_plan_requests r "
                "JOIN approval_decision_receipts d ON d.approval_id=r.approval_id "
                "LEFT JOIN universal_plan_progress p ON p.approval_id=r.approval_id "
                "WHERE (p.state IS NULL OR p.state NOT IN ('completed','denied','blocked','indeterminate') "
                "OR (? AND p.state='indeterminate')) AND substr(r.approval_id,1,?)=? "
                "ORDER BY r.rowid LIMIT ?", (include_indeterminate,len(prefix),prefix,max(1,min(32,limit)),)).fetchall()
        return tuple(row[0] for row in rows)

    def objective_submission(self, *, approval_id: str, template_id: str, now: datetime,
                             prefix: str, maximum_active: int, ttl_seconds: int) -> datetime:
        """Stable issuance metadata in the canonical DB; this grants no authority."""
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS universal_objective_submissions ("
                       "approval_id TEXT PRIMARY KEY, template_id TEXT NOT NULL, issued_at TEXT NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT template_id,issued_at FROM universal_objective_submissions WHERE approval_id=?",
                               (approval_id,)).fetchone()
            if prior is not None:
                if prior[0] != template_id:
                    raise PermissionError("OBJECTIVE_SUBMISSION_CHANGED")
                return datetime.fromisoformat(prior[1])
            # Uncertain effects retain their slot. Expired, undecided
            # requests cannot execute and must not permanently block new work.
            if len(self._active_objectives(db, prefix=prefix, now=now,
                                          ttl_seconds=ttl_seconds)) >= maximum_active:
                raise PermissionError("OBJECTIVE_ACTIVE_LIMIT")
            db.execute("INSERT INTO universal_objective_submissions VALUES (?,?,?)",
                       (approval_id,template_id,now.isoformat()))
        return now

    @staticmethod
    def _active_objectives(db, *, prefix, now, ttl_seconds):
        from datetime import timedelta
        rows = db.execute("SELECT x.approval_id,p.state,p.progress_json,r.material_json,s.issued_at,"
            "d.approval_id FROM (SELECT approval_id FROM universal_objective_submissions UNION "
            "SELECT approval_id FROM universal_plan_requests) x "
            "LEFT JOIN universal_plan_progress p ON p.approval_id=x.approval_id "
            "LEFT JOIN universal_plan_requests r ON r.approval_id=x.approval_id "
            "LEFT JOIN universal_objective_submissions s ON s.approval_id=x.approval_id "
            "LEFT JOIN approval_decision_receipts d ON d.approval_id=x.approval_id "
            "WHERE substr(x.approval_id,1,?)=? ORDER BY x.approval_id", (len(prefix),prefix)).fetchall()
        active = []
        for identifier,state,progress,material,issued,decision in rows:
            if state in ("completed","denied"):
                continue
            reason = json.loads(progress).get("reason_code","") if progress else ""
            unstarted = state in (None,"awaiting_approval") or (
                state=="blocked" and isinstance(reason,str) and reason.startswith("approval_delivery_"))
            if decision is None and unstarted:
                expires = (datetime.fromisoformat(json.loads(material)["scope"]["expires_at"])
                           if material else datetime.fromisoformat(issued)+timedelta(seconds=ttl_seconds))
                if now >= expires:
                    continue
            active.append(identifier)
        return tuple(active)

    def objective_submission_ids(self, *, prefix: str, now: datetime, ttl_seconds: int) -> tuple[str, ...]:
        with sqlite3.connect(self.path) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='universal_objective_submissions'").fetchone()
            if not exists:
                return ()
            active = self._active_objectives(db,prefix=prefix,now=now,ttl_seconds=ttl_seconds)
            return tuple(identifier for identifier in active if db.execute(
                "SELECT 1 FROM universal_objective_submissions WHERE approval_id=?",(identifier,)).fetchone())[:2]

    def record_progress(self, approval_id: str, *, state: str, now: datetime,
                        completed_steps: int = 0, current_execution_id: str | None = None,
                        reason_code: str | None = None) -> None:
        if state not in {'awaiting_approval','approved','running','completed','denied','blocked','indeterminate'}:
            raise ValueError('invalid approval progress state')
        if now.tzinfo is None:
            raise ValueError('approval progress time must be timezone-aware')
        payload = json.dumps(dict(state=state,updated_at=now.isoformat(),
            completed_steps=completed_steps,current_execution_id=current_execution_id,
            reason_code=reason_code),sort_keys=True)
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            if state == 'approved':
                prior = db.execute(
                    'SELECT state,progress_json FROM universal_plan_progress WHERE approval_id=?',
                    (approval_id,)).fetchone()
                if prior is not None:
                    # The maintenance worker can finish before the HTTP callback
                    # acknowledges its decision. A late acknowledgement cannot
                    # reset running, completed or uncertain execution to queued.
                    if prior[0] in {'running','completed','denied','indeterminate'}:
                        return
                    if prior[0] == 'blocked':
                        reason = json.loads(prior[1]).get('reason_code')
                        # A partially delivered valid card is still decidable;
                        # execution/security blocks must not be cleared by an ack.
                        if not isinstance(reason, str) or not reason.startswith('approval_delivery_'):
                            return
            db.execute('INSERT INTO universal_plan_progress VALUES (?,?,?) '
                       'ON CONFLICT(approval_id) DO UPDATE SET state=excluded.state,progress_json=excluded.progress_json',
                       (approval_id,state,payload))

    def progress(self, approval_id: str) -> dict | None:
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT progress_json FROM universal_plan_progress WHERE approval_id=?',(approval_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def step_result(self, approval_id: str, execution_id: str) -> dict | None:
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT result_json FROM universal_plan_step_results WHERE approval_id=? AND execution_id=?',
                           (approval_id,execution_id)).fetchone()
        return json.loads(row[0]) if row else None

    def record_step_result(self, approval_id: str, result, *, now: datetime) -> None:
        # Provider output and exception contents are intentionally NOT copied.
        payload=dict(execution_id=result.execution_id,status=result.status.value,stage=result.stage.value,
                     completed_at=now.isoformat())
        encoded=json.dumps(payload,sort_keys=True)
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO universal_plan_step_results VALUES (?,?,?)',
                       (approval_id,result.execution_id,encoded))


    def store_transport_evidence(self, evidence_hash: str, envelope: Mapping) -> None:
        """Retain the signed non-bearer decision evidence for independent restart verification.

        This private store holds the gateway signature and bounded human decision,
        never an OAuth token, credential, document body, or unsigned authority.
        """
        from jason_openclaw.signed_transport import canonical_signed_payload
        _safe_material(envelope)
        if hashlib.sha256(canonical_signed_payload(envelope)).hexdigest() != evidence_hash:
            raise PermissionError('signed approval evidence hash mismatch')
        encoded=json.dumps(dict(envelope),sort_keys=True,separators=(',',':'),allow_nan=False)
        if len(encoded.encode('utf-8'))>65536:
            raise ValueError('signed approval evidence exceeds retention bound')
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT signed_envelope_json FROM universal_approval_transport_evidence WHERE evidence_hash=?',
                           (evidence_hash,)).fetchone()
            if row is not None:
                if row[0]!=encoded:
                    raise PermissionError('immutable signed evidence was changed')
                return
            db.execute('INSERT INTO universal_approval_transport_evidence VALUES (?,?)',(evidence_hash,encoded))

    def retain_objective_handoff(self, approval_id: str, evidence_hash: str,
                                 envelope: Mapping, *, now: datetime) -> None:
        """Persist an original, independently verified callback for handoff.

        This pointer confers no authority. Root admission and the existing
        canonical approval service must still accept the actual signed evidence.
        An existing pointer can never be rebound to different evidence.
        """
        if (now.tzinfo is None or not self.contains(approval_id)
                or not isinstance(envelope.get('interaction'), Mapping)
                or envelope['interaction'].get('approval_id') != approval_id
                or envelope['interaction'].get('decision') != 'approve'):
            raise PermissionError('exact original objective callback required')
        self.store_transport_evidence(evidence_hash, envelope)
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute(
                'SELECT evidence_hash,state FROM universal_objective_decision_handoffs '
                'WHERE approval_id=?', (approval_id,)).fetchone()
            if prior is not None:
                if prior != (evidence_hash, 'pending'):
                    raise PermissionError('objective handoff changed or terminal')
                return
            db.execute('INSERT INTO universal_objective_decision_handoffs VALUES (?,?,?,?)',
                       (approval_id, evidence_hash, 'pending', now.isoformat()))

    def pending_objective_handoffs(self, *, prefix: str, limit: int = 1) -> tuple:
        if not prefix:
            raise ValueError('objective prefix required')
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT approval_id,evidence_hash FROM universal_objective_decision_handoffs "
                "WHERE state='pending' AND substr(approval_id,1,?)=? "
                "ORDER BY updated_at,approval_id LIMIT ?",
                (len(prefix), prefix, max(1, min(32, limit)))).fetchall()
        return tuple((identifier, digest) for identifier, digest in rows)

    def finish_objective_handoff(self, approval_id: str, evidence_hash: str,
                                  *, state: str, now: datetime) -> None:
        # Terminal scheduling outcomes do not grant approval, reset claims,
        # or change the canonical human decision.
        if state not in {'recorded', 'rejected', 'expired'} or now.tzinfo is None:
            raise ValueError('invalid objective handoff outcome')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute(
                'SELECT evidence_hash,state FROM universal_objective_decision_handoffs '
                'WHERE approval_id=?', (approval_id,)).fetchone()
            if prior == (evidence_hash, state):
                return
            if prior != (evidence_hash, 'pending'):
                raise PermissionError('objective handoff identity or state changed')
            db.execute('UPDATE universal_objective_decision_handoffs SET state=?,updated_at=? '
                       'WHERE approval_id=?', (state, now.isoformat(), approval_id))

    def transport_evidence(self, evidence_hash: str) -> dict:
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT signed_envelope_json FROM universal_approval_transport_evidence WHERE evidence_hash=?',
                           (evidence_hash,)).fetchone()
        if row is None:
            raise PermissionError('signed approval evidence is unavailable')
        return json.loads(row[0])


    def terminal_progress_ids(self, *, limit: int = 32, after: str = "") -> tuple[str, ...]:
        with sqlite3.connect(self.path) as db:
            rows=db.execute("SELECT approval_id FROM universal_plan_progress "
                "WHERE state IN ('completed','denied','blocked','indeterminate') AND approval_id>? ORDER BY approval_id LIMIT ?",
                (after,max(1,min(limit,32)))).fetchall()
        return tuple(row[0] for row in rows)

    def claim_status_delivery(self, approval_id: str, state: str, recipient: str, *, now: datetime) -> bool:
        with sqlite3.connect(self.path) as db:
            result=db.execute('INSERT OR IGNORE INTO universal_plan_status_deliveries VALUES (?,?,?,?,?,?)',
                (approval_id,state,recipient,'sending',None,now.isoformat()))
            return result.rowcount==1

    def status_delivery_result(self, approval_id: str, state: str, recipient: str, *, now: datetime,
                               status: str, receipt: str | None = None) -> None:
        if status not in {'sent','failed','indeterminate'}:
            raise ValueError('invalid status delivery result')
        if receipt is not None and (not isinstance(receipt,str) or len(receipt)>512):
            raise ValueError('bounded status delivery receipt required')
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE universal_plan_status_deliveries SET delivery_status=?,receipt=?,updated_at=? '
                       'WHERE approval_id=? AND state=? AND recipient=? AND delivery_status=?',
                       (status,receipt,now.isoformat(),approval_id,state,recipient,'sending'))
