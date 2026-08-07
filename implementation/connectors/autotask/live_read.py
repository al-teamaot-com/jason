from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from connectors.core.contracts import (
    Connector,
    ConnectorContext,
    ConnectorRequest,
)


class AutotaskLiveReadError(RuntimeError):
    """Safe failure for governed Autotask live-read validation."""


@dataclass(frozen=True)
class AutotaskLiveReadRequest:
    ticket_number: str
    scope_name: str
    allowed_scope: str
    principal_id: str
    organization_id: str
    correlation_id: str
    live_read_acknowledged: bool


@dataclass(frozen=True)
class AutotaskTicketSnapshot:
    """Ephemeral ticket content returned through the canonical read boundary.

    Raw title and description are intentionally not written to the standard
    live-read evidence record. Callers must apply their own governed data-
    handling rules before persisting derived artifacts.
    """

    ticket_number: str
    company_id: str
    title: str
    description: str
    created_at: str
    updated_at: str | None
    configuration_item_id: str | None
    requester_identity_id: str | None


@dataclass(frozen=True)
class AutotaskLiveReadEvidence:
    schema_version: str
    provider: str
    capability: str
    logical_secret: str
    scope_name: str
    ticket_number: str
    discovered_company_id: str
    company_boundary_source: str
    retrieved_at: str
    configuration_item_id: str | None
    requester_identity_id: str | None
    created_at: str
    updated_at: str | None
    title_sha256: str
    description_sha256: str
    evidence_sha256: str
    protected_values_exposed: bool
    status: str


class GovernedAutotaskLiveRead:
    """Preserve CAP-001 safeguards on the canonical connector path."""

    logical_secret = "autotask.readonly"
    capability = "autotask.ticket.search"

    def __init__(self, connector: Connector) -> None:
        self._connector = connector

    def read_ticket(
        self,
        request: AutotaskLiveReadRequest,
        *,
        output_path: Path,
        repository_root: Path | None = None,
    ) -> tuple[AutotaskTicketSnapshot, AutotaskLiveReadEvidence]:
        """Read one exact ticket and persist the existing redacted evidence."""
        normalized = self._validate_request(request)
        destination = output_path.expanduser().resolve()
        self._validate_destination(destination, repository_root)

        search = json.dumps(
            {
                "filter": [
                    {
                        "op": "eq",
                        "field": "ticketNumber",
                        "value": normalized.ticket_number,
                    }
                ]
            },
            separators=(",", ":"),
        )

        result = self._connector.execute(
            ConnectorRequest(
                context=ConnectorContext(
                    correlation_id=normalized.correlation_id,
                    principal_id=normalized.principal_id,
                    organization_id=normalized.organization_id,
                    client_id=None,
                    capability=self.capability,
                    mode="observe",
                ),
                arguments={"search": search},
            )
        )

        ticket = self._extract_exact_ticket(
            result.data,
            ticket_number=normalized.ticket_number,
        )
        discovered_company_id = self._required_string(
            ticket.get("companyID"),
            "companyID",
        )
        snapshot = AutotaskTicketSnapshot(
            ticket_number=normalized.ticket_number,
            company_id=discovered_company_id,
            title=str(ticket["title"]),
            description=str(ticket["description"]),
            created_at=str(ticket["createDate"]),
            updated_at=self._optional_string(ticket.get("lastActivityDate")),
            configuration_item_id=self._optional_string(
                ticket.get("configurationItemID")
            ),
            requester_identity_id=self._optional_string(ticket.get("contactID")),
        )
        evidence = self._build_evidence(
            normalized,
            ticket,
            discovered_company_id=discovered_company_id,
        )
        self._write_evidence(destination, evidence)
        return snapshot, evidence

    def validate(
        self,
        request: AutotaskLiveReadRequest,
        *,
        output_path: Path,
        repository_root: Path | None = None,
    ) -> AutotaskLiveReadEvidence:
        """Compatibility boundary for CAP-001 callers that need evidence only."""
        _, evidence = self.read_ticket(
            request,
            output_path=output_path,
            repository_root=repository_root,
        )
        return evidence

    @staticmethod
    def _validate_request(
        request: AutotaskLiveReadRequest,
    ) -> AutotaskLiveReadRequest:
        values = {
            "ticket_number": request.ticket_number.strip(),
            "scope_name": request.scope_name.strip(),
            "allowed_scope": request.allowed_scope.strip(),
            "principal_id": request.principal_id.strip(),
            "organization_id": request.organization_id.strip(),
            "correlation_id": request.correlation_id.strip(),
        }
        missing = sorted(name for name, value in values.items() if not value)
        if missing:
            raise AutotaskLiveReadError(
                "Required values are blank: " + ", ".join(missing)
            )
        if not request.live_read_acknowledged:
            raise PermissionError(
                "Live read requires explicit acknowledgement."
            )
        if values["scope_name"] != values["allowed_scope"]:
            raise PermissionError(
                "Requested scope does not match the authorized scope."
            )
        return AutotaskLiveReadRequest(
            **values,
            live_read_acknowledged=True,
        )

    @staticmethod
    def _validate_destination(
        destination: Path,
        repository_root: Path | None,
    ) -> None:
        if destination.exists():
            raise FileExistsError(
                "Evidence output already exists; overwrite is denied."
            )
        if repository_root is not None:
            root = repository_root.expanduser().resolve()
            try:
                destination.relative_to(root)
            except ValueError:
                pass
            else:
                raise AutotaskLiveReadError(
                    "Live-read evidence must be outside the repository."
                )

    @staticmethod
    def _extract_exact_ticket(
        payload: Mapping[str, Any],
        *,
        ticket_number: str,
    ) -> Mapping[str, Any]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise AutotaskLiveReadError(
                "Autotask response is missing the items collection."
            )
        if len(items) != 1 or not isinstance(items[0], Mapping):
            raise AutotaskLiveReadError(
                "Unique ticket lookup must return exactly one ticket."
            )
        ticket = items[0]
        if str(ticket.get("ticketNumber", "")) != ticket_number:
            raise AutotaskLiveReadError(
                "Validated ticket identity changed."
            )
        required = {
            "companyID",
            "title",
            "description",
            "createDate",
        }
        missing = sorted(field for field in required if field not in ticket)
        if missing:
            raise AutotaskLiveReadError(
                "Autotask ticket is missing required fields: "
                + ", ".join(missing)
            )
        return ticket

    @classmethod
    def _build_evidence(
        cls,
        request: AutotaskLiveReadRequest,
        ticket: Mapping[str, Any],
        *,
        discovered_company_id: str,
    ) -> AutotaskLiveReadEvidence:
        core: dict[str, Any] = {
            "schema_version": "1.1",
            "provider": "autotask",
            "capability": cls.capability,
            "logical_secret": cls.logical_secret,
            "scope_name": request.scope_name,
            "ticket_number": request.ticket_number,
            "discovered_company_id": discovered_company_id,
            "company_boundary_source": "autotask-ticket",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "configuration_item_id": cls._optional_string(
                ticket.get("configurationItemID")
            ),
            "requester_identity_id": cls._optional_string(
                ticket.get("contactID")
            ),
            "created_at": str(ticket["createDate"]),
            "updated_at": cls._optional_string(
                ticket.get("lastActivityDate")
            ),
            "title_sha256": cls._hash_text(str(ticket["title"])),
            "description_sha256": cls._hash_text(
                str(ticket["description"])
            ),
            "protected_values_exposed": False,
            "status": "approved",
        }
        evidence_sha256 = hashlib.sha256(
            json.dumps(
                core,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return AutotaskLiveReadEvidence(
            **core,
            evidence_sha256=evidence_sha256,
        )

    @staticmethod
    def _write_evidence(
        destination: Path,
        evidence: AutotaskLiveReadEvidence,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(evidence), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(destination)

    @staticmethod
    def _hash_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _required_string(value: object, field: str) -> str:
        if value is None or not str(value).strip():
            raise AutotaskLiveReadError(
                f"Autotask ticket contains an invalid {field}."
            )
        return str(value)

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        return str(value)
