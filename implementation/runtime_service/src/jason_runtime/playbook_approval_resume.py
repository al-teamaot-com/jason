"""Durable per-run playbook approval proposals and exactly-once resume state.

This is shared runtime infrastructure. It does not grant authority; it persists the
exact proposal that an external approval must match before the Central Orchestrator
may be asked to execute.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping


def _canon(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class PlaybookActionProposal:
    proposal_id: str
    playbook_id: str
    playbook_version: str
    policy_id: str
    ticket_id: int
    client_id: str
    target_id: str
    capability: str
    action_id: str
    arguments: Mapping[str, Any]
    disruption_classification: str
    expected_verification: str
    created_at: datetime
    expires_at: datetime

    def validate(self) -> None:
        required = (
            self.proposal_id,
            self.playbook_id,
            self.playbook_version,
            self.policy_id,
            self.client_id,
            self.target_id,
            self.capability,
            self.action_id,
            self.disruption_classification,
            self.expected_verification,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("playbook action proposal fields must be non-empty")
        if int(self.ticket_id) <= 0:
            raise ValueError("ticket_id must be positive")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("proposal timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("proposal expiration must be after creation")

    @property
    def fingerprint(self) -> str:
        self.validate()
        material = {
            "playbook_id": self.playbook_id,
            "playbook_version": self.playbook_version,
            "policy_id": self.policy_id,
            "ticket_id": int(self.ticket_id),
            "client_id": self.client_id,
            "target_id": self.target_id,
            "capability": self.capability,
            "action_id": self.action_id,
            "arguments": dict(self.arguments),
            "disruption_classification": self.disruption_classification,
            "expected_verification": self.expected_verification,
        }
        return hashlib.sha256(_canon(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProposalState:
    proposal: PlaybookActionProposal
    status: str
    approval_id: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    consumed_at: datetime | None = None
    execution_id: str | None = None
    correlation_id: str | None = None


class SQLitePlaybookActionProposalStore:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS playbook_action_proposals (
        proposal_id TEXT PRIMARY KEY,
        payload TEXT NOT NULL
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(self._SCHEMA)
        os.chmod(self.path, 0o600)

    def close(self) -> None:
        self._connection.close()

    def create(self, proposal: PlaybookActionProposal) -> ProposalState:
        proposal.validate()
        state = ProposalState(proposal=proposal, status="pending")
        payload = self._encode(state)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO playbook_action_proposals(proposal_id,payload) VALUES(?,?)",
                    (proposal.proposal_id, payload),
                )
        except sqlite3.IntegrityError as exc:
            existing = self.get(proposal.proposal_id)
            if existing and existing.proposal.fingerprint == proposal.fingerprint:
                return existing
            raise ValueError("proposal_id cannot be reused with changed scope") from exc
        return state

    def get(self, proposal_id: str) -> ProposalState | None:
        row = self._connection.execute(
            "SELECT payload FROM playbook_action_proposals WHERE proposal_id=?",
            (proposal_id,),
        ).fetchone()
        return None if row is None else self._decode(str(row["payload"]))

    def list_all(self) -> tuple[ProposalState, ...]:
        rows = self._connection.execute(
            "SELECT payload FROM playbook_action_proposals ORDER BY proposal_id"
        ).fetchall()
        return tuple(self._decode(str(row["payload"])) for row in rows)

    def find_for_ticket(self, ticket_id: int) -> ProposalState | None:
        matches = [
            item for item in self.list_all()
            if item.proposal.ticket_id == int(ticket_id)
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: item.proposal.created_at)
        return matches[-1]

    def find_pending_for_ticket(self, ticket_id: int) -> ProposalState | None:
        pending = [
            item for item in self.list_all()
            if item.proposal.ticket_id == int(ticket_id) and item.status == "pending"
        ]
        if len(pending) > 1:
            raise RuntimeError("multiple pending proposals exist for one ticket")
        return pending[0] if pending else None

    def decide(
        self,
        *,
        proposal_id: str,
        proposal_fingerprint: str,
        approval_id: str,
        decision: str,
        decided_by: str,
        decided_at: datetime,
    ) -> ProposalState:
        state = self._require(proposal_id)
        if state.status != "pending":
            raise ValueError("proposal is no longer pending")
        if decided_at.tzinfo is None:
            raise ValueError("decision timestamp must be timezone-aware")
        if state.proposal.fingerprint != str(proposal_fingerprint):
            raise PermissionError("approval does not match exact proposal fingerprint")
        if decided_at >= state.proposal.expires_at:
            return self._replace(state, status="expired", approval_id=approval_id,
                                 decided_by=decided_by, decided_at=decided_at)
        normalized = str(decision).strip().casefold()
        if normalized not in {"approved", "denied", "changes_requested"}:
            raise ValueError("unsupported proposal decision")
        return self._replace(
            state,
            status=normalized,
            approval_id=str(approval_id),
            decided_by=str(decided_by),
            decided_at=decided_at,
        )

    def consume_approved(
        self,
        *,
        proposal_id: str,
        proposal_fingerprint: str,
        execution_id: str,
        correlation_id: str,
        now: datetime | None = None,
    ) -> ProposalState:
        state = self._require(proposal_id)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("consume timestamp must be timezone-aware")
        if state.proposal.fingerprint != str(proposal_fingerprint):
            raise PermissionError("resume proposal fingerprint changed")
        if state.status == "consumed":
            raise ValueError("approved proposal has already been consumed")
        if state.status != "approved":
            raise PermissionError("only an approved proposal may be consumed")
        if current >= state.proposal.expires_at:
            self._replace(state, status="expired")
            raise PermissionError("proposal approval expired before execution")
        if not str(execution_id).strip() or not str(correlation_id).strip():
            raise ValueError("execution and correlation identifiers are required")
        return self._replace(
            state,
            status="consumed",
            consumed_at=current,
            execution_id=str(execution_id),
            correlation_id=str(correlation_id),
        )

    def _require(self, proposal_id: str) -> ProposalState:
        state = self.get(proposal_id)
        if state is None:
            raise LookupError("playbook action proposal not found")
        return state

    def _replace(self, state: ProposalState, **changes: Any) -> ProposalState:
        data = {
            "proposal": state.proposal,
            "status": state.status,
            "approval_id": state.approval_id,
            "decided_by": state.decided_by,
            "decided_at": state.decided_at,
            "consumed_at": state.consumed_at,
            "execution_id": state.execution_id,
            "correlation_id": state.correlation_id,
        }
        data.update(changes)
        updated = ProposalState(**data)
        with self._connection:
            self._connection.execute(
                "UPDATE playbook_action_proposals SET payload=? WHERE proposal_id=?",
                (self._encode(updated), updated.proposal.proposal_id),
            )
        return updated

    @staticmethod
    def _encode(state: ProposalState) -> str:
        proposal = asdict(state.proposal)
        proposal["arguments"] = dict(state.proposal.arguments)
        proposal["created_at"] = state.proposal.created_at.isoformat()
        proposal["expires_at"] = state.proposal.expires_at.isoformat()
        body = {
            "proposal": proposal,
            "status": state.status,
            "approval_id": state.approval_id,
            "decided_by": state.decided_by,
            "decided_at": state.decided_at.isoformat() if state.decided_at else None,
            "consumed_at": state.consumed_at.isoformat() if state.consumed_at else None,
            "execution_id": state.execution_id,
            "correlation_id": state.correlation_id,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decode(payload: str) -> ProposalState:
        body = json.loads(payload)
        raw = dict(body["proposal"])
        raw["created_at"] = datetime.fromisoformat(raw["created_at"])
        raw["expires_at"] = datetime.fromisoformat(raw["expires_at"])
        proposal = PlaybookActionProposal(**raw)
        return ProposalState(
            proposal=proposal,
            status=str(body["status"]),
            approval_id=body.get("approval_id"),
            decided_by=body.get("decided_by"),
            decided_at=datetime.fromisoformat(body["decided_at"]) if body.get("decided_at") else None,
            consumed_at=datetime.fromisoformat(body["consumed_at"]) if body.get("consumed_at") else None,
            execution_id=body.get("execution_id"),
            correlation_id=body.get("correlation_id"),
        )
