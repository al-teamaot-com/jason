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
    ]

    # The fact value is not exposed through evidence-index metadata. Jason
    # deterministically dereferences it only after the model selects a pointer.
    serialized_index = json.dumps(prompt["evidence_index"])
    assert "AOT\\\\real.user" not in serialized_index
    system_prompt = request["messages"][0]["content"]
    assert (
        "never prefix a pointer with /evidence"
        in system_prompt.casefold()
    )
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


def test_structured_json_retry_preserves_declared_generation_budget_after_truncated_json():
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
    assert transport.payloads[1]["options"]["num_predict"] == 160


def test_bounded_index_scans_deep_evidence_after_large_early_noise():
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "noise": {
            f"field{number}": number
            for number in range(1500)
        },
        "sections": {
            "audit": {
                "payload": {
                    "systemInfo": {
                        "totalPhysicalMemory": 68629368832,
                    }
                }
            }
        },
    }

    index = _bounded_evidence_index(
        data,
        requested_facts=("total memory",),
    )

    pointers = {
        item["json_pointer"]
        for item in index
    }

    assert (
        "/sections/audit/payload/systemInfo/totalPhysicalMemory"
        in pointers
    )


def test_bounded_index_understands_camel_case_and_plural_path_context():
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "sections": {
            "audit": {
                "payload": {
                    "processors": [
                        {
                            "name": "Intel Core i7-9700F",
                        }
                    ]
                }
            }
        }
    }

    index = _bounded_evidence_index(
        data,
        requested_facts=("processor model",),
    )

    pointers = {
        item["json_pointer"]
        for item in index
    }

    assert (
        "/sections/audit/payload/processors/0/name"
        in pointers
    )


def test_bounded_index_uses_sibling_context_for_software_version():
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "software": [
            {
                "name": "Some Other Application",
                "version": "1.0",
            },
            {
                "name": "Google Chrome",
                "version": "151.0.7922.138",
            },
        ]
    }

    index = _bounded_evidence_index(
        data,
        requested_facts=("Chrome version",),
    )

    chrome = next(
        item
        for item in index
        if item["json_pointer"] == "/software/1/version"
    )

    assert "Google Chrome" in chrome["context"]
    assert "151.0.7922.138" not in chrome["context"]


def test_bounded_index_uses_sibling_context_for_zerotier_version():
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "software": [
            {
                "name": "ZeroTier One",
                "version": "1.14.2",
            }
        ]
    }

    index = _bounded_evidence_index(
        data,
        requested_facts=("ZeroTier version",),
    )

    candidate = next(
        item
        for item in index
        if item["json_pointer"] == "/software/0/version"
    )

    assert "ZeroTier One" in candidate["context"]
    assert "1.14.2" not in candidate["context"]


def test_bounded_index_fails_closed_without_relevant_candidate():
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "deviceType": {
            "category": "Desktop",
        },
        "provider_documentation": {
            "human": "https://example.test/help",
        },
    }

    assert (
        _bounded_evidence_index(
            data,
            requested_facts=("motherboard model",),
        )
        == ()
    )


def test_v3_lan_and_wan_use_generic_ip_value_shape_not_provider_field_mapping():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "device": {
            "firstAddress": "192.168.12.33",
            "secondAddress": "216.54.107.150",
        }
    }

    lan = _bounded_evidence_index(
        data,
        requested_facts=("LAN IP",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    wan = _bounded_evidence_index(
        data,
        requested_facts=("WAN IP",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    assert lan
    assert wan
    assert lan[0]["json_pointer"] == "/device/firstAddress"
    assert wan[0]["json_pointer"] == "/device/secondAddress"


def test_v3_motherboard_fails_closed_on_generic_system_model():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "systemInfo": {
                "manufacturer": "System manufacturer",
                "model": "System Product Name",
            }
        },
        requested_facts=("motherboard model",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    assert index == ()


def test_v3_free_disk_space_prefers_capacity_with_free_space_semantics():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "logicalDisks": [
                {
                    "diskIdentifier": "C:",
                    "freespace": 207787356160,
                    "size": 999192260608,
                }
            ]
        },
        requested_facts=("free disk space",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    assert index
    assert index[0]["json_pointer"] == "/logicalDisks/0/freespace"


def test_v3_disk_error_does_not_rank_unrelated_connector_error():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "patches": {
                "status": "unavailable",
                "error_type": "ConnectorTransportError",
                "error": "HTTP transport failed",
            },
            "alerts": [
                {
                    "source": "disk",
                    "type": "Error",
                    "description": "The device has a bad block.",
                }
            ],
        },
        requested_facts=("disk error evidence",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    pointers = tuple(
        item["json_pointer"]
        for item in index
    )

    assert "/patches/error_type" not in pointers
    assert "/patches/error" not in pointers
    assert "/alerts/0/description" in pointers


def test_v3_default_model_index_is_small():
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "items": [
            {
                "name": f"Item {index}",
                "version": f"{index}.0",
            }
            for index in range(100)
        ]
    }

    result = _bounded_evidence_index(
        data,
        requested_facts=("Item 50 version",),
    )

    assert len(result) <= 10


def test_evidence_reasoner_prompt_explicitly_allows_abstention_and_fact_contracts():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import (
        OllamaResourceEvidenceReasoner,
        OllamaStructuredJsonClient,
    )

    class Transport:
        def __init__(self):
            self.payload = None

        def request(self, **kwargs):
            self.payload = kwargs["json"]
            return {
                "message": {
                    "content": '{"locations":[]}'
                }
            }

    transport = Transport()

    reasoner = OllamaResourceEvidenceReasoner(
        OllamaStructuredJsonClient(
            transport=transport,
            model="local-test",
        ),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    result = reasoner.locate(
        requested_facts=("motherboard model",),
        data={
            "systemInfo": {
                "model": "System Product Name",
            }
        },
    )

    assert result == ()

    # No candidate means no model call is necessary.
    assert transport.payload is None

    transport = Transport()

    reasoner = OllamaResourceEvidenceReasoner(
        OllamaStructuredJsonClient(
            transport=transport,
            model="local-test",
        ),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    reasoner.locate(
        requested_facts=("total memory",),
        data={
            "memory": {
                "totalPhysicalMemory": 68629368832,
            }
        },
    )

    user_payload = json.loads(
        transport.payload["messages"][1]["content"]
    )

    assert (
        user_payload["fact_contracts"]["total memory"]["expected_shape"]
        == "capacity"
    )

    system_prompt = transport.payload["messages"][0]["content"]
    assert "empty locations array is correct" in system_prompt
    assert "preferred to guessing" in system_prompt



def test_v31_descriptive_fact_excludes_wrong_shaped_cpu_count():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "audit": {
                "systemInfo": {
                    "totalCpuCores": 8,
                },
                "processors": [
                    {
                        "name": "Intel Core i7-9700F",
                    }
                ],
            }
        },
        requested_facts=("processor model",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    pointers = tuple(
        item["json_pointer"]
        for item in index
    )

    assert "/audit/systemInfo/totalCpuCores" not in pointers
    assert "/audit/processors/0/name" in pointers
    assert index[0]["json_pointer"] == "/audit/processors/0/name"


def test_v31_collection_shape_does_not_create_semantic_relevance():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "attachedDevices": [
                {
                    "deviceType": "Storage",
                    "deviceName": "USB Device",
                }
            ],
            "other": [
                {
                    "deviceType": "Printer",
                    "deviceName": "DYMO LabelWriter 450",
                }
            ],
        },
        requested_facts=("printers",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    pointers = tuple(
        item["json_pointer"]
        for item in index
    )

    assert "/attachedDevices" not in pointers
    assert "/other/0/deviceName" in pointers


def test_v31_disk_primary_term_outranks_generic_event_log_hint():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "alerts": [
                {
                    "source": "EventLog",
                    "type": "Error",
                    "description": "Unexpected shutdown",
                },
                {
                    "source": "disk",
                    "type": "Error",
                    "description": "The device has a bad block.",
                },
            ]
        },
        requested_facts=("disk error evidence",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    assert index
    top_pointers = tuple(
        item["json_pointer"]
        for item in index[:3]
    )

    assert any(
        pointer.startswith("/alerts/1/")
        for pointer in top_pointers
    )



def test_v32_collection_ranking_prefers_matching_resource_identity():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "identity": {
            "hostname": "AOT-50282",
            "device_uid": "device-target",
        },
        "site": {
            "devices": [
                {
                    "hostname": "OTHER-PC",
                    "uid": "device-other",
                    "nics": [
                        {"instance": "Other NIC"},
                    ],
                },
                {
                    "hostname": "AOT-50282",
                    "uid": "device-target",
                    "nics": [
                        {"instance": "Target NIC"},
                    ],
                },
            ]
        },
    }

    index = _bounded_evidence_index(
        data,
        requested_facts=("network adapters",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    pointers = tuple(
        item["json_pointer"]
        for item in index
    )

    assert "/site/devices/1/nics" in pointers
    assert pointers.index("/site/devices/1/nics") < pointers.index(
        "/site/devices/0/nics"
    )


def test_v32_open_alert_leaf_collection_outranks_pages_wrapper():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "alerts_open": {
                "pages": [
                    {
                        "alerts": [
                            {
                                "priority": "Moderate",
                                "resolved": False,
                            }
                        ]
                    }
                ]
            }
        },
        requested_facts=("open alerts",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    pointers = tuple(
        item["json_pointer"]
        for item in index
    )

    assert "/alerts_open/pages/0/alerts" in pointers

    if "/alerts_open/pages" in pointers:
        assert (
            pointers.index("/alerts_open/pages/0/alerts")
            < pointers.index("/alerts_open/pages")
        )


def test_v32_specific_disk_error_context_outranks_disk_identifier():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "audit": {
                "logicalDisks": [
                    {
                        "diskIdentifier": "C:",
                    }
                ]
            },
            "alerts": [
                {
                    "source": "disk",
                    "type": "Error",
                    "description": "The device has a bad block.",
                    "logName": "system",
                }
            ],
        },
        requested_facts=("disk error evidence",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    assert index

    assert index[0]["json_pointer"].startswith(
        "/alerts/0/"
    )


def test_v32_motherboard_product_outranks_manufacturer():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "baseBoard": {
                "manufacturer": "ASUSTeK COMPUTER INC.",
                "product": "PRIME H370M-PLUS",
            }
        },
        requested_facts=("motherboard model",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    assert index
    assert index[0]["json_pointer"] == "/baseBoard/product"



def test_v33_open_alert_metadata_scalars_are_not_collection_candidates():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "alerts_open": {
                "status": "available",
                "method": "GET",
                "page_count": 1,
                "complete": True,
                "pages": [
                    {
                        "alerts": [
                            {
                                "priority": "Moderate",
                                "resolved": False,
                            }
                        ]
                    }
                ],
            }
        },
        requested_facts=("open alerts",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    pointers = {
        item["json_pointer"]
        for item in index
    }

    assert "/alerts_open/status" not in pointers
    assert "/alerts_open/method" not in pointers
    assert "/alerts_open/page_count" not in pointers
    assert "/alerts_open/complete" not in pointers
    assert "/alerts_open/pages/0/alerts" in pointers


def test_v33_network_collection_does_not_offer_boolean_probe_flags():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "identity": {
                "hostname": "AOT-50282",
                "device_uid": "target-device",
            },
            "device": {
                "hostname": "AOT-50282",
                "uid": "target-device",
                "networkProbe": False,
                "onboardedViaNetworkMonitor": False,
                "nics": [
                    {
                        "instance": "Ethernet Adapter",
                        "ipv4": "192.168.12.33",
                    }
                ],
            },
        },
        requested_facts=("network adapters",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    pointers = {
        item["json_pointer"]
        for item in index
    }

    assert "/device/nics" in pointers
    assert "/device/networkProbe" not in pointers
    assert "/device/onboardedViaNetworkMonitor" not in pointers


def test_v33_disk_error_description_outranks_log_metadata():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    index = _bounded_evidence_index(
        {
            "alerts": [
                {
                    "alertContext": {
                        "logName": "system",
                        "code": "7",
                        "type": "Error",
                        "source": "disk",
                        "description": (
                            "The device, \\\\Device\\\\Harddisk1\\\\DR2, "
                            "has a bad block."
                        ),
                    }
                }
            ]
        },
        requested_facts=("disk error evidence",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    assert index
    assert (
        index[0]["json_pointer"]
        == "/alerts/0/alertContext/description"
    )



def test_deterministic_identity_consensus_avoids_llm_for_target_lan_ip():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import (
        OllamaResourceEvidenceReasoner,
        OllamaStructuredJsonClient,
    )

    class NoModelTransport:
        def request(self, **kwargs):
            raise AssertionError(
                "unambiguous identity-bound evidence must not call the model"
            )

    reasoner = OllamaResourceEvidenceReasoner(
        client=OllamaStructuredJsonClient(
            transport=NoModelTransport(),
            model="must-not-run",
        ),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    data = {
        "identity": {
            "discovery_record": {
                "hostname": "AOT-50282",
                "uid": "target-uid",
                "intIpAddress": "192.168.12.33",
            }
        },
        "device": {
            "hostname": "AOT-50282",
            "uid": "target-uid",
            "intIpAddress": "192.168.12.33",
        },
        "site": {
            "devices": [
                {
                    "hostname": "OTHER",
                    "uid": "other-uid",
                    "intIpAddress": "192.168.12.1",
                }
            ]
        },
    }

    locations = reasoner.locate(
        requested_facts=("LAN IP",),
        data=data,
    )

    assert locations == (
        {
            "requested_fact": "LAN IP",
            "json_pointer":
                "/identity/discovery_record/intIpAddress",
        },
    )


def test_deterministic_collection_prefers_relevant_complete_list():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import (
        OllamaResourceEvidenceReasoner,
        OllamaStructuredJsonClient,
    )

    class NoModelTransport:
        def request(self, **kwargs):
            raise AssertionError(
                "unambiguous collection must not call the model"
            )

    reasoner = OllamaResourceEvidenceReasoner(
        client=OllamaStructuredJsonClient(
            transport=NoModelTransport(),
            model="must-not-run",
        ),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    locations = reasoner.locate(
        requested_facts=("graphics adapter",),
        data={
            "audit": {
                "videoBoards": [
                    {
                        "displayAdapter":
                            "NVIDIA GeForce GT 710",
                    }
                ]
            }
        },
    )

    assert locations == (
        {
            "requested_fact":
                "graphics adapter",
            "json_pointer":
                "/audit/videoBoards",
        },
    )


def test_deterministic_filtered_collection_aggregates_matching_item_fields():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import (
        OllamaResourceEvidenceReasoner,
        OllamaStructuredJsonClient,
    )

    class NoModelTransport:
        def request(self, **kwargs):
            raise AssertionError(
                "structurally consistent printer collection must not call model"
            )

    reasoner = OllamaResourceEvidenceReasoner(
        client=OllamaStructuredJsonClient(
            transport=NoModelTransport(),
            model="must-not-run",
        ),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    locations = reasoner.locate(
        requested_facts=("printers",),
        data={
            "attachedDevices": [
                {
                    "deviceType": "Printer",
                    "deviceName":
                        "DYMO LabelWriter 450",
                },
                {
                    "deviceType": "Printer",
                    "deviceName":
                        "Microsoft IPP Class Driver",
                },
                {
                    "deviceType": "Storage",
                    "deviceName":
                        "USB Mass Storage Device",
                },
            ]
        },
    )

    assert locations == (
        {
            "requested_fact": "printers",
            "json_pointer":
                "/attachedDevices/0/deviceName",
        },
        {
            "requested_fact": "printers",
            "json_pointer":
                "/attachedDevices/1/deviceName",
        },
    )


def test_deterministic_target_nic_collection_avoids_llm():
    from orchestrator.canonical_fact_vocabulary import (
        DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    from orchestrator.ollama_reasoning import (
        OllamaResourceEvidenceReasoner,
        OllamaStructuredJsonClient,
    )

    class NoModelTransport:
        def request(self, **kwargs):
            raise AssertionError(
                "identity-bound NIC collection must not call model"
            )

    target_nics = [
        {
            "instance": "Ethernet Adapter",
            "ipv4": "192.168.12.33",
        },
        {
            "instance": "ZeroTier Virtual Port",
            "ipv4": "192.168.193.90",
        },
    ]

    reasoner = OllamaResourceEvidenceReasoner(
        client=OllamaStructuredJsonClient(
            transport=NoModelTransport(),
            model="must-not-run",
        ),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    locations = reasoner.locate(
        requested_facts=("network adapters",),
        data={
            "identity": {
                "discovery_record": {
                    "hostname": "AOT-50282",
                    "uid": "target-uid",
                }
            },
            "site": {
                "devices": [
                    {
                        "hostname": "OTHER",
                        "uid": "other-uid",
                        "nics": [
                            {
                                "instance":
                                    "Other Adapter",
                            }
                        ],
                    },
                    {
                        "hostname": "AOT-50282",
                        "uid": "target-uid",
                        "nics": target_nics,
                    },
                ]
            },
        },
    )

    assert locations == (
        {
            "requested_fact":
                "network adapters",
            "json_pointer":
                "/site/devices/1/nics",
        },
    )
