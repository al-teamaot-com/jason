from __future__ import annotations

from datetime import datetime, timezone

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from orchestrator.conversation_resource_intent import (
    MetadataFirstResourceInquiryInterpreter,
)
from orchestrator.print_capability_catalog import (
    PRINT_FLEET_USAGE_RANK, print_capabilities,
)
from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
from orchestrator.teams_conversation_flow import BoundConversationPrincipal


class NoFallback:
    def interpret(self, *, text, principal):
        return None


def build():
    now = datetime(2026, 10, 30, tzinfo=timezone.utc)
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    definitions = print_capabilities(now)
    for definition in definitions:
        capabilities.register(definition)
    contracts = []
    for definition in definitions:
        metadata = definition.metadata
        contracts.append({
            "capability_name": definition.capability_name,
            "resource_types": tuple(x.strip() for x in metadata["resource_types"].split(",")),
            "selector_keys": tuple(x.strip() for x in metadata["selector_keys"].split(",")),
            "fact_hints": tuple(x.strip() for x in metadata["fact_hints"].split(",")),
            "canonical_facts": tuple(
                x.strip() for x in metadata.get("canonical_facts", "").split(",") if x.strip()
            ),
            "query_shape": metadata.get("query_shape", ""),
            "report_timezone": "America/New_York",
            "selector_required": False,
        })
    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=tuple(contracts), fallback=NoFallback(),
    )
    planner = GovernedResourceInquiryPlanner(
        registry=capabilities, reasoner=MetadataResourceCapabilityReasoner(),
    )
    principal = BoundConversationPrincipal(
        principal_id="person-latoshia", organization_id="aot", client_id=None,
    )
    return interpreter, planner, principal


def test_latoshia_october_top_five_is_one_governed_report():
    interpreter, planner, principal = build()
    inquiry = interpreter.interpret(
        text=(
            "@Jason, what are our top 5 highest-volume printers for October 2026? "
            "Please include the customer, printer ID, black-and-white count, "
            "color count, and total pages printed this month."
        ),
        principal=principal,
    )
    assert inquiry is not None
    assert inquiry.resource_selector == {
        "month": "2026-10", "limit": "5", "timezone": "America/New_York",
    }
    assert inquiry.completeness_requirement == "complete"
    plan = planner.plan(inquiry)
    assert len(plan.steps) == 1
    assert plan.steps[0].capability_name == PRINT_FLEET_USAGE_RANK
    assert plan.steps[0].arguments["month"] == "2026-10"
    assert plan.steps[0].arguments["limit"] == "5"
    assert plan.steps[0].arguments["timezone"] == "America/New_York"


def test_top_ten_copiers_uses_parameterized_ranking_capability():
    interpreter, planner, principal = build()
    inquiry = interpreter.interpret(
        text="Show the top 10 copiers by monthly usage in September 2026",
        principal=principal,
    )
    assert inquiry is not None
    assert inquiry.resource_selector["month"] == "2026-09"
    assert inquiry.resource_selector["limit"] == "10"
    assert planner.plan(inquiry).steps[0].capability_name == PRINT_FLEET_USAGE_RANK


def test_ranking_does_not_claim_authority_for_unrelated_toner_question():
    interpreter, _, principal = build()
    inquiry = interpreter.interpret(
        text="Which 5 printers have the lowest toner?", principal=principal,
    )
    assert inquiry is None or inquiry.requested_facts != ("monthly print volume ranking",)
