from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from orchestrator.conversation_resource_intent import (
    GovernedResourceConversationIntentResolver,
    MetadataFirstResourceInquiryInterpreter,
    ReasonedResourceInquiryInterpreter,
)
from orchestrator.resource_capability_catalog import register_endpoint_resource_foundation
from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
from orchestrator.teams_conversation_flow import BoundConversationPrincipal


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


class Reasoner:
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = []

    def propose(self, *, text, organization_id, client_id):
        self.calls.append(
            {
                "text": text,
                "organization_id": organization_id,
                "client_id": client_id,
            }
        )
        return self.proposal


def principal():
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
    )


def resolver(proposal):
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
    )
    reasoner = Reasoner(proposal)
    return (
        GovernedResourceConversationIntentResolver(
            interpreter=ReasonedResourceInquiryInterpreter(reasoner),
            planner=GovernedResourceInquiryPlanner(
                registry=capabilities,
                reasoner=MetadataResourceCapabilityReasoner(),
            ),
        ),
        reasoner,
    )


def test_human_question_becomes_resource_inquiry_then_broad_capability():
    intent_resolver, reasoner = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-50282"},
            "requested_facts": ["last logged in user"],
        }
    )

    intent = intent_resolver.resolve(
        text="Who is logged into AOT-50282?",
        principal=principal(),
    )

    assert intent is not None
    assert intent.capability_name == "endpoint.device.search"
    assert intent.arguments == {
        "hostname": "AOT-50282",
        "requested_facts": ("last logged in user",),
    }
    assert intent.execution_mode == "deterministic"
    assert intent.permission_mode == "observe"
    assert reasoner.calls == [
        {
            "text": "Who is logged into AOT-50282?",
            "organization_id": "aot",
            "client_id": None,
        }
    ]
    # The language reasoner never receives a Datto/provider selection.
    assert "datto" not in repr(reasoner.calls).lower()


def test_language_reasoner_cannot_select_provider_or_capability():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-50282"},
            "requested_facts": ["last logged in user"],
            "provider": "datto_rmm",
            "capability_name": "datto_rmm.device.search",
        }
    )

    with pytest.raises(PermissionError, match="provider/execution selection"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_language_reasoner_cannot_smuggle_provider_through_selector():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {
                "hostname": "AOT-50282",
                "provider_id": "datto_rmm",
            },
            "requested_facts": ["last logged in user"],
        }
    )

    with pytest.raises(PermissionError, match="resource selector"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_language_reasoner_cannot_smuggle_nested_selector_operators():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": {"exact": "AOT-50282"}},
            "requested_facts": ["last logged in user"],
        }
    )

    with pytest.raises(ValueError, match="scalar strings"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_identifier_prefix_cannot_be_inferred_as_site_or_tenant_scope():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {
                "hostname": "AOT-50282",
                "site": "aot",
            },
            "requested_facts": ["last logged in user"],
        }
    )

    with pytest.raises(ValueError, match="grounded in identifiers explicitly supplied"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_explicit_site_selector_is_allowed_when_human_supplies_it():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {
                "hostname": "AOT-50282",
                "site": "Customer-B",
            },
            "requested_facts": ["last logged in user"],
        }
    )

    intent = intent_resolver.resolve(
        text="Who is logged into AOT-50282 at site Customer-B?",
        principal=principal(),
    )

    assert intent is not None
    assert intent.arguments["site"] == "Customer-B"


def test_language_reasoner_cannot_turn_read_question_into_execute_authority():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-50282"},
            "requested_facts": ["last logged in user"],
            "permission_mode": "execute",
        }
    )

    with pytest.raises(PermissionError, match="read-only"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_unrecognized_language_can_return_no_resource_inquiry():
    intent_resolver, _ = resolver(None)

    assert (
        intent_resolver.resolve(
            text="Tell me a joke.",
            principal=principal(),
        )
        is None
    )

def test_resource_interpreter_allows_empty_selector_for_broad_read_query() -> None:
    from orchestrator.conversation_resource_intent import ReasonedResourceInquiryInterpreter

    class EmptySelectorReasoner:
        def propose(self, **kwargs):
            return {
                "resource_type": "alert",
                "resource_selector": {},
                "requested_facts": ["open alerts"],
                "execution_mode": "deterministic",
                "permission_mode": "observe",
            }

    interpreter = ReasonedResourceInquiryInterpreter(
        reasoner=EmptySelectorReasoner()
    )

    principal = type(
        "Principal",
        (),
        {
            "organization_id": "aot",
            "client_id": None,
        },
    )()

    inquiry = interpreter.interpret(
        text="Show me open alerts",
        principal=principal,
    )

    assert inquiry is not None
    assert inquiry.resource_selector == {}
    assert inquiry.permission_mode == "observe"


def test_metadata_first_interpreter_resolves_unique_management_collection_without_reasoner():
    class Fallback:
        def __init__(self):
            self.calls = []

        def interpret(self, *, text, principal):
            self.calls.append((text, principal))
            raise AssertionError("fallback reasoner must not be called")

    fallback = Fallback()

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "management.site.search",
                "resource_types": ("management_site",),
                "selector_keys": ("name", "site", "site_id"),
                "fact_hints": (
                    "site",
                    "sites",
                    "client site",
                    "managed site",
                    "site name",
                    "site identifier",
                    "site details",
                ),
                "selector_required": False,
            },
        ),
        fallback=fallback,
    )

    inquiry = interpreter.interpret(
        text="What sites are in Datto RMM?",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.resource_type == "management_site"
    assert inquiry.resource_selector == {}
    assert inquiry.requested_facts == ("sites",)
    assert inquiry.execution_mode == "deterministic"
    assert inquiry.permission_mode == "observe"
    assert fallback.calls == []


def test_metadata_first_interpreter_falls_back_when_selector_is_required():
    class Fallback:
        def __init__(self):
            self.calls = []

        def interpret(self, *, text, principal):
            self.calls.append((text, principal))
            return None

    fallback = Fallback()

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "endpoint.software.search",
                "resource_types": ("endpoint_software", "endpoint"),
                "selector_keys": ("hostname", "name", "resource_id"),
                "fact_hints": ("software", "installed software"),
                "selector_required": True,
            },
        ),
        fallback=fallback,
    )

    result = interpreter.interpret(
        text="What software is installed on AOT-50282?",
        principal=principal(),
    )

    assert result is None
    assert len(fallback.calls) == 1


def test_metadata_first_interpreter_falls_back_on_ambiguous_metadata_match():
    class Fallback:
        def __init__(self):
            self.calls = []

        def interpret(self, *, text, principal):
            self.calls.append((text, principal))
            return None

    fallback = Fallback()

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "one",
                "resource_types": ("one",),
                "selector_keys": (),
                "fact_hints": ("status",),
                "selector_required": False,
            },
            {
                "capability_name": "two",
                "resource_types": ("two",),
                "selector_keys": (),
                "fact_hints": ("status",),
                "selector_required": False,
            },
        ),
        fallback=fallback,
    )

    result = interpreter.interpret(
        text="Show status",
        principal=principal(),
    )

    assert result is None
    assert len(fallback.calls) == 1


def test_metadata_first_interpreter_resolves_unique_management_collection_without_reasoner():
    class Fallback:
        def __init__(self):
            self.calls = []

        def interpret(self, *, text, principal):
            self.calls.append((text, principal))
            raise AssertionError("fallback reasoner must not be called")

    fallback = Fallback()

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "management.site.search",
                "resource_types": ("management_site",),
                "selector_keys": ("name", "site", "site_id"),
                "fact_hints": (
                    "site",
                    "sites",
                    "client site",
                    "managed site",
                    "site name",
                    "site identifier",
                    "site details",
                ),
                "selector_required": False,
            },
        ),
        fallback=fallback,
    )

    inquiry = interpreter.interpret(
        text="What sites are in Datto RMM?",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.resource_type == "management_site"
    assert inquiry.resource_selector == {}
    assert inquiry.requested_facts == ("sites",)
    assert inquiry.execution_mode == "deterministic"
    assert inquiry.permission_mode == "observe"
    assert fallback.calls == []


def test_metadata_first_interpreter_falls_back_when_selector_is_required():
    class Fallback:
        def __init__(self):
            self.calls = []

        def interpret(self, *, text, principal):
            self.calls.append((text, principal))
            return None

    fallback = Fallback()

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "endpoint.software.search",
                "resource_types": ("endpoint_software", "endpoint"),
                "selector_keys": ("hostname", "name", "resource_id"),
                "fact_hints": ("software", "installed software"),
                "selector_required": True,
            },
        ),
        fallback=fallback,
    )

    result = interpreter.interpret(
        text="What software is installed on AOT-50282?",
        principal=principal(),
    )

    assert result is None
    assert len(fallback.calls) == 1


def test_metadata_first_interpreter_falls_back_on_ambiguous_metadata_match():
    class Fallback:
        def __init__(self):
            self.calls = []

        def interpret(self, *, text, principal):
            self.calls.append((text, principal))
            return None

    fallback = Fallback()

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "one",
                "resource_types": ("one",),
                "selector_keys": (),
                "fact_hints": ("status",),
                "selector_required": False,
            },
            {
                "capability_name": "two",
                "resource_types": ("two",),
                "selector_keys": (),
                "fact_hints": ("status",),
                "selector_required": False,
            },
        ),
        fallback=fallback,
    )

    result = interpreter.interpret(
        text="Show status",
        principal=principal(),
    )

    assert result is None
    assert len(fallback.calls) == 1


def test_metadata_first_distinguishes_summary_from_complete_enumeration():
    class ForbiddenFallback:
        def interpret(self, **kwargs):
            raise AssertionError("fallback must not be called")

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "management.site.search",
                "resource_types": ("management_site",),
                "selector_keys": ("name", "site", "site_id"),
                "fact_hints": ("site", "sites", "managed site"),
                "selector_required": False,
            },
        ),
        fallback=ForbiddenFallback(),
    )

    summary = interpreter.interpret(
        text="What sites are in Datto RMM?",
        principal=principal(),
    )

    listing = interpreter.interpret(
        text="Please list the sites in Datto RMM",
        principal=principal(),
    )

    assert summary.result_intent == "summary"
    assert summary.completeness_requirement == "sufficient"

    assert listing.result_intent == "enumerate"
    assert listing.completeness_requirement == "complete"


def test_metadata_first_count_requires_complete_collection():
    class ForbiddenFallback:
        def interpret(self, **kwargs):
            raise AssertionError("fallback must not be called")

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "management.site.search",
                "resource_types": ("management_site",),
                "selector_keys": ("name", "site", "site_id"),
                "fact_hints": ("site", "sites", "managed site"),
                "selector_required": False,
            },
        ),
        fallback=ForbiddenFallback(),
    )

    inquiry = interpreter.interpret(
        text="How many sites are in Datto RMM?",
        principal=principal(),
    )

    assert inquiry.result_intent == "count"
    assert inquiry.completeness_requirement == "complete"
