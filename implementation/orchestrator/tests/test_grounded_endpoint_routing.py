from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.canonical_fact_vocabulary import (
    DEFAULT_CANONICAL_FACT_VOCABULARY,
)
from orchestrator.conversation_resource_intent import (
    MetadataFirstResourceInquiryInterpreter,
)
from orchestrator.resource_capability_catalog import (
    ENDPOINT_ALERT_HISTORY_SEARCH,
    ENDPOINT_ALERT_SEARCH,
    ENDPOINT_AUDIT_READ,
    ENDPOINT_DEVICE_READ,
    ENDPOINT_DEVICE_SEARCH,
    ENDPOINT_SOFTWARE_SEARCH,
    datto_rmm_endpoint_provider,
    endpoint_alert_history_search,
    endpoint_alert_search,
    endpoint_audit_read,
    endpoint_device_read,
    endpoint_device_search,
    endpoint_software_search,
)
from orchestrator.resource_reasoner import (
    MetadataResourceCapabilityReasoner,
)
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
)


NOW = datetime(
    2026,
    8,
    14,
    tzinfo=timezone.utc,
)


class NoLanguageFallback:
    def interpret(self, *, text, principal):
        raise AssertionError(
            "grounded endpoint question reached language fallback: "
            + text
        )


class RecordingFallback:
    def __init__(self):
        self.calls = []

    def interpret(self, *, text, principal):
        self.calls.append(text)
        return None


def principal():
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
    )


def interpreter(fallback=None):
    return MetadataFirstResourceInquiryInterpreter(
        contracts=(),
        fallback=fallback or NoLanguageFallback(),
        fact_vocabulary=
            DEFAULT_CANONICAL_FACT_VOCABULARY,
    )


def candidates():
    return (
        endpoint_device_search(NOW),
        endpoint_device_read(NOW),
        endpoint_alert_search(NOW),
        endpoint_alert_history_search(NOW),
        endpoint_audit_read(NOW),
        endpoint_software_search(NOW),
    )


def test_grounded_endpoint_routing_table_is_dynamic_and_complete():
    cases = (
        (
            "What is the LAN IP address of AOT-50282?",
            "LAN IP address",
            {"hostname": "AOT-50282"},
            ENDPOINT_DEVICE_SEARCH,
        ),
        (
            "What is the WAN IP address of AOT-50282?",
            "WAN IP address",
            {"hostname": "AOT-50282"},
            ENDPOINT_DEVICE_SEARCH,
        ),
        (
            "Who was the last user logged into AOT-50282?",
            "last logged in user",
            {"hostname": "AOT-50282"},
            ENDPOINT_DEVICE_SEARCH,
        ),
        (
            "What Windows version is installed on AOT-50282?",
            "operating system",
            {"hostname": "AOT-50282"},
            ENDPOINT_DEVICE_SEARCH,
        ),
        (
            "How much RAM is installed in AOT-50282?",
            "total memory",
            {"hostname": "AOT-50282"},
            ENDPOINT_AUDIT_READ,
        ),
        (
            "What processor is installed in AOT-50282?",
            "processor model",
            {"hostname": "AOT-50282"},
            ENDPOINT_AUDIT_READ,
        ),
        (
            "What motherboard is installed in AOT-50282?",
            "motherboard model",
            {"hostname": "AOT-50282"},
            ENDPOINT_AUDIT_READ,
        ),
        (
            "What video card is installed in AOT-50282?",
            "display adapters",
            {"hostname": "AOT-50282"},
            ENDPOINT_AUDIT_READ,
        ),
        (
            "What printers are attached to AOT-50282?",
            "printers",
            {"hostname": "AOT-50282"},
            ENDPOINT_AUDIT_READ,
        ),
        (
            "What version of ZeroTier is installed on AOT-50282?",
            "ZeroTier version",
            {
                "hostname": "AOT-50282",
                "software": "ZeroTier",
            },
            ENDPOINT_SOFTWARE_SEARCH,
        ),
        (
            "What version of Google Chrome is installed on AOT-50282?",
            "Google Chrome version",
            {
                "hostname": "AOT-50282",
                "software": "Google Chrome",
            },
            ENDPOINT_SOFTWARE_SEARCH,
        ),
        (
            "What network adapters are present on AOT-50282?",
            "network adapters",
            {"hostname": "AOT-50282"},
            ENDPOINT_AUDIT_READ,
        ),
        (
            "How much free disk space does AOT-50282 have?",
            "free disk space",
            {"hostname": "AOT-50282"},
            ENDPOINT_AUDIT_READ,
        ),
        (
            "What open alerts exist for AOT-50282?",
            "open alerts",
            {"hostname": "AOT-50282"},
            ENDPOINT_ALERT_SEARCH,
        ),
        (
            "Has AOT-50282 had any disk errors?",
            "disk error evidence",
            {"hostname": "AOT-50282"},
            ENDPOINT_ALERT_HISTORY_SEARCH,
        ),
    )

    reasoner = MetadataResourceCapabilityReasoner()

    for (
        question,
        expected_fact,
        expected_selector,
        expected_capability,
    ) in cases:
        inquiry = interpreter().interpret(
            text=question,
            principal=principal(),
        )

        assert inquiry is not None
        assert inquiry.resource_type == "endpoint"
        assert dict(inquiry.resource_selector) == (
            expected_selector
        )
        assert inquiry.requested_facts == (
            expected_fact,
        )

        steps = tuple(
            reasoner.select(
                inquiry=inquiry,
                candidates=candidates(),
            )
        )

        assert len(steps) == 1
        assert (
            steps[0].capability_name
            == expected_capability
        )
        assert (
            steps[0].arguments["requested_facts"]
            == (expected_fact,)
        )

        for key, value in expected_selector.items():
            assert steps[0].arguments[key] == value


def test_broad_endpoint_request_still_uses_governed_fallback():
    fallback = RecordingFallback()

    result = interpreter(
        fallback=fallback
    ).interpret(
        text=(
            "Tell me everything you know "
            "about AOT-50282."
        ),
        principal=principal(),
    )

    assert result is None
    assert fallback.calls == [
        "Tell me everything you know "
        "about AOT-50282."
    ]


def test_provider_registers_historical_alert_read():
    provider = datto_rmm_endpoint_provider(NOW)

    assert (
        ENDPOINT_ALERT_HISTORY_SEARCH
        in provider.capabilities
    )
