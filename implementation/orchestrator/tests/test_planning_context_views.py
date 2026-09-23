import pytest

from orchestrator.planning_context_views import (
    GovernedPlanningContextCatalog,
    PlanningContextRequest,
    PlanningContextView,
    PlanningContextViewUnavailableError,
    StaticPlanningContextProvider,
)


def test_catalog_allows_only_governed_view_names():
    catalog = GovernedPlanningContextCatalog(providers={})
    with pytest.raises(PermissionError):
        catalog.read(PlanningContextRequest(view_name="provider_api"))


def test_catalog_fails_closed_when_governed_view_is_unavailable():
    catalog = GovernedPlanningContextCatalog(providers={})
    with pytest.raises(PlanningContextViewUnavailableError):
        catalog.read(PlanningContextRequest(view_name="capabilities"))


def test_static_context_provider_returns_bounded_provider_neutral_records():
    provider = StaticPlanningContextProvider(
        view_name="capabilities",
        records=(
            {"capability_name": "endpoint.device.search", "purpose": "search endpoints"},
            {"capability_name": "ticket.search", "purpose": "search tickets"},
        ),
        searchable_fields=("capability_name", "purpose"),
    )
    catalog = GovernedPlanningContextCatalog(providers={"capabilities": provider})
    view = catalog.read(
        PlanningContextRequest(view_name="capabilities", query="endpoint", limit=1)
    )
    assert view.view_name == "capabilities"
    assert len(view.items) == 1
    assert view.items[0]["capability_name"] == "endpoint.device.search"


def test_catalog_rejects_provider_that_changes_view_name():
    class BadProvider:
        def read(self, request):
            return PlanningContextView(view_name="system_state", items=())

    catalog = GovernedPlanningContextCatalog(providers={"capabilities": BadProvider()})
    with pytest.raises(RuntimeError):
        catalog.read(PlanningContextRequest(view_name="capabilities"))


def test_request_limit_is_bounded():
    with pytest.raises(ValueError):
        PlanningContextRequest(view_name="capabilities", limit=0)
    with pytest.raises(ValueError):
        PlanningContextRequest(view_name="capabilities", limit=129)
