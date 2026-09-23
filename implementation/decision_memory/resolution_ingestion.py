from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from .resolution_memory import (
    ResolutionCase,
    ResolutionCaseStatus,
    ResolutionOutcome,
    ResolutionSignature,
    ResolutionSourceReference,
    ResolutionStep,
)


class ResolutionIngestionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConfirmedResolutionIngestion:
    """A fully evidenced candidate for durable Resolution Memory.

    Ingestion is intentionally strict: a completed ticket alone is never enough.
    The caller must supply a current client boundary, a normalized incident
    signature, an explicit root cause/final resolution, and at least one source
    reference. Verified status additionally requires technician confirmation and
    terminal verification evidence.
    """

    case_id: str
    organization_id: str
    client_id: str
    ticket_id: str
    ticket_company_id: str
    current_company_id: str
    signature: ResolutionSignature
    source_references: tuple[ResolutionSourceReference, ...]
    steps: tuple[ResolutionStep, ...]
    root_cause: str
    final_resolution: str
    outcome: ResolutionOutcome
    technician_confirmed: bool
    terminal_verification_confirmed: bool
    recorded_at: datetime
    resolved_at: datetime
    owner: str

    def to_case(self) -> ResolutionCase:
        required = {
            "case_id": self.case_id,
            "organization_id": self.organization_id,
            "client_id": self.client_id,
            "ticket_id": self.ticket_id,
            "ticket_company_id": self.ticket_company_id,
            "current_company_id": self.current_company_id,
            "root_cause": self.root_cause,
            "final_resolution": self.final_resolution,
            "owner": self.owner,
        }
        missing = sorted(k for k, v in required.items() if not str(v).strip())
        if missing:
            raise ResolutionIngestionError("missing required ingestion evidence: " + ", ".join(missing))
        if self.ticket_company_id != self.current_company_id:
            raise ResolutionIngestionError("ticket company does not match current company boundary")
        if not self.source_references:
            raise ResolutionIngestionError("at least one source reference is required")
        if not any(r.source_type == "autotask_ticket" and r.source_id == self.ticket_id for r in self.source_references):
            raise ResolutionIngestionError("source references must include the exact Autotask ticket")
        if self.outcome is ResolutionOutcome.RESOLVED and not self.terminal_verification_confirmed:
            raise ResolutionIngestionError("resolved case requires terminal verification evidence")
        status = (
            ResolutionCaseStatus.VERIFIED
            if self.technician_confirmed and self.terminal_verification_confirmed
            else ResolutionCaseStatus.OBSERVED
        )
        case = ResolutionCase(
            case_id=self.case_id,
            organization_id=self.organization_id,
            client_id=self.client_id,
            signature=self.signature,
            source_references=self.source_references,
            steps=self.steps,
            root_cause=self.root_cause,
            final_resolution=self.final_resolution,
            outcome=self.outcome,
            status=status,
            technician_confirmed=self.technician_confirmed,
            recorded_at=self.recorded_at,
            resolved_at=self.resolved_at,
            owner=self.owner,
        )
        case.validate()
        return case
