from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestrator.capability_routing_invoker import CanonicalCapabilityRoutingInvoker


class Delegate:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def invoke(self, *, request, resolution):
        self.calls.append((request, resolution))
        return self.result


def test_routes_only_by_already_resolved_canonical_capability() -> None:
    expected = object()
    delegate = Delegate(expected)
    invoker = CanonicalCapabilityRoutingInvoker(
        routes={"automation.component.search": delegate}
    )
    request = SimpleNamespace(capability_name="automation.component.search")
    resolution = SimpleNamespace(capability_name="automation.component.search")

    result = invoker.invoke(request=request, resolution=resolution)

    assert result is expected
    assert delegate.calls == [(request, resolution)]


def test_rejects_resolution_request_capability_mismatch() -> None:
    invoker = CanonicalCapabilityRoutingInvoker(routes={})

    with pytest.raises(PermissionError, match="does not match"):
        invoker.invoke(
            request=SimpleNamespace(capability_name="automation.component.search"),
            resolution=SimpleNamespace(capability_name="automation.job.read"),
        )


def test_fails_closed_without_registered_route() -> None:
    invoker = CanonicalCapabilityRoutingInvoker(routes={})

    with pytest.raises(LookupError, match="no governed invoker route"):
        invoker.invoke(
            request=SimpleNamespace(capability_name="automation.component.search"),
            resolution=SimpleNamespace(capability_name="automation.component.search"),
        )
