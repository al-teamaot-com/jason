from __future__ import annotations

import json

from orchestrator.hosted_reasoning_egress import (
    HostedReasoningEgressClassifier,
)


def classifier():
    return HostedReasoningEgressClassifier()


def payload(message):
    return json.dumps(
        {
            "message": message,
            "context": {
                "conversation_id": "conv-1",
                "organization_id": "aot",
                "active_entity_refs": {},
                "entities": [],
            },
        }
    )


def test_normal_endpoint_question_is_hosted_eligible():
    decision = classifier().classify(
        user_payload=payload(
            "How much RAM does AOT-50282 have?"
        )
    )

    assert decision.classification == "internal"
    assert decision.hosted_processing_allowed is True
    assert decision.data_handling.retention_allowed is False


def test_last_user_question_is_hosted_eligible():
    decision = classifier().classify(
        user_payload=payload(
            "Who was the last logged-on user on AOT-50282?"
        )
    )

    assert decision.hosted_processing_allowed is True


def test_password_request_is_restricted_even_without_password_value():
    decision = classifier().classify(
        user_payload=payload(
            "What is the administrator password for AOT-50282?"
        )
    )

    assert decision.classification == "restricted"
    assert decision.hosted_processing_allowed is False


def test_ssn_is_restricted():
    decision = classifier().classify(
        user_payload=payload(
            "Look up SSN 123-45-6789 for this record."
        )
    )

    assert decision.hosted_processing_allowed is False


def test_valid_payment_card_is_restricted():
    decision = classifier().classify(
        user_payload=payload(
            "Check card 4111 1111 1111 1111."
        )
    )

    assert decision.hosted_processing_allowed is False


def test_phi_indicator_is_restricted():
    decision = classifier().classify(
        user_payload=payload(
            "What diagnosis is in this patient's medical record?"
        )
    )

    assert decision.hosted_processing_allowed is False


def test_cui_indicator_is_restricted():
    decision = classifier().classify(
        user_payload=payload(
            "Summarize this CUI record."
        )
    )

    assert decision.hosted_processing_allowed is False


def test_secret_shaped_value_is_restricted():
    decision = classifier().classify(
        user_payload=payload(
            "Use bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
        )
    )

    assert decision.hosted_processing_allowed is False


def test_empty_payload_fails_closed():
    decision = classifier().classify(user_payload="")

    assert decision.classification == "restricted"
    assert decision.hosted_processing_allowed is False
