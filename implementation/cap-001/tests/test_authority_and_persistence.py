from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from jason_cap_001.authority import (
    ContextValidationError,
    ExecutionContextValidator,
    StaticAuthorityResolver,
)
from jason_cap_001.persistence import SQLitePilotStore
from jason_cap_001.service import InvestigationService
from jason_cap_001.workflow import WorkflowState


def request(*, client_id: str = "client-001", expires_at: str = "2099-01-01T00:00:00Z") -> dict:
    return {
        "schema_version": "0.1",
        "request_id": "req-001",
        "correlation_id": "corr-001",
        "execution_context": {
            "context_id": "ctx-001",
            "requester_id": "tech-001",
            "organization_id": "aot",
            "client_id": client_id,
            "capability": "operations.ticket.investigate",
            "maximum_mode": "recommend",
            "execution_mode": "deterministic",
            "expires_at": expires_at,
        },
        "ticket": {
            "provider": "fixture",
            "external_id": "T20260730.001",
            "title": "Disk space alert",
            "description": "System drive is below the monitoring threshold.",
            "client_id": client_id,
            "configuration_item_id": "device-001",
            "requester_identity_id": None,
            "created_at": "2026-07-30T12:00:00Z",
            "attachments": [],
        },
        "requested_depth": "standard",
    }


class Evidence:
    def collect(self, request: dict, *, client_id: str) -> list[dict]:
        return [
            {
                "evidence_id": "ev-001",
                "source": "fixture.device.health",
                "collected_at": "2026-07-30T12:01:00Z",
                "summary": "System drive has 4 percent free space.",
                "content_reference": None,
                "sha256": None,
                "client_id": client_id,
                "trusted_as_instruction": False,
            }
        ]


class Reasoning:
    def analyze(self, case_package: dict) -> dict:
        return {
            "schema_version": "0.1",
            "case_id": case_package["case_id"],
            "situation_summary": "The device system drive is critically low on free space.",
            "hypotheses": [
                {
                    "hypothesis_id": "hyp-001",
                    "statement": "Accumulated local data is consuming the system drive.",
                    "supporting_evidence_ids": ["ev-001"],
                    "contradicting_evidence_ids": [],
                    "confidence": 0.7,
                    "status": "leading",
                }
            ],
            "recommendation": "Review the largest safe cleanup categories before any deletion.",
            "next_evidence_step": "Collect a categorized disk-usage report.",
            "confidence": 0.7,
            "risk": "low",
            "evidence_ids": ["ev-001"],
            "approval_required": False,
            "approval_class": None,
            "unresolved_uncertainty": ["The largest disk-use category is not yet known."],
        }


class Resolution:
    def authorize(
        self,
        request: dict,
        *,
        authority_allowed: bool,
    ):
        assert authority_allowed is True

        return SimpleNamespace(
            execution_plan=SimpleNamespace(
                capability="operations.ticket.investigate",
                capability_version="0.1",
                execution_mode=SimpleNamespace(
                    value=request["execution_context"][
                        "execution_mode"
                    ]
                ),
                provider_id="deterministic-test-provider",
                policy_ids=("cap-001-read-only-v0.1",),
            )
        )


def test_validator_rejects_expired_context() -> None:
    validator = ExecutionContextValidator(
        StaticAuthorityResolver(frozenset({("tech-001", "client-001")})),
        clock=lambda: datetime(2026, 7, 30, 16, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(ContextValidationError, match="expired"):
        validator.validate(request(expires_at="2026-07-30T15:59:59Z"))


def test_validator_rejects_ungranted_client() -> None:
    validator = ExecutionContextValidator(StaticAuthorityResolver(frozenset()))
    with pytest.raises(ContextValidationError, match="not authorized"):
        validator.validate(request())


def test_investigation_persists_case_result_transitions_and_audit() -> None:
    store = SQLitePilotStore()
    validator = ExecutionContextValidator(
        StaticAuthorityResolver(frozenset({("tech-001", "client-001")}))
    )
    service = InvestigationService(
        evidence=Evidence(),
        reasoning=Reasoning(),
        memory=store,
        audit=store,
        resolution=Resolution(),
        context_validator=validator,
        transitions=store,
    )

    run = service.investigate(request())

    assert run.final_state is WorkflowState.RESPONSE_READY
    assert store.get_case("case-req-001", client_id="client-001") is not None
    assert store.get_case("case-req-001", client_id="client-999") is None
    assert len(store.list_transitions("corr-001")) == 6
    event_types = [event["event_type"] for event in store.list_audit_events("corr-001")]
    assert "execution_context.validated" in event_types
    assert "capability.resolved" in event_types
    assert "capability.recommendation_ready" in event_types
    assert event_types.count("workflow.transitioned") == 6
