from __future__ import annotations

from types import SimpleNamespace

from kernel.capabilities import CapabilityLifecycle
from orchestrator.conversation_kernel import (
    InformationNeed,
    InformationTarget,
    ReasoningBackend,
    ValidatedReasoningPool,
)
from orchestrator.evidence_gap_fulfillment import EvidenceGapFulfillmentPlanner
from orchestrator.information_fulfillment import RegistryBackedFulfillmentCatalog


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, *, system, user, schema, max_output_tokens=160):
        self.calls.append((system, user, schema, max_output_tokens))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeRegistry:
    def __init__(self, items):
        self.items = tuple(items)

    def list_all(self):
        return self.items


def capability(name, *, types, role, purpose):
    return SimpleNamespace(
        capability_name=name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": types,
            "operation": "search",
            "selector_keys": "hostname,name",
            "resource_role": role,
            "fact_hints": "legacy phrase that must not be used",
        },
        risk_level=SimpleNamespace(value="low"),
        display_name=name,
        business_purpose=purpose,
    )


def need():
    return InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source="literal",
            reference="NODE-77",
        ),
        need="historical operating condition evidence",
        authority="observe",
        temporal_scope="historical",
    )


def pool(*clients):
    return ValidatedReasoningPool(
        backends=tuple(
            ReasoningBackend(name=f"model-{index}", client=client)
            for index, client in enumerate(clients, start=1)
        )
    )


def catalog(*specialized):
    return RegistryBackedFulfillmentCatalog(
        registry=FakeRegistry(
            (
                capability(
                    "endpoint.device.search",
                    types="endpoint",
                    role="primary",
                    purpose="general endpoint discovery and read",
                ),
                *specialized,
            )
        )
    )


def test_one_remaining_specialized_candidate_needs_no_model_call():
    client = FakeClient()
    service = EvidenceGapFulfillmentPlanner(
        catalog=catalog(
            capability(
                "endpoint.history.search",
                types="endpoint_history,endpoint",
                role="specialized",
                purpose="read historical endpoint evidence",
            )
        ),
        reasoning=pool(client),
    )

    step = service.next_step(
        need=need(),
        attempted_capabilities=("endpoint.device.search",),
    )

    assert step.capability_name == "endpoint.history.search"
    assert step.target_reference == "NODE-77"
    assert client.calls == []


def test_multiple_specialized_candidates_allow_model_to_choose_only_one_next_read():
    client = FakeClient({"capability_name": "endpoint.history.search"})
    service = EvidenceGapFulfillmentPlanner(
        catalog=catalog(
            capability(
                "endpoint.history.search",
                types="endpoint_history,endpoint",
                role="specialized",
                purpose="read historical endpoint evidence",
            ),
            capability(
                "endpoint.software.search",
                types="endpoint_software,endpoint",
                role="specialized",
                purpose="read installed software inventory",
            ),
        ),
        reasoning=pool(client),
    )

    step = service.next_step(
        need=need(),
        attempted_capabilities=("endpoint.device.search",),
    )

    assert step.capability_name == "endpoint.history.search"
    assert len(client.calls) == 1


def test_attempted_specialized_resources_are_excluded_so_bad_order_can_recover_progressively():
    client = FakeClient()
    service = EvidenceGapFulfillmentPlanner(
        catalog=catalog(
            capability(
                "endpoint.history.search",
                types="endpoint_history,endpoint",
                role="specialized",
                purpose="read historical endpoint evidence",
            ),
            capability(
                "endpoint.software.search",
                types="endpoint_software,endpoint",
                role="specialized",
                purpose="read installed software inventory",
            ),
        ),
        reasoning=pool(client),
    )

    step = service.next_step(
        need=need(),
        attempted_capabilities=(
            "endpoint.device.search",
            "endpoint.software.search",
        ),
    )

    assert step.capability_name == "endpoint.history.search"
    assert client.calls == []


def test_invalid_cheap_choice_can_fall_back_to_stronger_backend():
    cheap = FakeClient({"capability_name": "provider.secret.path"})
    stronger = FakeClient({"capability_name": "endpoint.history.search"})
    service = EvidenceGapFulfillmentPlanner(
        catalog=catalog(
            capability(
                "endpoint.history.search",
                types="endpoint_history,endpoint",
                role="specialized",
                purpose="read historical endpoint evidence",
            ),
            capability(
                "endpoint.software.search",
                types="endpoint_software,endpoint",
                role="specialized",
                purpose="read installed software inventory",
            ),
        ),
        reasoning=pool(cheap, stronger),
    )

    step = service.next_step(
        need=need(),
        attempted_capabilities=("endpoint.device.search",),
    )

    assert step.capability_name == "endpoint.history.search"
    assert len(cheap.calls) == 1
    assert len(stronger.calls) == 1


def test_when_all_specialized_resources_are_exhausted_planner_returns_none():
    client = FakeClient()
    service = EvidenceGapFulfillmentPlanner(
        catalog=catalog(
            capability(
                "endpoint.history.search",
                types="endpoint_history,endpoint",
                role="specialized",
                purpose="read historical endpoint evidence",
            )
        ),
        reasoning=pool(client),
    )

    step = service.next_step(
        need=need(),
        attempted_capabilities=(
            "endpoint.device.search",
            "endpoint.history.search",
        ),
    )

    assert step is None
    assert client.calls == []
