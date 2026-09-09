from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.resource_capability_catalog import endpoint_device_search
from orchestrator.resource_inquiry import ResourceInquiry
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner


NOW = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "fact",
    (
        "ip address",
        "endpoint last seen",
    ),
)
def test_endpoint_semantic_concepts_plan_without_static_fact_mapping(fact):
    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50107"},
        requested_facts=(fact,),
    )

    plan = MetadataResourceCapabilityReasoner().select(
        inquiry=inquiry,
        candidates=(endpoint_device_search(NOW),),
    )

    assert len(plan) == 1
    assert plan[0].capability_name == "endpoint.device.search"
    assert plan[0].arguments["requested_facts"] == (fact,)


def test_sensitive_security_semantic_does_not_become_endpoint_read_authority():
    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50107"},
        requested_facts=("bitlocker recovery key",),
    )

    plan = MetadataResourceCapabilityReasoner().select(
        inquiry=inquiry,
        candidates=(endpoint_device_search(NOW),),
    )

    assert plan == ()
