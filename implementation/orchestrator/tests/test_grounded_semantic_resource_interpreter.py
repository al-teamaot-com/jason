from __future__ import annotations

import json

import pytest

from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
from orchestrator.grounded_semantic_resource_interpreter import (
    GroundedSemanticResourceInquiryInterpreter,
)
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
from orchestrator.semantic_fact_reasoning import OllamaSemanticFactReasoner
from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER
from orchestrator.teams_conversation_flow import BoundConversationPrincipal


class ForbiddenFallback:
    def interpret(self, **kwargs):
        raise AssertionError("grounded semantic endpoint read must not use full inquiry fallback")


class FixedSemanticReasoner:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def infer(self, **kwargs):
        self.calls.append(kwargs)
        return self.facts


class SemanticTransport:
    def __init__(self, structured):
        self.structured = structured
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "message": {
                "role": "assistant",
                "content": json.dumps(self.structured),
            }
        }


def principal() -> BoundConversationPrincipal:
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
    )


def contracts():
    return (
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
    )


def interpreter(reasoner) -> GroundedSemanticResourceInquiryInterpreter:
    return GroundedSemanticResourceInquiryInterpreter(
        contracts=contracts(),
        fallback=ForbiddenFallback(),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
        semantic_fact_reasoner=reasoner,
        fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
    )


@pytest.mark.parametrize(
    "human_text",
    (
        "Who used AOT-50282 last",
        "Who was on AOT-50282 last?",
        "Who last logged into AOT-50282?",
        "user on aot-50282?",
        "recent person for AOT-50282",
    ),
)
def test_free_form_endpoint_language_uses_fact_only_semantic_reasoning(human_text):
    reasoner = FixedSemanticReasoner(("last logged in user",))

    inquiry = interpreter(reasoner).interpret(
        text=human_text,
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.resource_type == "endpoint"
    assert inquiry.resource_selector == {"hostname": "AOT-50282"}
    assert inquiry.requested_facts == ("last logged in user",)
    assert inquiry.permission_mode == "observe"
    assert inquiry.execution_mode == "deterministic"

    assert len(reasoner.calls) == 1
    call = reasoner.calls[0]
    assert call["resource_selector"] == {"hostname": "AOT-50282"}
    assert "last logged in user" in call["eligible_facts"]


def test_explicit_known_fact_does_not_require_semantic_model():
    reasoner = FixedSemanticReasoner(("operating system",))

    inquiry = interpreter(reasoner).interpret(
        text="last user on AOT-50282?",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.requested_facts == ("last logged in user",)
    assert reasoner.calls == []


def test_semantic_fact_reasoner_cannot_select_outside_governed_candidates():
    transport = SemanticTransport(
        {
            "resolved": True,
            "requested_facts": ["delete endpoint"],
        }
    )
    client = OllamaStructuredJsonClient(
        transport=transport,
        model="local-test",
    )
    reasoner = OllamaSemanticFactReasoner(client)

    with pytest.raises(PermissionError, match="outside governed candidates"):
        reasoner.infer(
            text="do something unexpected to AOT-50282",
            resource_type="endpoint",
            resource_selector={"hostname": "AOT-50282"},
            eligible_facts=("last logged in user", "operating system"),
        )


def test_semantic_fact_reasoner_schema_has_no_selector_or_execution_authority():
    transport = SemanticTransport(
        {
            "resolved": True,
            "requested_facts": ["last logged in user"],
        }
    )
    client = OllamaStructuredJsonClient(
        transport=transport,
        model="local-test",
    )
    reasoner = OllamaSemanticFactReasoner(client)

    result = reasoner.infer(
        text="user on aot-50282?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        eligible_facts=("last logged in user", "operating system"),
    )

    assert result == ("last logged in user",)

    request = transport.calls[0]["json"]
    schema_properties = request["format"]["properties"]
    assert set(schema_properties) == {"resolved", "requested_facts"}
    assert schema_properties["requested_facts"]["items"]["enum"] == [
        "last logged in user",
        "operating system",
    ]

    prompt = json.loads(request["messages"][1]["content"])
    assert prompt["grounded_resource"]["selector"] == {
        "hostname": "AOT-50282"
    }
    assert prompt["governed_fact_candidates"][0]["canonical_fact"] == (
        "last logged in user"
    )
    assert "provider" not in request["format"]["properties"]
    assert "capability" not in request["format"]["properties"]
    assert "resource_selector" not in request["format"]["properties"]
