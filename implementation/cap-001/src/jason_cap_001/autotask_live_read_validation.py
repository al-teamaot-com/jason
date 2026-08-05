from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .autotask_ticket_provider import AutotaskTicketProvider


class LiveReadValidationError(RuntimeError):
    """Raised when controlled live-read validation cannot complete safely."""


@dataclass(frozen=True, slots=True)
class LiveReadValidationRequest:
    ticket_number: str
    company_id: str
    scope_name: str
    live_read_acknowledged: bool


@dataclass(frozen=True, slots=True)
class LiveReadEvidence:
    schema_version: str
    provider: str
    scope_name: str
    ticket_number: str
    company_id: str
    retrieved_at: str
    configuration_item_id: str | None
    requester_identity_id: str | None
    created_at: str
    updated_at: str | None
    title_sha256: str
    description_sha256: str
    evidence_sha256: str
    status: str


class AutotaskLiveReadValidator:
    """Run one explicit, read-only Autotask validation and write redacted evidence."""

    def __init__(self, *, provider: AutotaskTicketProvider, allowed_scope: str) -> None:
        normalized_scope = allowed_scope.strip()
        if not normalized_scope:
            raise ValueError("allowed_scope must be non-empty")
        self._provider = provider
        self._allowed_scope = normalized_scope

    def validate(
        self,
        request: LiveReadValidationRequest,
        *,
        output_path: Path,
    ) -> LiveReadEvidence:
        if not request.live_read_acknowledged:
            raise LiveReadValidationError(
                "Live-read validation requires explicit acknowledgement."
            )

        ticket_number = request.ticket_number.strip()
        company_id = request.company_id.strip()
        scope_name = request.scope_name.strip()
        if not ticket_number or not company_id or not scope_name:
            raise LiveReadValidationError(
                "ticket_number, company_id, and scope_name are required."
            )
        if scope_name != self._allowed_scope:
            raise PermissionError(
                "Requested validation scope is not authorized for live reads."
            )

        destination = output_path.expanduser().resolve()
        if self._is_inside_repository(destination):
            raise LiveReadValidationError(
                "Live-read evidence must be written outside the repository."
            )
        if destination.exists():
            raise LiveReadValidationError(
                "Live-read evidence output already exists; overwrite is denied."
            )

        ticket = self._provider.get_ticket(ticket_number, client_id=company_id)
        if ticket["external_id"] != ticket_number:
            raise LiveReadValidationError("Validated ticket identity changed.")
        if ticket["client_id"] != company_id:
            raise PermissionError("Validated ticket crossed the company boundary.")

        retrieved_at = datetime.now(timezone.utc).isoformat()
        title_sha256 = self._hash_text(ticket["title"])
        description_sha256 = self._hash_text(ticket["description"])

        core: dict[str, Any] = {
            "schema_version": "0.1",
            "provider": "autotask",
            "scope_name": scope_name,
            "ticket_number": ticket_number,
            "company_id": company_id,
            "retrieved_at": retrieved_at,
            "configuration_item_id": ticket["configuration_item_id"],
            "requester_identity_id": ticket["requester_identity_id"],
            "created_at": ticket["created_at"],
            "updated_at": ticket["updated_at"],
            "title_sha256": title_sha256,
            "description_sha256": description_sha256,
            "status": "approved",
        }
        evidence_sha256 = hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        evidence = LiveReadEvidence(**core, evidence_sha256=evidence_sha256)

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(asdict(evidence), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return evidence

    @staticmethod
    def _hash_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_inside_repository(path: Path) -> bool:
        current = Path.cwd().resolve()
        repository = None
        for candidate in (current, *current.parents):
            if (candidate / ".git").exists():
                repository = candidate
                break
        if repository is None:
            return False
        try:
            path.relative_to(repository)
        except ValueError:
            return False
        return True
