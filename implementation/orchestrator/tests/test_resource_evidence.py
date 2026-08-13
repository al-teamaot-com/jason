from __future__ import annotations

import pytest

from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.resource_evidence import (
    GovernedResourceEvidenceInterpreter,
    GovernedTeamsResourceResponseRenderer,
)
from orchestrator.teams_conversation_flow import ConversationIntent


class Reasoner:
    def __init__(self, proposals):
        self.proposals = proposals
        self.calls = []

    def locate(self, *, requested_facts, data):
        self.calls.append((requested_facts, data))
        return self.proposals


def result(
    *,
    data=None,
    provider="datto_rmm",
    status=OrchestrationStatus.SUCCEEDED,
    capability_name="endpoint.device.search",
):
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name=capability_name,
        status=status,
        stage=(ExecutionStage.COMPLETED if status is OrchestrationStatus.SUCCEEDED else ExecutionStage.FAILED),
        reason_codes=("capability_completed" if status is OrchestrationStatus.SUCCEEDED else "failed",),
        resolution=None,
        output={
            "provider": provider,
            "data": data
            if data is not None
            else {
                "devices": [
                    {
                        "hostname": "AOT-50282",
                        "lastUser": "AOT\\example.user",
                        "operatingSystem": "Windows 11 Pro",
                    }
                ]
            },
        },
        attempts=1,
        provider_id=provider,
    )


def canonical_search_data(*matches, provider_data=None):
    return {
        "resource_matches": list(matches),
        "provider_data": provider_data
        if provider_data is not None
        else {
            "devices": [
                {
                    "uid": "device-uid-1",
                    "hostname": "AOT-50282",
                    "lastUser": "AOT\\example.user",
                }
            ]
        },
    }


def intent(*facts, hostname="AOT-50282", site=None):
    arguments = {
        "hostname": hostname,
        "requested_facts": facts or ("last logged in user",),
    }
    if site is not None:
        arguments["site"] = site
    return ConversationIntent(
        capability_name="endpoint.device.search",
        arguments=arguments,
        execution_mode="deterministic",
        permission_mode="observe",
    )


def registry_intent(*facts, name="Jason Runtime Service"):
    return ConversationIntent(
        capability_name="system.registry.search",
        arguments={
            "name": name,
            "requested_facts": facts or ("resource_id",),
        },
        execution_mode="deterministic",
        permission_mode="observe",
    )



class FakeEvidenceReasoner:
    def __init__(self, proposals):
        self.proposals = tuple(proposals)

    def locate(self, *, requested_facts, data):
        return self.proposals

def test_reasoner_identifies_path_but_actual_provider_value_becomes_the_assertion():
    reasoner = Reasoner(
        [
            {
                "requested_fact": "last logged in user",
                "json_pointer": "/devices/0/lastUser",
                # Deliberately untrusted/hallucinated value: interpreter ignores it.
                "value": "WRONG\\user",
            }
        ]
    )
    interpreter = GovernedResourceEvidenceInterpreter(reasoner)

    facts = interpreter.interpret(
        result=result(),
        requested_facts=("last logged in user",),
    )

    assert facts[0].value == "AOT\\example.user"
    assert facts[0].json_pointer == "/devices/0/lastUser"


def test_renderer_returns_only_verified_requested_fact_after_unique_identity_resolution():
    reasoner = Reasoner(
        [
            {
                "requested_fact": "last logged in user",
                "json_pointer": "/provider_data/devices/0/lastUser",
            }
        ]
    )
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )
    data = canonical_search_data(
        {
            "resource_id": "device-uid-1",
            "hostname": "AOT-50282",
            "site": "Customer-A",
        }
    )

    text = renderer.render(result(data=data), intent("last logged in user"))

    assert text == (
        "AOT-50282 — last logged in user: AOT\\example.user. Source: datto_rmm."
    )
    assert reasoner.calls


def test_unique_system_registry_resource_id_is_rendered_without_language_reasoning():
    reasoner = Reasoner(
        [
            {
                "requested_fact": "resource_id",
                "json_pointer": "/evidence/resource_matches/0/resource_id",
            }
        ]
    )
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )
    data = {
        "match_count": 1,
        "resource_matches": [
            {
                "resource_id": "component.jason-runtime",
                "registry_id": "component.jason-runtime",
                "display_name": "Jason Runtime Service",
                "lifecycle_status": "verified",
            }
        ],
    }

    text = renderer.render(
        result(
            data=data,
            provider="system_registry",
            capability_name="system.registry.search",
        ),
        registry_intent("resource_id"),
    )

    assert text == (
        "Jason Runtime Service — resource_id: component.jason-runtime. "
        "Source: system_registry."
    )
    assert reasoner.calls == []


def test_direct_fact_name_normalization_accepts_human_spacing_without_inference():
    reasoner = Reasoner([])
    interpreter = GovernedResourceEvidenceInterpreter(reasoner)
    data = {
        "resource_matches": [
            {
                "resource_id": "component.jason-runtime",
            }
        ]
    }

    facts = interpreter.interpret(
        result=result(data=data, provider="system_registry"),
        requested_facts=("resource id",),
    )

    assert facts[0].value == "component.jason-runtime"
    assert facts[0].json_pointer == "/resource_matches/0/resource_id"
    assert reasoner.calls == []


def test_ambiguous_endpoint_name_never_selects_first_result_or_exposes_candidate_details():
    reasoner = Reasoner([])
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )
    data = canonical_search_data(
        {
            "resource_id": "device-uid-a",
            "hostname": "SERVER",
            "site": "Customer-A",
        },
        {
            "resource_id": "device-uid-b",
            "hostname": "SERVER",
            "site": "Customer-B",
        },
    )

    text = renderer.render(result(data=data), intent(hostname="SERVER"))

    assert text == (
        "SERVER is ambiguous: 2 managed endpoints matched. "
        "Please specify the site/client or a durable resource identifier. "
        "No device was selected. Source: datto_rmm."
    )
    assert "Customer-A" not in text
    assert "Customer-B" not in text
    assert "device-uid" not in text
    assert reasoner.calls == []


def test_no_endpoint_match_returns_deterministic_no_match_without_reasoner():
    reasoner = Reasoner([])
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )

    text = renderer.render(
        result(data=canonical_search_data()),
        intent(hostname="MISSING-SERVER"),
    )

    assert text == (
        "MISSING-SERVER — no matching managed endpoint was found. Source: datto_rmm."
    )
    assert reasoner.calls == []


def test_unique_endpoint_match_requires_durable_resource_identity():
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(Reasoner([]))
    )
    data = canonical_search_data({"hostname": "SERVER", "site": "Customer-A"})

    with pytest.raises(LookupError, match="durable resource identity"):
        renderer.render(result(data=data), intent(hostname="SERVER"))


def test_search_result_missing_canonical_matches_fails_closed():
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(Reasoner([]))
    )

    with pytest.raises(RuntimeError, match="canonical resource_matches"):
        renderer.render(result(), intent())


def test_evidence_reasoner_cannot_assert_an_unrequested_provider_field():
    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner(
            [
                {
                    "requested_fact": "operating system",
                    "json_pointer": "/devices/0/operatingSystem",
                }
            ]
        )
    )

    with pytest.raises(PermissionError, match="unrequested fact"):
        interpreter.interpret(
            result=result(),
            requested_facts=("last logged in user",),
        )


def test_missing_evidence_pointer_fails_closed():
    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner(
            [
                {
                    "requested_fact": "last logged in user",
                    "json_pointer": "/devices/0/notARealField",
                }
            ]
        )
    )

    with pytest.raises(LookupError, match="does not exist"):
        interpreter.interpret(
            result=result(),
            requested_facts=("last logged in user",),
        )


def test_all_requested_facts_must_be_supported_before_response():
    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner(
            [
                {
                    "requested_fact": "last logged in user",
                    "json_pointer": "/devices/0/lastUser",
                }
            ]
        )
    )

    with pytest.raises(LookupError, match="did not support all requested facts"):
        interpreter.interpret(
            result=result(),
            requested_facts=("last logged in user", "operating system"),
        )


def test_inconsistent_provider_provenance_fails_closed():
    bad = result()
    bad = OrchestrationResult(
        execution_id=bad.execution_id,
        correlation_id=bad.correlation_id,
        capability_name=bad.capability_name,
        status=bad.status,
        stage=bad.stage,
        reason_codes=bad.reason_codes,
        resolution=None,
        output={"provider": "other", "data": bad.output["data"]},
        attempts=bad.attempts,
        provider_id="datto_rmm",
    )
    interpreter = GovernedResourceEvidenceInterpreter(Reasoner([]))

    with pytest.raises(RuntimeError, match="provenance"):
        interpreter.interpret(
            result=bad,
            requested_facts=("last logged in user",),
        )


def test_collection_renderer_summarizes_alert_without_dumping_raw_diagnostics():
    reasoner = Reasoner(
        [
            {
                "requested_fact": "severity",
                "json_pointer": "/provider_data/alerts/0/priority",
            },
        ]
    )

    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )

    data = {
        "resource_matches": [
            {
                "resource_id": "device-uid-1",
                "hostname": "AOT-50282",
                "site": "Atlantic Office Machines",
            }
        ],
        "resolved_resource_id": "device-uid-1",
        "provider_data": {
            "alerts": [
                {
                    "priority": "Moderate",
                    "resolved": False,
                    "diagnostics": "THIS RAW DIAGNOSTIC MUST NOT BE RETURNED",
                    "alertContext": {
                        "samples": {
                            "Status": (
                                "Unhealthy - Local user changes detected; "
                                "AddedUsers=CodexSandboxOffline,CodexSandboxOnline"
                            )
                        }
                    },
                }
            ]
        },
    }

    alert_intent = ConversationIntent(
        capability_name="endpoint.alert.search",
        arguments={
            "hostname": "AOT-50282",
            "requested_facts": ("alerts", "severity"),
        },
        execution_mode="deterministic",
        permission_mode="observe",
    )

    text = renderer.render(
        result(
            data=data,
            capability_name="endpoint.alert.search",
        ),
        alert_intent,
    )

    assert text.startswith("AOT-50282 — 1 alert found.")
    assert "Moderate" in text
    assert "Local user changes detected" in text
    assert "CodexSandboxOffline" in text
    assert "THIS RAW DIAGNOSTIC MUST NOT BE RETURNED" not in text
    assert '"alertContext"' not in text
    assert "Source: datto_rmm." in text
    assert reasoner.calls
    assert reasoner.calls[0][0] == ("severity",)


def test_empty_collection_renderer_answers_no_items_concisely():
    reasoner = Reasoner(
        [
            {
                "requested_fact": "alerts",
                "json_pointer": "/provider_data/alerts",
            }
        ]
    )

    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )

    data = {
        "resource_matches": [
            {
                "resource_id": "device-uid-1",
                "hostname": "AOT-50282",
            }
        ],
        "resolved_resource_id": "device-uid-1",
        "provider_data": {"alerts": []},
    }

    alert_intent = ConversationIntent(
        capability_name="endpoint.alert.search",
        arguments={
            "hostname": "AOT-50282",
            "requested_facts": ("alerts",),
        },
        execution_mode="deterministic",
        permission_mode="observe",
    )

    text = renderer.render(
        result(
            data=data,
            capability_name="endpoint.alert.search",
        ),
        alert_intent,
    )

    assert text == (
        "AOT-50282 — no alerts found. Source: datto_rmm."
    )


def test_collection_renderer_bounds_large_results():
    reasoner = Reasoner(
        [
            {
                "requested_fact": "software",
                "json_pointer": "/provider_data/software",
            }
        ]
    )

    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )

    data = {
        "resource_matches": [
            {
                "resource_id": "device-uid-1",
                "hostname": "AOT-50282",
            }
        ],
        "resolved_resource_id": "device-uid-1",
        "provider_data": {
            "software": [
                {"name": f"Application {number}", "version": f"{number}.0"}
                for number in range(1, 9)
            ]
        },
    }

    software_intent = ConversationIntent(
        capability_name="endpoint.software.search",
        arguments={
            "hostname": "AOT-50282",
            "requested_facts": ("software",),
        },
        execution_mode="deterministic",
        permission_mode="observe",
    )

    text = renderer.render(
        result(
            data=data,
            capability_name="endpoint.software.search",
        ),
        software_intent,
    )

    assert "8 software found." in text
    assert "Application 1" in text
    assert "Application 5" in text
    assert "Application 6" not in text
    assert "+3 more" in text


def test_provider_data_collection_is_selected_directly_without_reasoner():
    reasoner = Reasoner([])

    interpreter = GovernedResourceEvidenceInterpreter(reasoner)

    data = {
        "resource_matches": [
            {
                "resource_id": "device-uid-1",
                "hostname": "AOT-50282",
            }
        ],
        "resolved_resource_id": "device-uid-1",
        "provider_data": {
            "software": [
                {"name": "Application 1", "version": "1.0"},
                {"name": "Application 2", "version": "2.0"},
            ]
        },
    }

    facts = interpreter.interpret(
        result=result(
            data=data,
            capability_name="endpoint.software.search",
        ),
        requested_facts=("software",),
    )

    assert len(facts) == 1
    assert facts[0].json_pointer == "/provider_data/software"
    assert len(facts[0].value) == 2
    assert reasoner.calls == []


def test_provider_data_alert_collection_is_selected_directly_without_reasoner():
    reasoner = Reasoner([])

    interpreter = GovernedResourceEvidenceInterpreter(reasoner)

    data = {
        "resource_matches": [
            {
                "resource_id": "device-uid-1",
                "hostname": "AOT-50282",
            }
        ],
        "resolved_resource_id": "device-uid-1",
        "provider_data": {
            "alerts": [
                {
                    "priority": "Moderate",
                    "message": "Test alert",
                }
            ]
        },
    }

    facts = interpreter.interpret(
        result=result(
            data=data,
            capability_name="endpoint.alert.search",
        ),
        requested_facts=("alerts",),
    )

    assert facts[0].json_pointer == "/provider_data/alerts"
    assert len(facts[0].value) == 1
    assert reasoner.calls == []


def test_top_level_site_collection_is_selected_directly_without_reasoner():
    reasoner = Reasoner([])

    interpreter = GovernedResourceEvidenceInterpreter(reasoner)

    data = {
        "pageDetails": {
            "count": 2,
            "totalCount": 46,
        },
        "sites": [
            {
                "uid": "site-1",
                "name": "Atlantic Office Machines",
            },
            {
                "uid": "site-2",
                "name": "Autotask Corporation",
            },
        ],
    }

    facts = interpreter.interpret(
        result=result(
            data=data,
            capability_name="management.site.search",
        ),
        requested_facts=("sites",),
    )

    assert len(facts) == 1
    assert facts[0].json_pointer == "/sites"
    assert len(facts[0].value) == 2
    assert reasoner.calls == []


def test_top_level_sites_render_as_bounded_collection():
    reasoner = Reasoner([])

    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )

    data = {
        "pageDetails": {
            "count": 6,
            "totalCount": 46,
        },
        "sites": [
            {"name": f"Site {number}", "uid": f"site-{number}"}
            for number in range(1, 7)
        ],
    }

    site_intent = ConversationIntent(
        capability_name="management.site.search",
        arguments={
            "requested_facts": ("sites",),
        },
        execution_mode="deterministic",
        permission_mode="observe",
    )

    text = renderer.render(
        result(
            data=data,
            capability_name="management.site.search",
        ),
        site_intent,
    )

    assert "6 sites found." in text
    assert "Site 1" in text
    assert "Site 5" in text
    assert "Site 6" not in text
    assert "+1 more" in text
    assert reasoner.calls == []


def test_complete_enumeration_renders_every_collection_item():
    reasoner = Reasoner([])

    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )

    data = {
        "pageDetails": {
            "count": 6,
            "totalCount": 6,
        },
        "sites": [
            {"name": f"Site {number}"}
            for number in range(1, 7)
        ],
    }

    intent = ConversationIntent(
        capability_name="management.site.search",
        arguments={
            "requested_facts": ("sites",),
            "result_intent": "enumerate",
            "completeness_requirement": "complete",
        },
        execution_mode="deterministic",
        permission_mode="observe",
    )

    text = renderer.render(
        result(
            data=data,
            capability_name="management.site.search",
        ),
        intent,
    )

    assert "6 sites found:" in text
    for number in range(1, 7):
        assert f"- Site {number}" in text
    assert "+1 more" not in text


def test_processor_model_rejects_numeric_count_as_wrong_shape():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY

    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner([
            {
                "requested_fact": "processor model",
                "json_pointer": "/provider_data/processors/0/logicalProcessors",
            }
        ]),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    data = result()
    data = OrchestrationResult(
        execution_id=data.execution_id,
        correlation_id=data.correlation_id,
        capability_name=data.capability_name,
        status=data.status,
        stage=data.stage,
        reason_codes=data.reason_codes,
        resolution=data.resolution,
        output={
            "provider": "datto_rmm",
            "data": {"provider_data": {"processors": [{"logicalProcessors": 8}]}},
        },
        attempts=data.attempts,
        provider_id="datto_rmm",
    )
    with pytest.raises(LookupError, match="wrong shape"):
        interpreter.interpret(result=data, requested_facts=("processor model",))


def test_processor_model_accepts_descriptive_provider_value():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY

    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner([
            {
                "requested_fact": "processor model",
                "json_pointer": "/provider_data/processors/0/name",
            }
        ]),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    data = result()
    data = OrchestrationResult(
        execution_id=data.execution_id,
        correlation_id=data.correlation_id,
        capability_name=data.capability_name,
        status=data.status,
        stage=data.stage,
        reason_codes=data.reason_codes,
        resolution=data.resolution,
        output={
            "provider": "datto_rmm",
            "data": {"provider_data": {"processors": [{"name": "Intel Core i7"}]}},
        },
        attempts=data.attempts,
        provider_id="datto_rmm",
    )
    facts = interpreter.interpret(result=data, requested_facts=("processor model",))
    assert facts[0].value == "Intel Core i7"


def test_semantic_context_rejects_unrelated_descriptive_version():
    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=FakeEvidenceReasoner([
            {
                "requested_fact": "operating system display version",
                "json_pointer": "/provider_data/health/version",
            }
        ]),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    orchestration_result = result(
        data={
            "provider_data": {
                "health": {
                    "version": "Unhealthy - Local user changes detected",
                }
            }
        }
    )
    with pytest.raises(LookupError, match="outside required semantic context"):
        interpreter.interpret(
            result=orchestration_result,
            requested_facts=("operating system display version",),
            evidence_contexts={
                "operating system display version": ("operating_system", "windows_release")
            },
        )


def test_semantic_context_accepts_operating_system_release_path():
    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=FakeEvidenceReasoner([
            {
                "requested_fact": "operating system display version",
                "json_pointer": "/provider_data/operating_system/windows_release/display_version",
            }
        ]),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    orchestration_result = result(
        data={
            "provider_data": {
                "operating_system": {
                    "windows_release": {
                        "display_version": "24H2",
                    }
                }
            }
        }
    )
    facts = interpreter.interpret(
        result=orchestration_result,
        requested_facts=("operating system display version",),
        evidence_contexts={
            "operating system display version": ("operating_system", "windows_release")
        },
    )
    assert facts[0].value == "24H2"


def test_semantic_adapter_processor_fact_resolves_deterministically_before_reasoner():
    class NoEvidenceReasoner:
        def locate(self, *, requested_facts, data):
            raise AssertionError("semantic adapter fact should resolve without language reasoning")

    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=NoEvidenceReasoner(),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    orchestration_result = result(
        data={
            "provider_data": {
                "processor": "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz",
                "semantic_evidence": {
                    "processor": {
                        "hardware_inventory": {
                            "processor_model": "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz",
                        }
                    }
                },
            }
        }
    )

    facts = interpreter.interpret(
        result=orchestration_result,
        requested_facts=("processor model",),
        evidence_contexts={
            "processor model": ("processor", "hardware_inventory"),
        },
    )

    assert len(facts) == 1
    assert facts[0].value == "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz"
    assert facts[0].json_pointer == "/provider_data/semantic_evidence/processor/hardware_inventory/processor_model"


def test_raw_processor_field_cannot_bypass_required_semantic_context():
    class WrongPathReasoner:
        def locate(self, *, requested_facts, data):
            return ({
                "requested_fact": "processor model",
                "json_pointer": "/provider_data/processor",
            },)

    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=WrongPathReasoner(),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    orchestration_result = result(
        data={
            "provider_data": {
                "processor": "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz",
            }
        }
    )

    import pytest
    with pytest.raises(LookupError, match="outside required semantic context"):
        interpreter.interpret(
            result=orchestration_result,
            requested_facts=("processor model",),
            evidence_contexts={
                "processor model": ("processor", "hardware_inventory"),
            },
        )


def test_renderer_reports_unavailable_fact_without_generic_failure():
    from orchestrator.resource_evidence import GovernedTeamsResourceResponseRenderer
    from orchestrator.teams_conversation_flow import ConversationIntent

    class MissingEvidenceInterpreter:
        def interpret(self, **kwargs):
            raise LookupError("requested facts were not located in governed provider evidence")

    renderer = GovernedTeamsResourceResponseRenderer(interpreter=MissingEvidenceInterpreter())
    response = renderer.render(
        result=result(data={"resource_matches": [{"resource_id": "device-1", "hostname": "AOT-50282"}], "provider_data": {}}),
        intent=ConversationIntent(
            capability_name="endpoint.device.search",
            arguments={
                "hostname": "AOT-50282",
                "requested_facts": ("operating system display version",),
            },
        ),
    )
    assert "operating system display version: unavailable" in response
    assert "Source:" in response


def test_renderer_unavailable_response_does_not_invent_display_version_value():
    from orchestrator.resource_evidence import GovernedTeamsResourceResponseRenderer
    from orchestrator.teams_conversation_flow import ConversationIntent

    class MissingEvidenceInterpreter:
        def interpret(self, **kwargs):
            raise LookupError("provider evidence is outside required semantic context")

    renderer = GovernedTeamsResourceResponseRenderer(interpreter=MissingEvidenceInterpreter())
    response = renderer.render(
        result=result(data={"resource_matches": [{"resource_id": "device-1", "hostname": "AOT-50282"}], "provider_data": {"displayVersion": "4.4.11965.11965"}}),
        intent=ConversationIntent(
            capability_name="endpoint.device.search",
            arguments={
                "hostname": "AOT-50282",
                "requested_facts": ("operating system display version",),
            },
        ),
    )
    assert "unavailable from the current governed provider evidence" in response
    assert "4.4.11965.11965" not in response


def test_approved_semantic_mapping_projects_real_provider_field_without_reasoner_mapping():
    from orchestrator.semantic_mapping_evidence import (
        GovernedSemanticMappingEvidenceProjector,
    )
    from orchestrator.semantic_mapping_registry import (
        ApprovedSemanticMapping,
        SemanticMappingRegistry,
    )

    class NoSemanticGuessReasoner:
        def locate(self, *, requested_facts, data):
            return ()

    mapping = ApprovedSemanticMapping(
        mapping_id="example-display-version",
        version=1,
        provider_id="example_provider",
        canonical_fact="operating system display version",
        provider_schema="Device",
        provider_field="displayVersion",
        resource_authority="managed_endpoint",
        approval_status="approved",
        approved_by="technology-steward",
        approval_basis="authoritative cross-source evidence",
        openapi_source_reference="openapi:test",
        semantic_source_reference="help:test",
        capability_names=("endpoint.device.search",),
        active=True,
    )

    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=NoSemanticGuessReasoner(),
        semantic_mapping_projector=GovernedSemanticMappingEvidenceProjector(
            registry=SemanticMappingRegistry((mapping,))
        ),
    )

    result = OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="endpoint.device.search",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("capability_completed",),
        resolution=None,
        provider_id="example_provider",
        output={
            "provider": "example_provider",
            "data": {
                "resource_matches": [
                    {
                        "resource_id": "device-1",
                        "hostname": "EXAMPLE-1",
                    }
                ],
                "resolved_resource_id": "device-1",
                "provider_data": {
                    "hostname": "EXAMPLE-1",
                    "displayVersion": "24H2",
                },
            },
        },
    )

    facts = interpreter.interpret(
        result=result,
        requested_facts=("operating system display version",),
    )

    assert len(facts) == 1
    assert facts[0].value == "24H2"
    assert (
        facts[0].json_pointer
        == "/provider_data/semantic_evidence/operating_system_display_version"
    )
