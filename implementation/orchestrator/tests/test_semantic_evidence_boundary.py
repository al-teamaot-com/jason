from __future__ import annotations

import pytest

from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.resource_evidence import GovernedResourceEvidenceInterpreter


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


def interpreter(pointer: str) -> GovernedResourceEvidenceInterpreter:
    return GovernedResourceEvidenceInterpreter(
        reasoner=PointerReasoner(pointer),
    )


def test_bitlocker_status_cannot_bind_to_generic_provider_status():
    evidence = interpreter("/provider_data/status")

    with pytest.raises(
        LookupError,
        match="did not support all requested facts: bitlocker status",
    ):
        evidence.interpret(
            result=result(
                {
                    "provider_data": {
                        "status": "RunningAndUpToDate",
                    }
                }
            ),
            requested_facts=("bitlocker status",),
            evidence_contexts={
                "bitlocker status": ("bitlocker", "udf"),
            },
        )


def test_bitlocker_recovery_key_cannot_bind_to_discovery_marker():
    evidence = interpreter("/provider_data/hostname_fragment")

    with pytest.raises(
        LookupError,
        match="did not support all requested facts: bitlocker recovery key",
    ):
        evidence.interpret(
            result=result(
                {
                    "provider_data": {
                        "hostname_fragment": "hostname_fragment",
                    }
                }
            ),
            requested_facts=("bitlocker recovery key",),
            evidence_contexts={
                "bitlocker recovery key": ("bitlocker", "recovery"),
            },
        )


def test_governed_semantic_projection_can_satisfy_bitlocker_status():
    evidence = interpreter("/unused")

    facts = evidence.interpret(
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
        evidence_contexts={
            "bitlocker status": ("bitlocker", "udf"),
        },
    )

    assert facts[0].value == "Encrypted"
    assert facts[0].json_pointer.startswith(
        "/provider_data/semantic_evidence/"
    )
