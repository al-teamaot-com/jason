"""Durable, immutable owner approval records for playbook autonomy promotion.

Source metadata may nominate a playbook for autonomous use, but source metadata
is not authority. Standing autonomy requires a separate durable approval record
for the exact playbook version and capability.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4


@dataclass(frozen=True)
class PlaybookAutonomyApproval:
    approval_id: str
    playbook_id: str
    playbook_version: str
    policy_id: str
    allowed_capabilities: tuple[str, ...]
    approved_by: str
    approved_at: datetime
    expires_at: datetime | None = None
    status: str = "approved"
    revoked_by: str | None = None
    revoked_at: datetime | None = None
    revoke_reason: str | None = None

    def __post_init__(self) -> None:
        for name, value in {
            "approval_id": self.approval_id,
            "playbook_id": self.playbook_id,
            "playbook_version": self.playbook_version,
            "policy_id": self.policy_id,
            "approved_by": self.approved_by,
            "status": self.status,
        }.items():
            if not str(value).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.approved_at.tzinfo is None:
            raise ValueError("approved_at must be timezone-aware")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.revoked_at is not None and self.revoked_at.tzinfo is None:
            raise ValueError("revoked_at must be timezone-aware")
        if not self.allowed_capabilities:
            raise ValueError("allowed_capabilities must not be empty")
        if len(set(self.allowed_capabilities)) != len(self.allowed_capabilities):
            raise ValueError("allowed_capabilities must be unique")

    def authorizes(
        self,
        *,
        playbook_id: str,
        playbook_version: str,
        policy_id: str,
        capability: str,
        now: datetime | None = None,
    ) -> bool:
        now = now or datetime.now(timezone.utc)
        return (
            self.status == "approved"
            and self.playbook_id == playbook_id
            and self.playbook_version == playbook_version
            and self.policy_id == policy_id
            and capability in self.allowed_capabilities
            and (self.expires_at is None or now < self.expires_at)
        )


class SQLitePlaybookAutonomyApprovalStore:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS playbook_autonomy_approvals (
        approval_id TEXT PRIMARY KEY,
        playbook_id TEXT NOT NULL,
        playbook_version TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_playbook_autonomy_scope
      ON playbook_autonomy_approvals(playbook_id, playbook_version, policy_id);
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

    def put(self, record: PlaybookAutonomyApproval) -> None:
        payload = self._encode(record)
        with self._connection:
            existing = self._connection.execute(
                "SELECT payload FROM playbook_autonomy_approvals WHERE approval_id=?",
                (record.approval_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload"]) == payload:
                    return
                raise ValueError("playbook autonomy approval id cannot be reused with changed scope")
            self._connection.execute(
                "INSERT INTO playbook_autonomy_approvals VALUES (?,?,?,?,?)",
                (record.approval_id, record.playbook_id, record.playbook_version, record.policy_id, payload),
            )

    def get(self, approval_id: str) -> PlaybookAutonomyApproval | None:
        row = self._connection.execute(
            "SELECT payload FROM playbook_autonomy_approvals WHERE approval_id=?",
            (approval_id,),
        ).fetchone()
        return None if row is None else self._decode(str(row["payload"]))

    def find_approved(
        self,
        *,
        playbook_id: str,
        playbook_version: str,
        policy_id: str,
        capability: str,
        now: datetime | None = None,
    ) -> PlaybookAutonomyApproval | None:
        rows = self._connection.execute(
            "SELECT payload FROM playbook_autonomy_approvals WHERE playbook_id=? AND playbook_version=? AND policy_id=? ORDER BY approval_id",
            (playbook_id, playbook_version, policy_id),
        ).fetchall()
        matches = [
            self._decode(str(row["payload"]))
            for row in rows
        ]
        valid = [
            record for record in matches
            if record.authorizes(
                playbook_id=playbook_id,
                playbook_version=playbook_version,
                policy_id=policy_id,
                capability=capability,
                now=now,
            )
        ]
        if len(valid) > 1:
            raise ValueError("multiple active playbook autonomy approvals match the same scope")
        return valid[0] if valid else None

    def find_scope_approved(
        self,
        *,
        playbook_id: str,
        playbook_version: str,
        policy_id: str,
        required_capabilities: Iterable[str],
        now: datetime | None = None,
    ) -> PlaybookAutonomyApproval | None:
        required = set(required_capabilities)
        if not required:
            return None
        rows = self._connection.execute(
            "SELECT payload FROM playbook_autonomy_approvals WHERE playbook_id=? AND playbook_version=? AND policy_id=? ORDER BY approval_id",
            (playbook_id, playbook_version, policy_id),
        ).fetchall()
        now = now or datetime.now(timezone.utc)
        valid = []
        for row in rows:
            record = self._decode(str(row["payload"]))
            if (
                record.status == "approved"
                and (record.expires_at is None or now < record.expires_at)
                and required.issubset(set(record.allowed_capabilities))
            ):
                valid.append(record)
        if len(valid) > 1:
            raise ValueError("multiple active playbook autonomy approvals match the same scope")
        return valid[0] if valid else None

    def revoke(self, approval_id: str, *, revoked_by: str, reason: str = "owner_revoked") -> PlaybookAutonomyApproval | None:
        current = self.get(approval_id)
        if current is None:
            return None
        if current.status == "revoked":
            return current
        if not revoked_by.strip() or not reason.strip():
            raise ValueError("revocation requires actor and reason")
        changed = PlaybookAutonomyApproval(
            approval_id=current.approval_id,
            playbook_id=current.playbook_id,
            playbook_version=current.playbook_version,
            policy_id=current.policy_id,
            allowed_capabilities=current.allowed_capabilities,
            approved_by=current.approved_by,
            approved_at=current.approved_at,
            expires_at=current.expires_at,
            status="revoked",
            revoked_by=revoked_by,
            revoked_at=datetime.now(timezone.utc),
            revoke_reason=reason,
        )
        payload = self._encode(changed)
        with self._connection:
            self._connection.execute(
                "UPDATE playbook_autonomy_approvals SET payload=? WHERE approval_id=?",
                (payload, approval_id),
            )
        return changed

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def new(
        *,
        playbook_id: str,
        playbook_version: str,
        policy_id: str,
        allowed_capabilities: Iterable[str],
        approved_by: str,
        expires_at: datetime | None = None,
    ) -> PlaybookAutonomyApproval:
        return PlaybookAutonomyApproval(
            approval_id=f"pbauto_{uuid4().hex}",
            playbook_id=playbook_id,
            playbook_version=playbook_version,
            policy_id=policy_id,
            allowed_capabilities=tuple(allowed_capabilities),
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )

    @staticmethod
    def _encode(record: PlaybookAutonomyApproval) -> str:
        payload = asdict(record)
        payload["approved_at"] = record.approved_at.isoformat()
        payload["expires_at"] = record.expires_at.isoformat() if record.expires_at else None
        payload["revoked_at"] = record.revoked_at.isoformat() if record.revoked_at else None
        payload["allowed_capabilities"] = list(record.allowed_capabilities)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decode(payload: str) -> PlaybookAutonomyApproval:
        raw = json.loads(payload)
        raw["approved_at"] = datetime.fromisoformat(raw["approved_at"])
        raw["expires_at"] = datetime.fromisoformat(raw["expires_at"]) if raw.get("expires_at") else None
        raw["revoked_at"] = datetime.fromisoformat(raw["revoked_at"]) if raw.get("revoked_at") else None
        raw["allowed_capabilities"] = tuple(raw["allowed_capabilities"])
        return PlaybookAutonomyApproval(**raw)
