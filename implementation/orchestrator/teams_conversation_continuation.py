from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping


_MAX_RESPONSE_CHARS = 1600
_MAX_FACTS = 20
_MAX_SELECTOR_ITEMS = 12
_MAX_SELECTOR_VALUE_CHARS = 256


@dataclass(frozen=True, slots=True)
class ConversationContinuationState:
    """Bounded, non-secret state for one authenticated Jason conversation.

    The record carries only Jason-owned conversation context that has already crossed
    the normal identity and response boundaries. It never stores provider payloads,
    credentials, tokens, model transcripts, or arbitrary tool output.
    """

    principal_id: str
    organization_id: str
    conversation_id: str
    last_message_id: str
    response_kind: str
    last_response_text: str
    last_capability_name: str | None
    requested_facts: tuple[str, ...]
    resource_selector: Mapping[str, str]
    updated_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        required = {
            "principal_id": self.principal_id,
            "organization_id": self.organization_id,
            "conversation_id": self.conversation_id,
            "last_message_id": self.last_message_id,
            "response_kind": self.response_kind,
            "last_response_text": self.last_response_text,
        }
        missing = sorted(name for name, value in required.items() if not str(value).strip())
        if missing:
            raise ValueError("conversation continuation fields are empty: " + ", ".join(missing))
        if self.response_kind not in {"result", "guidance"}:
            raise ValueError("conversation continuation response_kind is invalid")
        if len(self.last_response_text) > _MAX_RESPONSE_CHARS:
            raise ValueError("conversation continuation response text exceeds safety bound")
        if len(self.requested_facts) > _MAX_FACTS:
            raise ValueError("conversation continuation fact set exceeds safety bound")
        if len(self.resource_selector) > _MAX_SELECTOR_ITEMS:
            raise ValueError("conversation continuation selector exceeds safety bound")
        for raw_key, raw_value in self.resource_selector.items():
            key = str(raw_key).strip()
            value = str(raw_value).strip()
            if not key or not value:
                raise ValueError("conversation continuation selector entries must be non-empty")
            if len(value) > _MAX_SELECTOR_VALUE_CHARS:
                raise ValueError("conversation continuation selector value exceeds safety bound")
        if self.updated_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("conversation continuation timestamps must be timezone-aware")
        if self.expires_at <= self.updated_at:
            raise ValueError("conversation continuation expiry must follow update time")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams_conversation_continuation (
    organization_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    last_message_id TEXT NOT NULL,
    response_kind TEXT NOT NULL,
    last_response_text TEXT NOT NULL,
    last_capability_name TEXT,
    requested_facts_json TEXT NOT NULL,
    resource_selector_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, principal_id, conversation_id)
);
CREATE INDEX IF NOT EXISTS ix_teams_conversation_continuation_expiry
  ON teams_conversation_continuation(expires_at);
"""


class SQLiteTeamsConversationContinuationStore:
    """Short-lived Jason-owned continuation state keyed by bound human identity."""

    def __init__(self, path: str | Path, *, ttl_seconds: int = 1200) -> None:
        if ttl_seconds < 60 or ttl_seconds > 86400:
            raise ValueError("conversation continuation ttl must be between 60 and 86400 seconds")
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl = timedelta(seconds=ttl_seconds)
        self._connection = sqlite3.connect(str(self._path))
        self._connection.executescript(_SCHEMA)
        self._connection.commit()
        os.chmod(self._path, 0o600)

    @property
    def ttl(self) -> timedelta:
        return self._ttl

    def get(
        self,
        *,
        organization_id: str,
        principal_id: str,
        conversation_id: str,
        now: datetime | None = None,
    ) -> ConversationContinuationState | None:
        observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        row = self._connection.execute(
            """
            SELECT last_message_id, response_kind, last_response_text,
                   last_capability_name, requested_facts_json,
                   resource_selector_json, updated_at, expires_at
            FROM teams_conversation_continuation
            WHERE organization_id = ? AND principal_id = ? AND conversation_id = ?
            """,
            (organization_id, principal_id, conversation_id),
        ).fetchone()
        if row is None:
            return None

        expires_at = _parse_utc(str(row[7]))
        if observed_at >= expires_at:
            self.delete(
                organization_id=organization_id,
                principal_id=principal_id,
                conversation_id=conversation_id,
            )
            return None

        requested_facts = json.loads(str(row[4]))
        resource_selector = json.loads(str(row[5]))
        if not isinstance(requested_facts, list) or not isinstance(resource_selector, dict):
            raise RuntimeError("conversation continuation state is malformed")

        return ConversationContinuationState(
            principal_id=principal_id,
            organization_id=organization_id,
            conversation_id=conversation_id,
            last_message_id=str(row[0]),
            response_kind=str(row[1]),
            last_response_text=str(row[2]),
            last_capability_name=None if row[3] is None else str(row[3]),
            requested_facts=tuple(str(item) for item in requested_facts),
            resource_selector={str(key): str(value) for key, value in resource_selector.items()},
            updated_at=_parse_utc(str(row[6])),
            expires_at=expires_at,
        )

    def put(
        self,
        *,
        principal_id: str,
        organization_id: str,
        conversation_id: str,
        last_message_id: str,
        response_kind: str,
        last_response_text: str,
        last_capability_name: str | None,
        requested_facts: tuple[str, ...],
        resource_selector: Mapping[str, str],
        now: datetime | None = None,
    ) -> ConversationContinuationState:
        updated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        state = ConversationContinuationState(
            principal_id=principal_id,
            organization_id=organization_id,
            conversation_id=conversation_id,
            last_message_id=last_message_id,
            response_kind=response_kind,
            last_response_text=last_response_text.strip()[:_MAX_RESPONSE_CHARS],
            last_capability_name=(
                None if last_capability_name is None else last_capability_name.strip()
            ),
            requested_facts=tuple(str(item).strip() for item in requested_facts if str(item).strip()),
            resource_selector={
                str(key).strip(): str(value).strip()
                for key, value in resource_selector.items()
                if str(key).strip() and str(value).strip()
            },
            updated_at=updated_at,
            expires_at=updated_at + self._ttl,
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO teams_conversation_continuation(
                    organization_id, principal_id, conversation_id,
                    last_message_id, response_kind, last_response_text,
                    last_capability_name, requested_facts_json,
                    resource_selector_json, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(organization_id, principal_id, conversation_id) DO UPDATE SET
                    last_message_id = excluded.last_message_id,
                    response_kind = excluded.response_kind,
                    last_response_text = excluded.last_response_text,
                    last_capability_name = excluded.last_capability_name,
                    requested_facts_json = excluded.requested_facts_json,
                    resource_selector_json = excluded.resource_selector_json,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (
                    state.organization_id,
                    state.principal_id,
                    state.conversation_id,
                    state.last_message_id,
                    state.response_kind,
                    state.last_response_text,
                    state.last_capability_name,
                    json.dumps(list(state.requested_facts), separators=(",", ":")),
                    json.dumps(dict(state.resource_selector), sort_keys=True, separators=(",", ":")),
                    state.updated_at.isoformat(),
                    state.expires_at.isoformat(),
                ),
            )
        return state

    def delete(self, *, organization_id: str, principal_id: str, conversation_id: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                DELETE FROM teams_conversation_continuation
                WHERE organization_id = ? AND principal_id = ? AND conversation_id = ?
                """,
                (organization_id, principal_id, conversation_id),
            )

    def close(self) -> None:
        self._connection.close()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("conversation continuation timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)
