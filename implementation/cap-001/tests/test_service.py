from __future__ import annotations

from copy import deepcopy

import pytest

from jason_cap_001.service import InvestigationService
from jason_cap_001.workflow import WorkflowState


class EvidenceStub:
    def collect(self, request: dict, *, client_id: str) -> list[dict]:
        return [
            {
                "evidence_id": "e1",
                "source": "fixture",
                "collected_at": "2026-07-30T14:00:00Z",
                "summary": "Diagnostic reports one warning.",
                "content_reference": None,
                "sha256": None,
                "client_id": client_id,
                "trusted_as_instruction": False,
            }
        ]


class ReasoningStub:
    def analyze(self, case_package: dict) -> dict:
        return {
            "schema_version": "0.1",
            "case_id": case_package["case_id"],
            "situation_summary": "One diagnostic warning requires review.",
            "hypotheses": [
                {
                    "hypothesis_id": "h1",
                    "statement": "The warning may require technician action.",
                    "supporting_evidence_ids": ["e1"],
                    "contradicting_evidence_ids": [],
                    "confidence": 0.7,
                    "status": "leading",
                }
            ],
            "recommendation": "Review the cited warning and verify its current state before changing the system.",
            "next_evidence_step": None,
            "confidence": 0.7,
            "risk": "medium",
            "evidence_ids": ["e1"],
            "approval_required": False,
            "approval_class": None,
            "unresolved_uncertainty": [],
        }


class MemoryStub:
    def __init__(self) -> None:
        self.cases: list[dict] = []
        self.results: list[dict] = []

    def record_case(self, case_package: dict) -> None:
        self.cases.append(case_package)

    def record_result(self, reasoning_result: dict) -> None:
        self.results.append(reasoning_result)


class AuditStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


def request_fixture() -> dict:
    return {
        "schema_version": "0.1",
        "request_id": "req-1",
        "correlation_id": "corr-1",
        "execution_context": {
            "context_id": "ctx-1",
            "requester_id": "person-1",
            "organization_id": "aot",
            "client_id": "client-1",
            "capability": "ticket.investigate",
            "maximum_mode": "recommend",
            "expires_at": "2026-07-31T14:00:00Z",
        },
        "ticket": {
            "provider": "fixture",
            "external_id": "ticket-1",
            "title": "Diagnostic warning",
            "description": "Please review the attached diagnostic output.",
            "client_id": "client-1",
            "configuration_item_id": None,
            "requester_identity_id": None,
            "created_at": "2026-07-30T13:00:00Z",
            "attachments": [],
        },
        "requested_depth": "standard",
    }


def test_end_to_end_read_only_recommendation() -> None:
    memory = MemoryStub()
    audit = AuditStub()
    service = InvestigationService(evidence=EvidenceStub(), reasoning=ReasoningStub(), memory=memory, audit=audit)

    run = service.investigate(request_fixture())

    assert run.final_state == WorkflowState.RESPONSE_READY
    assert run.quality.passed
    assert len(memory.cases) == 1
    assert len(memory.results) == 1
    assert audit.events[-1][0] == "capability.recommendation_ready"


def test_client_scope_mismatch_fails_closed() -> None:
    request = deepcopy(request_fixture())
    request["ticket"]["client_id"] = "client-2"
    service = InvestigationService(evidence=EvidenceStub(), reasoning=ReasoningStub(), memory=MemoryStub(), audit=AuditStub())

    with pytest.raises(PermissionError):
        service.investigate(request)
