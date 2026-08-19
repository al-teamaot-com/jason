from __future__ import annotations

from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
from orchestrator.conversation_resource_intent import MetadataFirstResourceInquiryInterpreter
from orchestrator.teams_conversation_flow import BoundConversationPrincipal


class ForbiddenFallback:
    def interpret(self, **kwargs):
        raise AssertionError("bounded deterministic read must not fall back to reasoning")


def principal() -> BoundConversationPrincipal:
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
    )


def interpreter() -> MetadataFirstResourceInquiryInterpreter:
    return MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "endpoint.device.search",
                "resource_types": ("endpoint",),
                "selector_keys": ("hostname", "name", "resource_id"),
                "fact_hints": (
                    "hostname",
                    "last logged in user",
                    "operating system",
                    "ip address",
                ),
                "canonical_facts": (
                    "LAN IP address",
                    "WAN IP address",
                    "last logged in user",
                    "operating system",
                ),
                "selector_required": True,
            },
        ),
        fallback=ForbiddenFallback(),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )


def test_generic_ip_question_expands_to_complete_bounded_safe_fact_set():
    inquiry = interpreter().interpret(
        text="What's the IP address for AOT-50282?",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.resource_type == "endpoint"
    assert inquiry.resource_selector == {"hostname": "AOT-50282"}
    assert inquiry.requested_facts == (
        "LAN IP address",
        "WAN IP address",
    )
    assert inquiry.permission_mode == "observe"
    assert inquiry.execution_mode == "deterministic"


def test_explicit_lan_ip_question_remains_one_fact():
    inquiry = interpreter().interpret(
        text="What's the LAN IP address for AOT-50282?",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.requested_facts == ("LAN IP address",)


def test_explicit_public_ip_question_remains_one_fact():
    inquiry = interpreter().interpret(
        text="What's the public IP address for AOT-50282?",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.requested_facts == ("WAN IP address",)


def test_explicit_os_and_last_user_question_preserves_both_facts():
    inquiry = interpreter().interpret(
        text="What OS and last user does AOT-50282 show?",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.resource_selector == {
        "hostname": "AOT-50282",
    }
    assert inquiry.requested_facts == (
        "operating system",
        "last logged in user",
    )
    assert inquiry.permission_mode == "observe"
    assert inquiry.execution_mode == "deterministic"


def test_explicit_last_user_and_os_reverse_order_preserves_both_facts():
    inquiry = interpreter().interpret(
        text="For AOT-50282, give me the last user and OS.",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.requested_facts == (
        "last logged in user",
        "operating system",
    )
