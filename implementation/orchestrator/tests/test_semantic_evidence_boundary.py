from __future__ import annotations

import pytest

from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.resource_evidence import GovernedResourceEvidenceInterpreter
from orchestrator.semantic_evidence_boundary import GovernedSemanticEvidenceBoundary
from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER


class PointerReasoner:
    def __init__(self, pointer: str) -> None:
        self.pointer = pointer

    def locate(self, *, requested_facts, data):
        return tuple(
            {
                "requested_fact": fact,
                "json_pointer": self.pointer,
            }
            for fact in requested_facts
        )


def result(data):
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="endpoint.device.search",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("capability_completed",),
        resolution=None,
        output={"provider": "datto_rmm", "data": data},
        attempts=1,
        provider_id="datto_rmm",
    )


def boundary(pointer: str) -> GovernedSemanticEvidenceBoundary:
    return GovernedSemanticEvidenceBoundary(
        inner=GovernedResourceEvidenceInterpreter(
            reasoner=PointerReasoner(pointer),
        ),
        fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
    )


def test_bitlocker_status_cannot_bind_to_generic_provider_status():
    interpreter = boundary("/provider_data/status")

    with pytest.raises(LookupError, match="semantic context required for bitlocker status"):
        interpreter.interpret(
            result=result(
                {
                    "provider_data": {
                        "status": "RunningAndUpToDate",
                    }
                }
            ),
            requested_facts=("bitlocker status",),
        )


def test_bitlocker_recovery_key_cannot_bind_to_discovery_marker():
    interpreter = boundary("/provider_data/hostname_fragment")

    with pytest.raises(
        LookupError,
        match="semantic context required for bitlocker recovery key",
    ):
        interpreter.interpret(
            result=result(
                {
                    "provider_data": {
                        "hostname_fragment": "hostname_fragment",
                    }
                }
            ),
            requested_facts=("bitlocker recovery key",),
        )


def test_governed_semantic_projection_can_satisfy_bitlocker_status():
    interpreter = boundary("/unused")

    facts = interpreter.interpret(
        result=result(
            {
                "provider_data": {
                    "semantic_evidence": {
                        "security": {
                            "bitlocker": {
                                "udf": {
                                    "bitlocker status": "Encrypted",
                                }
                            }
                        }
                    }
                }
            }
        ),
        requested_facts=("bitlocker status",),
    )

    assert facts[0].value == "Encrypted"
    assert facts[0].json_pointer.startswith(
        "/provider_data/semantic_evidence/"
    )
