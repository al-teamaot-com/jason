"""SQLite persistence for Jason's bounded provider-independent conversation state."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .dynamic_conversation_kernel import (
    ConversationEntity,
    ConversationReferenceResolution,
    DynamicConversationContext,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS dynamic_conversation_context (
    organization_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    active_entity_refs_json TEXT NOT NULL,
    active_topic TEXT,
    recent_resolutions_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, principal_id, conversation_id)
);
CREATE INDEX IF NOT EXISTS ix_dynamic_conversation_context_expiry
  ON dynamic_conversation_context(expires_at);
"""


class SQLiteDynamicConversationContextStore:
    """Store only bounded Jason-owned context, never provider payloads or credentials."""

    def __init__(self, path: str | Path, *, ttl_seconds: int = 3600) -> None:
        if ttl_seconds < 60 or ttl_seconds > 86400:
            raise ValueError("dynamic conversation ttl must be between 60 and 86400 seconds")
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl = timedelta(seconds=ttl_seconds)
        self._connection = sqlite3.connect(str(self._path))
        self._connection.executescript(_SCHEMA)
        self._connection.commit()
        os.chmod(self._path, 0o600)

    def get(
        self,
        *,
        organization_id: str,
        principal_id: str,
        conversation_id: str,
        now: datetime | None = None,
    ) -> DynamicConversationContext | None:
        observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        row = self._connection.execute(
            """
            SELECT entities_json, active_entity_refs_json, active_topic,
                   recent_resolutions_json, expires_at
            FROM dynamic_conversation_context
            WHERE organization_id = ? AND principal_id = ? AND conversation_id = ?
            """,
            (organization_id, principal_id, conversation_id),
        ).fetchone()
        if row is None:
            return None
        expires_at = _parse_utc(str(row[4]))
        if observed >= expires_at:
            self.delete(
                organization_id=organization_id,
                principal_id=principal_id,
                conversation_id=conversation_id,
            )
            return None

        entities_raw = json.loads(str(row[0]))
        active_raw = json.loads(str(row[1]))
        resolutions_raw = json.loads(str(row[3]))
        if not isinstance(entities_raw, list) or not isinstance(active_raw, dict) or not isinstance(resolutions_raw, list):
            raise RuntimeError("dynamic conversation context is malformed")

        entities = tuple(
            ConversationEntity(
                ref=str(item["ref"]),
                kind=str(item["kind"]),
                canonical_id=str(item["canonical_id"]),
                display_name=str(item["display_name"]),
                provenance=str(item["provenance"]),
            )
            for item in entities_raw
            if isinstance(item, Mapping)
        )
        resolutions = tuple(
            ConversationReferenceResolution(
                mention=str(item["mention"]),
                entity_ref=str(item["entity_ref"]),
                basis=str(item["basis"]),
            )
            for item in resolutions_raw
            if isinstance(item, Mapping)
        )
        return DynamicConversationContext(
            conversation_id=conversation_id,
            principal_id=principal_id,
            organization_id=organization_id,
            entities=entities,
            active_entity_refs={str(key): str(value) for key, value in active_raw.items()},
            active_topic=None if row[2] is None else str(row[2]),
            recent_resolutions=resolutions,
        )

    def put(
        self,
        context: DynamicConversationContext,
        *,
        now: datetime | None = None,
    ) -> DynamicConversationContext:
        updated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        expires = updated + self._ttl
        entities = [
            {
                "ref": item.ref,
                "kind": item.kind,
                "canonical_id": item.canonical_id,
                "display_name": item.display_name,
                "provenance": item.provenance,
            }
            for item in context.entities
        ]
        resolutions = [
            {
                "mention": item.mention,
                "entity_ref": item.entity_ref,
                "basis": item.basis,
            }
            for item in context.recent_resolutions
        ]
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO dynamic_conversation_context(
                    organization_id, principal_id, conversation_id,
                    entities_json, active_entity_refs_json, active_topic,
                    recent_resolutions_json, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(organization_id, principal_id, conversation_id) DO UPDATE SET
                    entities_json = excluded.entities_json,
                    active_entity_refs_json = excluded.active_entity_refs_json,
                    active_topic = excluded.active_topic,
                    recent_resolutions_json = excluded.recent_resolutions_json,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (
                    context.organization_id,
                    context.principal_id,
                    context.conversation_id,
                    json.dumps(entities, sort_keys=True, separators=(",", ":")),
                    json.dumps(dict(context.active_entity_refs), sort_keys=True, separators=(",", ":")),
                    context.active_topic,
                    json.dumps(resolutions, sort_keys=True, separators=(",", ":")),
                    updated.isoformat(),
                    expires.isoformat(),
                ),
            )
        return context

    def delete(self, *, organization_id: str, principal_id: str, conversation_id: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                DELETE FROM dynamic_conversation_context
                WHERE organization_id = ? AND principal_id = ? AND conversation_id = ?
                """,
                (organization_id, principal_id, conversation_id),
            )

    def close(self) -> None:
        self._connection.close()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("dynamic conversation timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)
