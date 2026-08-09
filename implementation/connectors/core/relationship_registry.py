from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from .relationships import CanonicalRelationship, RelationshipState, ResourceRef, VerificationState


class CanonicalRelationshipRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RelationshipLifecycleEvent:
    event_id: int
    relationship_id: str
    organization_id: str
    previous_state: RelationshipState | None
    new_state: RelationshipState
    changed_by: str
    reason: str
    occurred_at: datetime


_ALLOWED_TRANSITIONS: dict[RelationshipState, frozenset[RelationshipState]] = {
    RelationshipState.CANDIDATE: frozenset({RelationshipState.ACTIVE, RelationshipState.REJECTED}) if hasattr(RelationshipState, "REJECTED") else frozenset({RelationshipState.ACTIVE, RelationshipState.RETIRED}),
    RelationshipState.ACTIVE: frozenset({
        RelationshipState.SUSPENDED,
        RelationshipState.EXPIRED,
        RelationshipState.REVOKED,
        RelationshipState.SUPERSEDED,
        RelationshipState.RETIRED,
    }),
    RelationshipState.SUSPENDED: frozenset({
        RelationshipState.ACTIVE,
        RelationshipState.EXPIRED,
        RelationshipState.REVOKED,
        RelationshipState.RETIRED,
    }),
    RelationshipState.EXPIRED: frozenset({RelationshipState.RETIRED}),
    RelationshipState.REVOKED: frozenset({RelationshipState.RETIRED}),
    RelationshipState.SUPERSEDED: frozenset({RelationshipState.RETIRED}),
    RelationshipState.RETIRED: frozenset(),
}


def _resource(payload: dict[str, object]) -> ResourceRef:
    return ResourceRef(**payload)


def _relationship_from_payload(payload: str) -> CanonicalRelationship:
    data = json.loads(payload)
    data["source"] = _resource(data["source"])
    data["target"] = _resource(data["target"])
    data["state"] = RelationshipState(data["state"])
    data["verification"] = VerificationState(data["verification"])
    data["provenance"] = tuple(data["provenance"])
    data["effective_at"] = datetime.fromisoformat(data["effective_at"])
    data["expires_at"] = None if data.get("expires_at") is None else datetime.fromisoformat(data["expires_at"])
    return CanonicalRelationship(**data)


def _encode_relationship(relationship: CanonicalRelationship) -> str:
    payload = asdict(relationship)
    payload["state"] = relationship.state.value
    payload["verification"] = relationship.verification.value
    payload["effective_at"] = relationship.effective_at.astimezone(timezone.utc).isoformat()
    payload["expires_at"] = None if relationship.expires_at is None else relationship.expires_at.astimezone(timezone.utc).isoformat()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class SQLiteCanonicalRelationshipRegistry:
    """Tenant-isolated durable registry for canonical relationships and lifecycle evidence.

    Relationship payloads are append-once by relationship id. Lifecycle changes are
    recorded as separate immutable events and never rewrite provenance.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS canonical_relationships (
                    relationship_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    current_state TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_canonical_relationships_org
                    ON canonical_relationships(organization_id, current_state);
                CREATE TABLE IF NOT EXISTS canonical_relationship_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    relationship_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    previous_state TEXT,
                    new_state TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY(relationship_id) REFERENCES canonical_relationships(relationship_id)
                );
                CREATE INDEX IF NOT EXISTS ix_canonical_relationship_events_scope
                    ON canonical_relationship_events(organization_id, relationship_id, event_id);
                """
            )

    def register(self, relationship: CanonicalRelationship, *, changed_by: str, reason: str) -> None:
        if not changed_by.strip() or not reason.strip():
            raise CanonicalRelationshipRegistryError("registry actor and reason are required")
        organization_id = relationship.source.organization_id
        if relationship.target.organization_id != organization_id:
            raise PermissionError("canonical relationship organization mismatch")
        payload = _encode_relationship(relationship)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT organization_id,payload,current_state FROM canonical_relationships WHERE relationship_id=?",
                (relationship.relationship_id,),
            ).fetchone()
            if existing is not None:
                if existing["organization_id"] != organization_id:
                    raise PermissionError("relationship id already exists in another organization")
                if existing["payload"] == payload and existing["current_state"] == relationship.state.value:
                    connection.rollback()
                    return
                raise CanonicalRelationshipRegistryError("conflicting canonical relationship id reuse is not permitted")
            connection.execute(
                "INSERT INTO canonical_relationships(relationship_id,organization_id,payload,current_state) VALUES (?,?,?,?)",
                (relationship.relationship_id, organization_id, payload, relationship.state.value),
            )
            connection.execute(
                "INSERT INTO canonical_relationship_events(relationship_id,organization_id,previous_state,new_state,changed_by,reason,occurred_at) VALUES (?,?,?,?,?,?,?)",
                (
                    relationship.relationship_id,
                    organization_id,
                    None,
                    relationship.state.value,
                    changed_by,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def get(self, relationship_id: str, *, organization_id: str) -> CanonicalRelationship | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT organization_id,payload,current_state FROM canonical_relationships WHERE relationship_id=?",
                (relationship_id,),
            ).fetchone()
        if row is None:
            return None
        if row["organization_id"] != organization_id:
            raise PermissionError("canonical relationship organization mismatch")
        relationship = _relationship_from_payload(row["payload"])
        if relationship.state.value == row["current_state"]:
            return relationship
        return CanonicalRelationship(
            relationship_id=relationship.relationship_id,
            relationship_type=relationship.relationship_type,
            source=relationship.source,
            target=relationship.target,
            state=RelationshipState(row["current_state"]),
            verification=relationship.verification,
            confidence=relationship.confidence,
            established_by=relationship.established_by,
            provenance=relationship.provenance,
            effective_at=relationship.effective_at,
            expires_at=relationship.expires_at,
        )

    def transition(
        self,
        relationship_id: str,
        *,
        organization_id: str,
        new_state: RelationshipState,
        changed_by: str,
        reason: str,
        occurred_at: datetime | None = None,
    ) -> None:
        if not changed_by.strip() or not reason.strip():
            raise CanonicalRelationshipRegistryError("registry actor and reason are required")
        when = occurred_at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            raise CanonicalRelationshipRegistryError("relationship lifecycle timestamp must be timezone-aware")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT organization_id,current_state FROM canonical_relationships WHERE relationship_id=?",
                (relationship_id,),
            ).fetchone()
            if row is None:
                raise CanonicalRelationshipRegistryError("canonical relationship does not exist")
            if row["organization_id"] != organization_id:
                raise PermissionError("canonical relationship organization mismatch")
            current_state = RelationshipState(row["current_state"])
            if new_state == current_state:
                connection.rollback()
                return
            if new_state not in _ALLOWED_TRANSITIONS[current_state]:
                raise PermissionError(f"canonical relationship transition denied: {current_state.value}->{new_state.value}")
            connection.execute(
                "UPDATE canonical_relationships SET current_state=? WHERE relationship_id=?",
                (new_state.value, relationship_id),
            )
            connection.execute(
                "INSERT INTO canonical_relationship_events(relationship_id,organization_id,previous_state,new_state,changed_by,reason,occurred_at) VALUES (?,?,?,?,?,?,?)",
                (
                    relationship_id,
                    organization_id,
                    current_state.value,
                    new_state.value,
                    changed_by,
                    reason,
                    when.astimezone(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def supersede(
        self,
        relationship_id: str,
        replacement: CanonicalRelationship,
        *,
        organization_id: str,
        changed_by: str,
        reason: str,
    ) -> None:
        if replacement.relationship_id == relationship_id:
            raise CanonicalRelationshipRegistryError("replacement relationship id must be new")
        if replacement.source.organization_id != organization_id or replacement.target.organization_id != organization_id:
            raise PermissionError("replacement relationship organization mismatch")
        self.register(replacement, changed_by=changed_by, reason=f"replacement: {reason}")
        self.transition(
            relationship_id,
            organization_id=organization_id,
            new_state=RelationshipState.SUPERSEDED,
            changed_by=changed_by,
            reason=f"superseded-by:{replacement.relationship_id}: {reason}",
        )

    def history(self, relationship_id: str, *, organization_id: str) -> tuple[RelationshipLifecycleEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM canonical_relationship_events WHERE relationship_id=? ORDER BY event_id",
                (relationship_id,),
            ).fetchall()
        events: list[RelationshipLifecycleEvent] = []
        for row in rows:
            if row["organization_id"] != organization_id:
                raise PermissionError("canonical relationship organization mismatch")
            events.append(
                RelationshipLifecycleEvent(
                    event_id=row["event_id"],
                    relationship_id=row["relationship_id"],
                    organization_id=row["organization_id"],
                    previous_state=None if row["previous_state"] is None else RelationshipState(row["previous_state"]),
                    new_state=RelationshipState(row["new_state"]),
                    changed_by=row["changed_by"],
                    reason=row["reason"],
                    occurred_at=datetime.fromisoformat(row["occurred_at"]),
                )
            )
        return tuple(events)

    def list_for_organization(
        self,
        organization_id: str,
        *,
        states: Iterable[RelationshipState] | None = None,
    ) -> tuple[CanonicalRelationship, ...]:
        allowed_states = tuple(states or ())
        with self._connect() as connection:
            if allowed_states:
                placeholders = ",".join("?" for _ in allowed_states)
                rows = connection.execute(
                    f"SELECT relationship_id FROM canonical_relationships WHERE organization_id=? AND current_state IN ({placeholders}) ORDER BY relationship_id",
                    (organization_id, *(state.value for state in allowed_states)),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT relationship_id FROM canonical_relationships WHERE organization_id=? ORDER BY relationship_id",
                    (organization_id,),
                ).fetchall()
        return tuple(
            relationship
            for row in rows
            if (relationship := self.get(row["relationship_id"], organization_id=organization_id)) is not None
        )
