from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from orchestrator.ollama_reasoning import (
    OllamaResourceCapabilityReasoner,
    OllamaResourceEvidenceReasoner,
    OllamaResourceInquiryReasoner,
    OllamaStructuredJsonClient,
)
from orchestrator.resource_capability_catalog import endpoint_device_search
from orchestrator.resource_inquiry import ResourceInquiry


class Transport:
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


@dataclass
class Candidate:
    capability_name: str
    display_name: str = "Endpoint search"
    business_purpose: str = "Retrieve endpoint inventory facts"
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {
                "provider_neutral": "true",
                "read_only": "true",
                "resource_types": "endpoint,device",
            }


def client(structured):
    transport = Transport(structured)
    return OllamaStructuredJsonClient(transport=transport, model="local-test"), transport


def test_structured_client_enforces_explicit_generation_budget():
    llm, transport = client({"resolved": False})

    assert llm.complete(
        system="Return a decision.",
        user="hello",
        schema={"type": "object"},
        max_output_tokens=64,
    ) == {"resolved": False}

    request = transport.calls[0]
    assert request["json"]["think"] is False
    assert request["json"]["options"] == {
        "temperature": 0,
        "num_predict": 64,
    }
    assert request["timeout_seconds"] == 45.0


def test_structured_client_rejects_unbounded_generation_budget():
    llm, _ = client({})

    with pytest.raises(ValueError, match="output budget"):
        llm.complete(
            system="x",
            user="y",
            schema={"type": "object"},
            max_output_tokens=4096,
        )


def test_resource_inquiry_reasoner_returns_only_provider_neutral_structure():
    llm, transport = client(
        {
            "resolved": True,
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-50282"},
            "requested_facts": ["last logged in user"],
            "execution_mode": "deterministic",
            "permission_mode": "observe",
            "provider": "should-never-propagate",
        }
    )
    result = OllamaResourceInquiryReasoner(llm).propose(
        text="Who is logged into AOT-50282?",
        organization_id="aot",
        client_id=None,
    )

    assert result == {
        "resource_type": "endpoint",
        "resource_selector": {"hostname": "AOT-50282"},
        "requested_facts": ["last logged in user"],
        "execution_mode": "deterministic",
        "permission_mode": "observe",
    }
    request = transport.calls[0]["json"]
    assert request["think"] is False
    assert request["stream"] is False
    assert request["options"] == {"temperature": 0, "num_predict": 160}
    assert request["format"]["additionalProperties"] is False


def test_resource_inquiry_reasoner_uses_closed_registered_language_contract():
    llm, transport = client(
        {
            "resolved": True,
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "50282"},
            "requested_facts": ["most recent user"],
            "execution_mode": "deterministic",
            "permission_mode": "observe",
        }
    )
    reasoner = OllamaResourceInquiryReasoner(
        llm,
        resource_types=("endpoint",),
        selector_keys=("hostname", "name", "resource_id"),
    )

    result = reasoner.propose(
        text="who was on 50282 last?",
        organization_id="aot",
        client_id=None,
    )

    assert result["resource_type"] == "endpoint"
    request = transport.calls[0]["json"]
    assert request["think"] is False
    resource_type_schema = request["format"]["properties"]["resource_type"]
    selector_schema = request["format"]["properties"]["resource_selector"]
    assert resource_type_schema["enum"] == ["endpoint"]
    assert selector_schema["additionalProperties"] is False
    assert tuple(selector_schema["properties"]) == ("hostname", "name", "resource_id")
    prompt = json.loads(request["messages"][1]["content"])
    assert prompt["allowed_resource_types"] == ["endpoint"]
    assert prompt["allowed_selector_keys"] == ["hostname", "name", "resource_id"]


def test_capability_reasoner_selects_only_candidate_and_builds_arguments_deterministically():
    llm, transport = client({"capability_names": ["endpoint.device.search"]})
    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("last logged in user",),
    )
    steps = OllamaResourceCapabilityReasoner(llm).select(
        inquiry=inquiry,
        candidates=[Candidate("endpoint.device.search")],
    )

    assert len(steps) == 1
    assert steps[0].capability_name == "endpoint.device.search"
    assert steps[0].arguments == {
        "hostname": "AOT-50282",
        "requested_facts": ["last logged in user"],
    }
    assert transport.calls[0]["json"]["think"] is False
    assert transport.calls[0]["json"]["options"]["num_predict"] == 64


def test_capability_reasoner_accepts_real_governed_capability_contract():
    llm, transport = client({"capability_names": ["endpoint.device.search"]})
    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("last logged in user",),
    )

    steps = OllamaResourceCapabilityReasoner(llm).select(
        inquiry=inquiry,
        candidates=[endpoint_device_search(datetime.now(timezone.utc))],
    )

    assert steps[0].capability_name == "endpoint.device.search"
    prompt = json.loads(transport.calls[0]["json"]["messages"][1]["content"])
    candidate = prompt["candidates"][0]
    assert candidate["display_name"] == "Search Managed Endpoints"
    assert candidate["business_purpose"]
    assert "description" not in candidate


def test_capability_reasoner_rejects_name_outside_candidate_set_even_if_model_returns_it():
    llm, _ = client({"capability_names": ["datto_rmm.device.search"]})
    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("last logged in user",),
    )
    try:
        OllamaResourceCapabilityReasoner(llm).select(
            inquiry=inquiry,
            candidates=[Candidate("endpoint.device.search")],
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("out-of-candidate capability must fail closed")


def test_evidence_reasoner_returns_locations_not_values():
    llm, transport = client(
        {
            "locations": [
                {
                    "requested_fact": "last logged in user",
                    "json_pointer": "/devices/0/lastUser",
                    "value": "model-asserted-value-must-be-ignored",
                }
            ]
        }
    )
    locations = OllamaResourceEvidenceReasoner(llm).locate(
        requested_facts=("last logged in user",),
        data={"devices": [{"lastUser": "AOT\\real.user"}]},
    )
    assert locations == (
        {
            "requested_fact": "last logged in user",
            "json_pointer": "/devices/0/lastUser",
            "value": "model-asserted-value-must-be-ignored",
        },
    )
    assert transport.calls[0]["json"]["think"] is False
    assert transport.calls[0]["json"]["options"]["num_predict"] == 96
