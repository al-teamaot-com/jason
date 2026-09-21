"""Durable trusted state for Jason-owned Autotask ticket work.

The store captures the pre-claim queue/status before Jason moves a ticket into its
working queue. A later handoff can therefore restore only provider state that
Jason itself previously recorded from an authoritative ticket read.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@dataclass(frozen=True, slots=True)
class TicketWorkClaim:
    ticket_id: int
    original_queue_id: int
    original_status_id: int
    state: str
    captured_at: str
    claimed_at: str = ""
    returned_at: str = ""
    handoff_reason_class: str = ""
    blocker_fingerprint: str = ""

    @classmethod
    def from_ticket(cls, ticket: Mapping[str, Any]) -> "TicketWorkClaim":
        ticket_id = _positive_int(ticket.get("id"))
        queue_id = _positive_int(ticket.get("queueID"))
        status_id = _positive_int(ticket.get("status"))
        if ticket_id is None or queue_id is None or status_id is None:
            raise ValueError("AUTOTASK_TICKET_WORK_ORIGINAL_STATE_INCOMPLETE")
        return cls(
            ticket_id=ticket_id,
            original_queue_id=queue_id,
            original_status_id=status_id,
            state="pending",
            captured_at=_now(),
        )


class TicketWorkClaimStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(
            path
            or os.environ.get(
                "JASON_TICKET_WORK_CLAIMS_PATH",
                "/var/lib/jason/openclaw/ticket-work-claims.json",
            )
        )

    def _load_all(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("AUTOTASK_TICKET_WORK_CLAIM_STORE_INVALID")
        return {
            str(key): dict(value)
            for key, value in payload.items()
            if isinstance(value, Mapping)
        }

    def _write_all(self, payload: Mapping[str, Mapping[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=".ticket-work-claims.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def get(self, ticket_id: int) -> TicketWorkClaim | None:
        raw = self._load_all().get(str(int(ticket_id)))
        if raw is None:
            return None
        return TicketWorkClaim(**raw)

    def stage(self, ticket: Mapping[str, Any], *, blocker_fingerprint: str = "") -> TicketWorkClaim:
        candidate = TicketWorkClaim.from_ticket(ticket)
        payload = self._load_all()
        existing_raw = payload.get(str(candidate.ticket_id))
        if isinstance(existing_raw, Mapping):
            existing = TicketWorkClaim(**dict(existing_raw))
            if existing.state == "claimed":
                return existing
            if existing.state == "returned":
                supplied = blocker_fingerprint.strip()
                if not supplied or supplied == existing.blocker_fingerprint:
                    raise ValueError("AUTOTASK_TICKET_WORK_BLOCKER_UNCHANGED")
        payload[str(candidate.ticket_id)] = asdict(candidate)
        self._write_all(payload)
        return candidate

    def mark_claimed(self, ticket_id: int) -> TicketWorkClaim:
        payload = self._load_all()
        raw = payload.get(str(int(ticket_id)))
        if not isinstance(raw, Mapping):
            raise ValueError("AUTOTASK_TICKET_WORK_CLAIM_STATE_MISSING")
        claim = TicketWorkClaim(**dict(raw))
        updated = TicketWorkClaim(
            **{
                **asdict(claim),
                "state": "claimed",
                "claimed_at": _now(),
                "returned_at": "",
                "handoff_reason_class": "",
                "blocker_fingerprint": "",
            }
        )
        payload[str(updated.ticket_id)] = asdict(updated)
        self._write_all(payload)
        return updated

    def discard_pending(self, ticket_id: int) -> None:
        payload = self._load_all()
        raw = payload.get(str(int(ticket_id)))
        if not isinstance(raw, Mapping):
            return
        claim = TicketWorkClaim(**dict(raw))
        if claim.state != "pending":
            return
        payload.pop(str(claim.ticket_id), None)
        self._write_all(payload)

    def mark_returned(
        self,
        ticket_id: int,
        *,
        reason_class: str,
        blocker_fingerprint: str,
    ) -> TicketWorkClaim:
        payload = self._load_all()
        raw = payload.get(str(int(ticket_id)))
        if not isinstance(raw, Mapping):
            raise ValueError("AUTOTASK_TICKET_WORK_CLAIM_STATE_MISSING")
        claim = TicketWorkClaim(**dict(raw))
        if claim.state != "claimed":
            raise ValueError("AUTOTASK_TICKET_WORK_NOT_CLAIMED")
        updated = TicketWorkClaim(
            **{
                **asdict(claim),
                "state": "returned",
                "returned_at": _now(),
                "handoff_reason_class": reason_class.strip(),
                "blocker_fingerprint": blocker_fingerprint.strip(),
            }
        )
        payload[str(updated.ticket_id)] = asdict(updated)
        self._write_all(payload)
        return updated
