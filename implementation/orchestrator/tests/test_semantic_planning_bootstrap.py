from orchestrator.semantic_planning_bootstrap import ProviderNeutralIntentContextBootstrapper


def test_bootstrapper_requests_semantic_and_capability_context_from_intent():
    requests = ProviderNeutralIntentContextBootstrapper().requests_for(
        intent={
            "human_text": "What CPU does AOT-EXAMPLE have?",
            "resource_type": "endpoint",
            "requested_facts": ("processor model",),
            "permission_mode": "observe",
        }
    )
    assert [item.view for item in requests] == ["semantic_knowledge", "capability_registry"]
    assert requests[0].query == {"query": "processor model"}
    assert requests[1].query == {"query": "endpoint"}


def test_bootstrapper_never_adds_provider_or_execution_fields():
    requests = ProviderNeutralIntentContextBootstrapper().requests_for(
        intent={
            "resource_type": "endpoint",
            "requested_facts": ("total memory",),
        }
    )
    rendered = repr(requests).casefold()
    for forbidden in ("provider_name", "connector_name", "tool_name", "credential", "command"):
        assert forbidden not in rendered
