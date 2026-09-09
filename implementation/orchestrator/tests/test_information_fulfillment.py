from __future__ import annotations

from types import SimpleNamespace

import pytest

from kernel.capabilities import CapabilityLifecycle
from orchestrator.conversation_kernel import InformationNeed, InformationTarget
from orchestrator.information_fulfillment import (
    GovernedInitialFulfillmentPlanner,
    RegistryBackedFulfillmentCatalog,
)


class FakeRegistry:
    def __init__(self, items):
        self.items = tuple(items)

    def list_all(self):
        return self.items


def capability(
    name,
    *,
    resource_types,
    operation,
    selector_keys="name,resource_id",
    read_only="true",
    provider_neutral="true",
    resource_role=None,
):
    metadata = {
        "resource_types": resource_types,
        "operation": operation,
        "selector_keys": selector_keys,
        "read_only": read_only,
        "provider_neutral": provider_neutral,
        # Legacy semantics are deliberately irrelevant to the new planner.
        "fact_hints": "logged in user,alerts,whatever",
        "canonical_facts": "some mapped fact",
    }
    if resource_role is not None:
        metadata["resource_role"] = resource_role
    return SimpleNamespace(
        capability_name=name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        metadata=metadata,
        risk_level=SimpleNamespace(value="low"),
        display_name=name,
        business_purpose="governed resource access",
    )


def need(*, source="literal", reference="NODE-77"):
    return InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source=source,
            reference=reference,
            entity_ref="entity-1" if source == "verified_entity" else None,
        ),
        need="arbitrary human information need",
        authority="observe",
    )


def catalog(*extra):
    return RegistryBackedFulfillmentCatalog(
        registry=FakeRegistry(
            (
                capability(
                    "endpoint.device.search",
                    resource_types="endpoint",
                    operation="search",
                ),
                capability(
                    "endpoint.device.read",
                    resource_types="endpoint",
                    operation="read",
                    selector_keys="resource_id",
                ),
                capability(
                    "endpoint.alert.history.search",
                    resource_types="endpoint_alert,alert,endpoint",
                    operation="search",
                ),
                *extra,
            )
        )
    )


def test_literal_target_starts_with_one_primary_search_not_speculative_specialized_reads():
    planner = GovernedInitialFulfillmentPlanner(catalog=catalog())

    plan = planner.plan(need())

    assert len(plan.steps) == 1
    assert plan.steps[0].capability_name == "endpoint.device.search"
    assert plan.steps[0].information_need == "arbitrary human information need"


def test_verified_entity_prefers_primary_read_when_registered():
    planner = GovernedInitialFulfillmentPlanner(catalog=catalog())

    plan = planner.plan(need(source="verified_entity", reference="resource-123"))

    assert plan.steps[0].capability_name == "endpoint.device.read"


def test_specialized_capabilities_are_structurally_available_but_not_initially_speculated():
    items = catalog().list_available()

    roles = {item.capability_name: item.role for item in items}

    assert roles["endpoint.device.search"] == "primary"
    assert roles["endpoint.device.read"] == "primary"
    assert roles["endpoint.alert.history.search"] == "specialized"


def test_semantic_hint_metadata_does_not_change_initial_capability_choice():
    misleading = capability(
        "endpoint.fake.specialized",
        resource_types="endpoint_detail,endpoint",
        operation="search",
    )
    planner = GovernedInitialFulfillmentPlanner(catalog=catalog(misleading))

    plan = planner.plan(need())

    assert plan.steps[0].capability_name == "endpoint.device.search"


def test_multiple_primary_search_claims_fail_closed_instead_of_first_match_routing():
    duplicate = capability(
        "endpoint.alternate.search",
        resource_types="endpoint",
        operation="search",
        resource_role="primary",
    )
    planner = GovernedInitialFulfillmentPlanner(catalog=catalog(duplicate))

    with pytest.raises(
        LookupError,
        match="multiple primary governed capabilities",
    ):
        planner.plan(need())


def test_provider_specific_capability_is_not_exposed_to_fulfillment_catalog():
    private = capability(
        "endpoint.private.search",
        resource_types="endpoint",
        operation="search",
        provider_neutral="false",
    )
    items = catalog(private).list_available()

    assert "endpoint.private.search" not in {item.capability_name for item in items}
