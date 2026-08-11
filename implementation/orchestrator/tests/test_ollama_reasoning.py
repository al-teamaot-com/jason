from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

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
    assert request["stream"] is False
    assert request["options"]["temperature"] == 0
    assert request["format"]["additionalProperties"] is False


def test_capability_reasoner_selects_only_candidate_and_builds_arguments_deterministically():
    llm, _ = client({"capability_names": ["endpoint.device.search"]})
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
    llm, _ = client(
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
