from datetime import datetime, timezone

from orchestrator.resource_capability_catalog import (
    endpoint_device_read,
    endpoint_device_search,
)
from orchestrator.resource_inquiry import ResourceInquiry
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner


NOW = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)


def test_bitlocker_status_has_explicit_endpoint_read_coverage():
    reasoner = MetadataResourceCapabilityReasoner()
    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50107"},
        requested_facts=("bitlocker status",),
        evidence_contexts={
            "bitlocker status": ("bitlocker", "udf"),
        },
    )

    plan = reasoner.select(
        inquiry=inquiry,
        candidates=(endpoint_device_search(NOW), endpoint_device_read(NOW)),
    )

    assert plan
    assert plan[0].capability_name == "endpoint.device.search"
    assert plan[0].arguments["requested_facts"] == ("bitlocker status",)
    assert plan[0].arguments["evidence_contexts"] == {
        "bitlocker status": ("bitlocker", "udf"),
    }


def test_bitlocker_recovery_key_does_not_fall_into_generic_endpoint_read():
    reasoner = MetadataResourceCapabilityReasoner()
    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50107"},
        requested_facts=("bitlocker recovery key",),
        evidence_contexts={
            "bitlocker recovery key": ("bitlocker", "recovery"),
        },
    )

    plan = reasoner.select(
        inquiry=inquiry,
        candidates=(endpoint_device_search(NOW), endpoint_device_read(NOW)),
    )

    assert plan == ()
