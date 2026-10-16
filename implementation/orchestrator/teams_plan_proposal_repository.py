"""Durable, append-only server-owned proposal source for Teams approval callbacks.

A Teams card carries only an approval identifier; never trust scope or approval
fingerprints supplied by an incoming card interaction.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .approval_plan_scope import ApprovedPlanScope
from .teams_plan_grant_bridge import ServerOwnedPlanProposal


class PlanProposalRepository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS plan_proposals (approval_id TEXT PRIMARY KEY, proposal_json TEXT NOT NULL)')

    def store(self, proposal: ServerOwnedPlanProposal) -> None:
        scope = proposal.scope
        if (not proposal.approval_id or not proposal.plan_fingerprint or
                not proposal.requester_id or not proposal.capability or
                scope.organization_id != proposal.organization_id or
                proposal.capability not in scope.allowed_capabilities or
                (proposal.client_id not in scope.allowed_clients and not
                 (proposal.client_id is None and not scope.allowed_clients))):
            raise ValueError('invalid or out-of-scope server-owned proposal')
        payload = dict(approval_id=proposal.approval_id, organization_id=proposal.organization_id,
            client_id=proposal.client_id, requester_id=proposal.requester_id, capability=proposal.capability,
            plan_fingerprint=proposal.plan_fingerprint,
            scope=dict(plan_id=scope.plan_id, organization_id=scope.organization_id,
                policy_digest=scope.policy_digest, allowed_capabilities=sorted(scope.allowed_capabilities),
                allowed_clients=sorted(scope.allowed_clients), max_risk=scope.max_risk,
                production_allowed=scope.production_allowed, expires_at=scope.expires_at.isoformat()))
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO plan_proposals VALUES (?,?)', (proposal.approval_id, json.dumps(payload, sort_keys=True)))

    def require(self, approval_id: str) -> ServerOwnedPlanProposal:
        if not approval_id:
            raise PermissionError('missing approval identifier')
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT proposal_json FROM plan_proposals WHERE approval_id=?', (approval_id,)).fetchone()
        if row is None:
            raise PermissionError('unknown server-owned approval proposal')
        data = json.loads(row[0])
        s = data['scope']
        scope = ApprovedPlanScope(s['plan_id'], s['organization_id'], s['policy_digest'],
            frozenset(s['allowed_capabilities']), frozenset(s['allowed_clients']),
            s['max_risk'], s['production_allowed'], datetime.fromisoformat(s['expires_at']))
        return ServerOwnedPlanProposal(data['approval_id'], data['organization_id'],
            data['client_id'], data['requester_id'], data['capability'], data['plan_fingerprint'], scope)
