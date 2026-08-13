from __future__ import annotations

from dataclasses import replace

from jason_runtime.composition import RuntimeSettings, build_disabled_semantic_intent_planner
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
from orchestrator.planning_context_views import GovernedPlanningContextCatalog


class NoopTransport:
    def request(self, **kwargs):
        raise AssertionError('no model call expected during composition')


def _settings() -> RuntimeSettings:
    return RuntimeSettings.from_env()


def test_semantic_planner_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv('JASON_OLLAMA_MODEL', 'test-model')
    settings = _settings()
    planner = build_disabled_semantic_intent_planner(
        settings=settings,
        client=OllamaStructuredJsonClient(transport=NoopTransport(), model='test-model'),
        context_catalog=GovernedPlanningContextCatalog(providers={}),
    )
    assert planner is None


def test_semantic_planner_can_be_composed_without_execution_wiring(monkeypatch):
    monkeypatch.setenv('JASON_OLLAMA_MODEL', 'test-model')
    settings = replace(_settings(), semantic_planner_enabled=True)
    planner = build_disabled_semantic_intent_planner(
        settings=settings,
        client=OllamaStructuredJsonClient(transport=NoopTransport(), model='test-model'),
        context_catalog=GovernedPlanningContextCatalog(providers={}),
    )
    assert planner is not None
    assert planner.budget.max_iterations == 6
    assert planner.budget.max_context_requests == 6
