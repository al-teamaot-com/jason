from __future__ import annotations

import pytest

from orchestrator.conversation_evidence_transform import (
    TransformEvidence,
    ValidatedConversationEvidenceTransformer,
)
from orchestrator.conversation_kernel import (
    ConversationKernelError,
    ReasoningBackend,
    ValidatedReasoningPool,
)


class FakeClient:
    def __init__(
        self,
        *responses,
    ):
        self.responses = list(responses)
        self.calls = []

    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens=160,
    ):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "max_output_tokens": max_output_tokens,
            }
        )

        return self.responses.pop(0)


def pool(client):
    return ValidatedReasoningPool(
        backends=(
            ReasoningBackend(
                name="model",
                client=client,
            ),
        )
    )


def approved_review():
    return {
        "approved": True,
        "operation_matches_evidence": True,
        "produces_answer_ready_value": True,
        "unsupported_is_justified": False,
        "unsupported_claim_risk": False,
    }


def transformer(
    *,
    operation,
    input_paths,
):
    planner = FakeClient(
        {
            "operation": operation,
            "input_paths": list(input_paths),
        }
    )

    reviewer = FakeClient(
        approved_review()
    )

    return (
        ValidatedConversationEvidenceTransformer(
            planning=pool(planner),
            reviewing=pool(reviewer),
        ),
        planner,
    )


def test_identity_uses_one_selected_scalar():
    service, _ = transformer(
        operation="identity",
        input_paths=(
            "/sources/0/data/value",
        ),
    )

    result = service.transform(
        question="requested text value",
        evidence=(
            TransformEvidence(
                path="/sources/0/data/value",
                value="Example Value",
            ),
        ),
    )

    assert result is not None
    assert result.operation == "identity"
    assert result.value == "Example Value"
    assert result.source_paths == (
        "/sources/0/data/value",
    )


def test_redundant_scalar_and_container_can_choose_only_scalar_measurement():
    service, _ = transformer(
        operation="bytes_to_gib",
        input_paths=(
            "/sources/0/data/total",
        ),
    )

    result = service.transform(
        question="requested capacity",
        evidence=(
            TransformEvidence(
                path="/sources/0/data/total",
                value=68719476736,
            ),
            TransformEvidence(
                path="/sources/0/data/modules",
                value=[
                    {"size": 17179869184},
                    {"size": 17179869184},
                    {"size": 17179869184},
                    {"size": 17179869184},
                ],
            ),
        ),
    )

    assert result is not None
    assert result.operation == "bytes_to_gib"
    assert result.value == "64 GiB"
    assert result.source_paths == (
        "/sources/0/data/total",
    )


def test_selected_container_exposes_bounded_descendant_inputs_for_sum():
    paths = tuple(
        f"/sources/0/data/modules/{index}/size"
        for index in range(4)
    )

    service, planner = transformer(
        operation="sum_bytes_to_gib",
        input_paths=paths,
    )

    result = service.transform(
        question="requested total capacity",
        evidence=(
            TransformEvidence(
                path="/sources/0/data/modules",
                value=[
                    {"size": 17179869184},
                    {"size": 17179869184},
                    {"size": 17179869184},
                    {"size": 17179869184},
                ],
            ),
        ),
    )

    assert result is not None
    assert result.value == "64 GiB"
    assert result.source_paths == paths

    call = planner.calls[0]

    for path in paths:
        assert path in call["user"]


def test_transform_schema_does_not_embed_provider_derived_paths():
    odd_path = (
        "/sources/0/data/example/' Write-Host \""
    )

    service, planner = transformer(
        operation="identity",
        input_paths=(odd_path,),
    )

    result = service.transform(
        question="requested text",
        evidence=(
            TransformEvidence(
                path=odd_path,
                value="Example",
            ),
        ),
    )

    assert result is not None

    schema = planner.calls[0]["schema"]

    assert (
        schema["properties"]
        ["input_paths"]
        ["items"]
        == {"type": "string"}
    )

    assert odd_path not in str(schema)


def test_unoffered_transform_input_is_rejected_deterministically():
    planner = FakeClient(
        {
            "operation": "identity",
            "input_paths": [
                "/sources/0/data/not-offered"
            ],
        }
    )

    reviewer = FakeClient(
        approved_review()
    )

    service = (
        ValidatedConversationEvidenceTransformer(
            planning=pool(planner),
            reviewing=pool(reviewer),
        )
    )

    with pytest.raises(
        ConversationKernelError,
    ):
        service.transform(
            question="requested text",
            evidence=(
                TransformEvidence(
                    path="/sources/0/data/actual",
                    value="Example",
                ),
            ),
        )

    assert reviewer.calls == []
