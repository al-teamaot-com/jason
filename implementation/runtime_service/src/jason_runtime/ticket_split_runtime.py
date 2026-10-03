from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


class TicketSplitError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TicketSplitTarget:
    target_key: str
    title: str
    description: str
    configuration_item_id: int

    def __post_init__(self) -> None:
        if not self.target_key.strip():
            raise ValueError("target_key must be non-empty")
        if not self.title.strip():
            raise ValueError("title must be non-empty")
        if self.configuration_item_id <= 0:
            raise ValueError("configuration_item_id must be positive")


@dataclass(frozen=True, slots=True)
class TicketSplitRequest:
    source_ticket_id: int
    source_ticket_number: str
    company_id: int
    queue_id: int | str
    priority: int
    targets: tuple[TicketSplitTarget, ...]
    status: int | str | None = None
    issue_type: int | None = None
    sub_issue_type: int | None = None
    ticket_type: int | None = None

    def __post_init__(self) -> None:
        if self.source_ticket_id <= 0:
            raise ValueError("source_ticket_id must be positive")
        if not self.source_ticket_number.strip():
            raise ValueError("source_ticket_number must be non-empty")
        if self.company_id < 0:
            raise ValueError("company_id must be non-negative")
        if isinstance(self.queue_id, str):
            if not self.queue_id.strip():
                raise ValueError("queue_id must be a non-empty label or positive integer")
        elif int(self.queue_id) <= 0:
            raise ValueError("queue_id must be a non-empty label or positive integer")
        if self.priority <= 0:
            raise ValueError("priority must be positive")
        if len(self.targets) < 2:
            raise ValueError("ticket split requires at least two targets")
        keys = [target.target_key.casefold() for target in self.targets]
        if len(set(keys)) != len(keys):
            raise ValueError("ticket split target_key values must be unique")


@dataclass(frozen=True, slots=True)
class TicketSplitChild:
    source_ticket_id: int
    target_key: str
    child_ticket_id: int
    marker: str


@dataclass(frozen=True, slots=True)
class TicketSplitResult:
    source_ticket_id: int
    children: tuple[TicketSplitChild, ...]
    created_count: int
    reused_count: int


class SQLiteTicketSplitStore:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS ticket_split_children (
        source_ticket_id INTEGER NOT NULL,
        target_key TEXT NOT NULL,
        child_ticket_id INTEGER NOT NULL,
        marker TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY(source_ticket_id, target_key)
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

    def get(self, source_ticket_id: int, target_key: str) -> TicketSplitChild | None:
        row = self._connection.execute(
            "SELECT source_ticket_id,target_key,child_ticket_id,marker FROM ticket_split_children "
            "WHERE source_ticket_id=? AND target_key=?",
            (source_ticket_id, target_key.casefold()),
        ).fetchone()
        if row is None:
            return None
        return TicketSplitChild(
            source_ticket_id=int(row["source_ticket_id"]),
            target_key=str(row["target_key"]),
            child_ticket_id=int(row["child_ticket_id"]),
            marker=str(row["marker"]),
        )

    def put(self, child: TicketSplitChild) -> None:
        payload = json.dumps(asdict(child), sort_keys=True, separators=(",", ":"))
        with self._connection:
            existing = self._connection.execute(
                "SELECT child_ticket_id,marker FROM ticket_split_children "
                "WHERE source_ticket_id=? AND target_key=?",
                (child.source_ticket_id, child.target_key.casefold()),
            ).fetchone()
            if existing is not None:
                if (
                    int(existing["child_ticket_id"]) == child.child_ticket_id
                    and str(existing["marker"]) == child.marker
                ):
                    return
                raise TicketSplitError("ticket split target already maps to a different child")
            self._connection.execute(
                "INSERT INTO ticket_split_children VALUES (?,?,?,?,?)",
                (
                    child.source_ticket_id,
                    child.target_key.casefold(),
                    child.child_ticket_id,
                    child.marker,
                    payload,
                ),
            )

    def list_for_source(self, source_ticket_id: int) -> tuple[TicketSplitChild, ...]:
        rows = self._connection.execute(
            "SELECT source_ticket_id,target_key,child_ticket_id,marker "
            "FROM ticket_split_children WHERE source_ticket_id=? ORDER BY target_key",
            (source_ticket_id,),
        ).fetchall()
        return tuple(
            TicketSplitChild(
                source_ticket_id=int(row["source_ticket_id"]),
                target_key=str(row["target_key"]),
                child_ticket_id=int(row["child_ticket_id"]),
                marker=str(row["marker"]),
            )
            for row in rows
        )

    def close(self) -> None:
        self._connection.close()


class TicketSplitExecutor:
    """Provider-neutral composite ticket split primitive.

    The caller supplies the playbook/workflow scope and therefore the exact
    standing authority. This primitive never grants service.ticket.create
    authority by itself.
    """

    def __init__(self, *, actions, store: SQLiteTicketSplitStore) -> None:
        self.actions = actions
        self.store = store

    @staticmethod
    def marker(source_ticket_number: str, target_key: str) -> str:
        digest = hashlib.sha256(
            f"{source_ticket_number.casefold()}|{target_key.casefold()}".encode("utf-8")
        ).hexdigest()[:20]
        return f"JASON-SPLIT:{source_ticket_number}:{digest}"

    @staticmethod
    def _action_data(output: Mapping[str, Any]) -> Mapping[str, Any]:
        data = output.get("data")
        return data if isinstance(data, Mapping) else output

    @classmethod
    def _verified_ticket_id(cls, output: Mapping[str, Any]) -> int:
        data = cls._action_data(output)
        verification = data.get("jasonVerification")
        if isinstance(verification, Mapping):
            if verification.get("readbackVerified") is not True:
                raise TicketSplitError("created child ticket did not pass provider readback")
            raw = verification.get("ticketId") or data.get("itemId") or data.get("id")
        else:
            if data.get("readback_verified") is not True:
                raise TicketSplitError("created child ticket did not pass provider readback")
            raw = data.get("ticket_id")
        try:
            ticket_id = int(raw)
        except (TypeError, ValueError) as error:
            raise TicketSplitError("created child ticket id is missing") from error
        if ticket_id <= 0:
            raise TicketSplitError("created child ticket id is invalid")
        return ticket_id

    def execute(self, *, scope, request: TicketSplitRequest) -> TicketSplitResult:
        children: list[TicketSplitChild] = []
        created = 0
        reused = 0
        for target in request.targets:
            existing = self.store.get(request.source_ticket_id, target.target_key)
            if existing is not None:
                children.append(existing)
                reused += 1
                continue

            marker = self.marker(request.source_ticket_number, target.target_key)
            description = (
                f"{target.description.strip()}\n\n"
                f"Source ticket: {request.source_ticket_number}\n"
                f"Split target: {target.target_key}\n"
                f"Split marker: {marker}"
            ).strip()
            payload: dict[str, Any] = {
                "companyID": request.company_id,
                "title": target.title.strip()[:512],
                "description": description,
                "priority": request.priority,
                "queueID": request.queue_id,
                "configurationItemID": target.configuration_item_id,
            }
            if request.status is not None:
                payload["status"] = request.status
            if request.issue_type is not None:
                payload["issueType"] = request.issue_type
            if request.sub_issue_type is not None:
                payload["subIssueType"] = request.sub_issue_type
            if request.ticket_type is not None:
                payload["ticketType"] = request.ticket_type

            output = self.actions.execute(
                scope,
                "service.ticket.create",
                {"payload": payload},
            )
            child_id = self._verified_ticket_id(output)
            child = TicketSplitChild(
                source_ticket_id=request.source_ticket_id,
                target_key=target.target_key.casefold(),
                child_ticket_id=child_id,
                marker=marker,
            )
            self.store.put(child)
            children.append(child)
            created += 1

        return TicketSplitResult(
            source_ticket_id=request.source_ticket_id,
            children=tuple(children),
            created_count=created,
            reused_count=reused,
        )
