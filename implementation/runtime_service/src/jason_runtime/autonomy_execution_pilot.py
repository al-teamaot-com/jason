"""Controlled first autonomous mutation acceptance for Project Jason.

This module proves the non-human workload identity -> durable playbook promotion
-> exact governed execution -> independent readback chain on one explicitly
configured Autotask test ticket. It is not a general queue execution loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from autonomous_remediation.autonomous_principal import (
    AutonomousRequestFactory,
    StandingPolicyAuthorization,
)
from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)


SERVICE_TICKET_READ = "service.ticket.read"
SERVICE_TICKET_NOTES_SEARCH = "service.ticket.notes.search"
SERVICE_COMPANY_READ = "service.company.read"
SERVICE_TICKET_NOTE_CREATE = "service.ticket.note.create"


class GovernedReadPort(Protocol):
    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


class OrchestratorPort(Protocol):
    def execute(self, request: Any) -> Any: ...


class AutonomyExecutionPilotError(RuntimeError):
    pass


@dataclass(frozen=True)
class AutonomyInternalNotePilotSpec:
    ticket_id: int
    expected_ticket_number: str
    company_id: int
    expected_company_name: str
    playbook_id: str
    playbook_version: str
    policy_id: str
    note_title: str
    note_body: str

    def __post_init__(self) -> None:
        if self.ticket_id < 1 or self.company_id < 1:
            raise ValueError("ticket_id and company_id must be positive")
        for name in (
            "expected_ticket_number",
            "expected_company_name",
            "playbook_id",
            "playbook_version",
            "policy_id",
            "note_title",
            "note_body",
        ):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True)
class AutonomyInternalNotePilotResult:
    status: str
    ticket_id: int
    ticket_number: str
    company_id: int
    company_name: str
    note_title: str
    ticket_note_id: int | None
    provider: str | None
    correlation_id: str | None
    approval_id: str | None
    idempotency_key: str | None
    readback_verified: bool
    duplicate_write_avoided: bool


class ControlledAutonomyInternalNotePilot:
    """Execute at most one exact internal-note mutation on a controlled test ticket."""

    def __init__(
        self,
        *,
        spec: AutonomyInternalNotePilotSpec,
        reads: GovernedReadPort,
        request_factory: AutonomousRequestFactory,
        orchestrator: OrchestratorPort,
        promotion_store: SQLitePlaybookAutonomyApprovalStore,
    ) -> None:
        self.spec = spec
        self.reads = reads
        self.request_factory = request_factory
        self.orchestrator = orchestrator
        self.promotion_store = promotion_store

    def run_once(self) -> AutonomyInternalNotePilotResult:
        ticket = self._precheck_ticket()
        company = self._precheck_company()
        existing = self._matching_notes()
        if len(existing) > 1:
            raise AutonomyExecutionPilotError(
                "pilot marker is duplicated; refusing another write"
            )
        if len(existing) == 1:
            note_id = self._positive_int(existing[0].get("id"), "existing note id")
            return AutonomyInternalNotePilotResult(
                status="already_verified",
                ticket_id=self.spec.ticket_id,
                ticket_number=self.spec.expected_ticket_number,
                company_id=self.spec.company_id,
                company_name=self.spec.expected_company_name,
                note_title=self.spec.note_title,
                ticket_note_id=note_id,
                provider="autotask",
                correlation_id=None,
                approval_id=None,
                idempotency_key=None,
                readback_verified=True,
                duplicate_write_avoided=True,
            )

        promotion = self.promotion_store.find_approved(
            playbook_id=self.spec.playbook_id,
            playbook_version=self.spec.playbook_version,
            policy_id=self.spec.policy_id,
            capability=SERVICE_TICKET_NOTE_CREATE,
        )
        if promotion is None:
            raise AutonomyExecutionPilotError(
                "exact durable playbook/capability promotion is missing"
            )

        standing_policy = StandingPolicyAuthorization(
            playbook_id=self.spec.playbook_id,
            playbook_version=self.spec.playbook_version,
            policy_id=self.spec.policy_id,
            promotion_approval_id=promotion.approval_id,
        )
        request = self.request_factory.build(
            capability_name=SERVICE_TICKET_NOTE_CREATE,
            arguments={
                "payload": {
                    "ticketID": self.spec.ticket_id,
                    "description": self.spec.note_body,
                    "noteType": 3,
                    "publish": 1,
                    "title": self.spec.note_title,
                }
            },
            client_id=None,
            standing_policy=standing_policy,
        )
        result = self.orchestrator.execute(request)

        status = getattr(getattr(result, "status", None), "value", None)
        if status != "succeeded":
            raise AutonomyExecutionPilotError(
                "governed autonomous mutation did not succeed: "
                + str(getattr(result, "error_code", None) or getattr(result, "reason_codes", None))
            )

        output = result.output if isinstance(getattr(result, "output", None), Mapping) else {}
        verification = output.get("jasonVerification")
        if not isinstance(verification, Mapping) or verification.get("readbackVerified") is not True:
            raise AutonomyExecutionPilotError(
                "provider mutation succeeded without required connector readback verification"
            )
        note_id = self._positive_int(
            verification.get("ticketNoteId"),
            "verified ticket note id",
        )

        post = self._matching_notes()
        if len(post) != 1:
            raise AutonomyExecutionPilotError(
                "independent governed note search did not observe exactly one pilot note"
            )
        observed_id = self._positive_int(post[0].get("id"), "post-read note id")
        if observed_id != note_id:
            raise AutonomyExecutionPilotError(
                "independent governed readback note id does not match connector verification"
            )

        return AutonomyInternalNotePilotResult(
            status="succeeded",
            ticket_id=self.spec.ticket_id,
            ticket_number=str(ticket.get("ticketNumber") or ""),
            company_id=self.spec.company_id,
            company_name=str(company.get("companyName") or ""),
            note_title=self.spec.note_title,
            ticket_note_id=note_id,
            provider=getattr(result, "provider_id", None),
            correlation_id=getattr(result, "correlation_id", None),
            approval_id=request.approval_id,
            idempotency_key=request.idempotency_key,
            readback_verified=True,
            duplicate_write_avoided=False,
        )

    def _precheck_ticket(self) -> Mapping[str, Any]:
        data = self._read_data(
            self.reads.execute(
                SERVICE_TICKET_READ,
                {"ticket_id": self.spec.ticket_id},
            )
        )
        items = data.get("items")
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
            raise AutonomyExecutionPilotError(
                "controlled pilot ticket did not resolve uniquely"
            )
        ticket = items[0]
        if self._positive_int(ticket.get("id"), "ticket id") != self.spec.ticket_id:
            raise AutonomyExecutionPilotError("controlled pilot ticket id drifted")
        if str(ticket.get("ticketNumber") or "") != self.spec.expected_ticket_number:
            raise AutonomyExecutionPilotError("controlled pilot ticket number drifted")
        if self._positive_int(ticket.get("companyID"), "ticket company id") != self.spec.company_id:
            raise AutonomyExecutionPilotError("controlled pilot ticket company drifted")
        return ticket

    def _precheck_company(self) -> Mapping[str, Any]:
        data = self._read_data(
            self.reads.execute(
                SERVICE_COMPANY_READ,
                {"resource_id": self.spec.company_id},
            )
        )
        company = data.get("item")
        if not isinstance(company, Mapping):
            raise AutonomyExecutionPilotError(
                "controlled pilot company did not resolve"
            )
        if self._positive_int(company.get("id"), "company id") != self.spec.company_id:
            raise AutonomyExecutionPilotError("controlled pilot company id drifted")
        if str(company.get("companyName") or "") != self.spec.expected_company_name:
            raise AutonomyExecutionPilotError("controlled pilot company name drifted")
        return company

    def _matching_notes(self) -> list[Mapping[str, Any]]:
        data = self._read_data(
            self.reads.execute(
                SERVICE_TICKET_NOTES_SEARCH,
                {"ticket_id": self.spec.ticket_id},
            )
        )
        items = data.get("items")
        if not isinstance(items, list):
            raise AutonomyExecutionPilotError("ticket note search returned invalid items")
        return [
            item
            for item in items
            if isinstance(item, Mapping)
            and str(item.get("title") or "") == self.spec.note_title
            and str(item.get("description") or "") == self.spec.note_body
            and int(item.get("noteType") or 0) == 3
            and int(item.get("publish") or 0) == 1
        ]

    @staticmethod
    def _read_data(result: Mapping[str, Any]) -> Mapping[str, Any]:
        if str(result.get("status") or "") != "succeeded":
            raise AutonomyExecutionPilotError(
                "governed pilot pre/post read failed: "
                + str(result.get("error_code") or result.get("reason_codes"))
            )
        evidence = result.get("evidence")
        data = evidence.get("data") if isinstance(evidence, Mapping) else None
        if not isinstance(data, Mapping):
            raise AutonomyExecutionPilotError(
                "governed pilot read returned no structured provider data"
            )
        return data

    @staticmethod
    def _positive_int(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise AutonomyExecutionPilotError(f"{label} is invalid")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise AutonomyExecutionPilotError(f"{label} is invalid") from exc
        if parsed < 1:
            raise AutonomyExecutionPilotError(f"{label} is invalid")
        return parsed
