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
        "result_intent": "summary",
        "completeness_requirement": "sufficient",
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
        fact_hints=("hostname last user logged in user operating system",),
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
    assert selector_schema["properties"]["hostname"] == {
        "type": "string",
        "minLength": 1,
    }
    prompt = json.loads(request["messages"][1]["content"])
    assert prompt["allowed_resource_types"] == ["endpoint"]
    assert prompt["allowed_selector_keys"] == ["hostname", "name", "resource_id"]
    assert prompt["fact_hints"] == ["hostname last user logged in user operating system"]
    assert "organization_scope" not in prompt
    assert "client_scope_present" not in prompt
    system_prompt = request["messages"][0]["content"]
    assert "Never infer ownership, tenant, client, site" in system_prompt
    assert "Authorization scope is not supplied to this language reasoner" in system_prompt
    assert "requested_facts must describe only" in system_prompt
    assert "Return the smallest set of requested facts necessary" in system_prompt
    assert "Never add related, adjacent, potentially useful, or merely available facts" in system_prompt


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
        "result_intent": "summary",
        "completeness_requirement": "sufficient",
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
    request = transport.calls[0]["json"]
    assert request["think"] is False
    assert request["options"]["num_predict"] == 96
    prompt = json.loads(request["messages"][1]["content"])
    assert "evidence" not in prompt
    assert prompt["evidence_index"] == [
        {
            "json_pointer": "/devices/0/lastUser",
            "field": "lastUser",
            "type": "str",
        },
        {
            "json_pointer": "/devices",
            "field": "devices",
            "type": "list",
        },
    ]
    system_prompt = request["messages"][0]["content"]
    assert "never prefix a pointer with /evidence" in system_prompt
    assert "/resource_matches/0/resource_id" in system_prompt



def test_evidence_reasoner_sends_bounded_structural_index_not_full_payload():
    from orchestrator.ollama_reasoning import (
        OllamaResourceEvidenceReasoner,
        OllamaStructuredJsonClient,
    )

    class Transport:
        def __init__(self):
            self.request_json = None

        def request(self, **kwargs):
            self.request_json = kwargs["json"]
            return {
                "message": {
                    "content": '{"locations":[{"requested_fact":"last logged in user","json_pointer":"/devices/0/lastUser"}]}'
                }
            }

    transport = Transport()
    reasoner = OllamaResourceEvidenceReasoner(
        OllamaStructuredJsonClient(
            transport=transport,
            model="local-test",
        )
    )

    huge = {
        "devices": [
            {
                "hostname": "AOT-50282",
                "lastUser": "ExampleUser",
                "noise": "x" * 10000,
            }
        ],
        "large": [{"field": "value"} for _ in range(500)],
    }

    result = reasoner.locate(
        requested_facts=("last logged in user",),
        data=huge,
    )

    assert result[0]["json_pointer"] == "/devices/0/lastUser"

    import json
    payload = json.loads(transport.request_json["messages"][1]["content"])

    assert "evidence" not in payload
    assert "evidence_index" in payload

    encoded = json.dumps(payload)
    assert len(encoded) < 30000
    assert "x" * 1000 not in encoded

    pointers = {item["json_pointer"] for item in payload["evidence_index"]}
    assert "/devices/0/lastUser" in pointers


def test_bounded_evidence_index_has_hard_entry_limit():
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "items": [
            {f"field_{j}": f"value_{i}_{j}" for j in range(20)}
            for i in range(100)
        ]
    }

    index = _bounded_evidence_index(data, max_entries=25)
    assert len(index) <= 25



def test_relevance_bounded_index_prioritizes_requested_fact_and_excludes_values():
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "noise": {f"field_{i}": f"value_{i}" for i in range(200)},
        "device": {
            "hostname": "AOT-50282",
            "lastUser": "AOT\\verified.user",
            "operatingSystem": "Windows",
        },
    }

    index = _bounded_evidence_index(
        data,
        requested_facts=("last logged in user",),
        max_entries=8,
    )

    assert index[0]["json_pointer"] == "/device/lastUser"
    assert all("value" not in item for item in index)
    assert len(index) <= 8



def test_evidence_pointer_schema_is_constrained_to_supplied_index():
    from orchestrator.ollama_reasoning import (
        OllamaResourceEvidenceReasoner,
        OllamaStructuredJsonClient,
    )

    class Transport:
        def __init__(self):
            self.request_json = None

        def request(self, **kwargs):
            self.request_json = kwargs["json"]
            return {
                "message": {
                    "content": '{"locations":[{"requested_fact":"last logged in user","json_pointer":"/device/lastUser"}]}'
                }
            }

    transport = Transport()
    reasoner = OllamaResourceEvidenceReasoner(
        OllamaStructuredJsonClient(
            transport=transport,
            model="local-test",
        )
    )

    reasoner.locate(
        requested_facts=("last logged in user",),
        data={
            "device": {
                "hostname": "AOT-50282",
                "lastUser": "AOT\\verified.user",
            }
        },
    )

    schema = transport.request_json["format"]
    pointer_schema = (
        schema["properties"]["locations"]["items"]["properties"]["json_pointer"]
    )

    assert pointer_schema["type"] == "string"
    assert "/device/lastUser" in pointer_schema["enum"]
    assert "/resource_matches/0/from" not in pointer_schema["enum"]


def test_canonical_evidence_hints_rank_provider_fields_without_changing_requested_fact_labels():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "provider_data": {
            "processors": [
                {"logicalProcessors": 8, "name": "Intel Core i7"}
            ]
        }
    }
    index = _bounded_evidence_index(
        data,
        requested_facts=("processor model",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    pointers = [item["json_pointer"] for item in index]
    assert "/provider_data/processors/0/name" in pointers[:8]


def test_structured_json_retry_increases_generation_budget_after_truncated_json():
    import json

    class TruncatingTransport:
        def __init__(self):
            self.payloads = []

        def request(self, **kwargs):
            import copy
            self.payloads.append(copy.deepcopy(kwargs["json"]))
            if len(self.payloads) == 1:
                return {"message": {"content": '{"status":"propose_plan","rationale_summary":"unterminated'}}
            return {"message": {"content": json.dumps({"status": "ok"})}}

    transport = TruncatingTransport()
    client = OllamaStructuredJsonClient(transport=transport, model="test-model")
    result = client.complete(
        system="bounded test",
        user="bounded test",
        schema={"type": "object"},
        max_output_tokens=160,
    )

    assert result == {"status": "ok"}
    assert transport.payloads[0]["options"]["num_predict"] == 160
    assert transport.payloads[1]["options"]["num_predict"] == 320
