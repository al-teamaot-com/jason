from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from jason_runtime.conversation_experience_application import (
    apply_conversation_experience_cutover,
)
from jason_runtime.http import RuntimeHttpApplication
from jason_runtime.return_path import (
    OpenClawReturnPathConversationIngress,
    OpenClawReturnPathTransport,
)
from orchestrator.teams_conversation_experience import TeamsConversationExperienceFlow
from orchestrator.teams_request_factory import GovernedTeamsOrchestrationRequestFactory


class Dummy:
    pass


@dataclass(frozen=True, slots=True)
class GovernedIngress:
    flow: object
    marker: str = "preserved-governed-ingress"


@dataclass(frozen=True, slots=True)
class FallbackFlow:
    identity_binder: object
    request_factory: object
    orchestrator: object
    transport: object


def runtime_settings(tmp_path: Path):
    return SimpleNamespace(
        ollama_url="http://ollama.invalid:11434",
        ollama_model="current-local-model",
        dynamic_conversation_context_db=tmp_path / "context.sqlite3",
        dynamic_conversation_context_ttl_seconds=3600,
    )


def application(tmp_path: Path):
    transport = OpenClawReturnPathTransport()
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    request_factory = GovernedTeamsOrchestrationRequestFactory(
        authority=Dummy(),
        capabilities=capabilities,
    )
    fallback = FallbackFlow(
        identity_binder=Dummy(),
        request_factory=request_factory,
        orchestrator=Dummy(),
        transport=transport,
    )
    governed = GovernedIngress(flow=fallback)
    app = RuntimeHttpApplication(
        ingress=OpenClawReturnPathConversationIngress(
            ingress=governed,
            transport=transport,
        )
    )
    return app, fallback, governed, transport


def test_disabled_application_cutover_returns_exact_composed_runtime(tmp_path):
    app, _, _, _ = application(tmp_path)

    selected = apply_conversation_experience_cutover(
        app,
        runtime_settings=runtime_settings(tmp_path),
        environ={"JASON_CONVERSATION_EXPERIENCE_ENABLED": "false"},
    )

    assert selected is app
    assert not (tmp_path / "context.sqlite3").exists()


def test_enabled_application_cutover_replaces_only_conversation_flow(tmp_path):
    app, fallback, governed, transport = application(tmp_path)

    selected = apply_conversation_experience_cutover(
        app,
        runtime_settings=runtime_settings(tmp_path),
        environ={
            "JASON_CONVERSATION_EXPERIENCE_ENABLED": "true",
            "JASON_CONVERSATION_REASONING_MODELS": "cheap-local,stronger-local",
            "JASON_CONVERSATION_REASONING_TIMEOUT_SECONDS": "120",
            "JASON_CONVERSATION_MAX_SPECIALIZED_READS_PER_NEED": "5",
        },
    )

    assert selected is not app
    assert selected.ingress is not app.ingress
    assert selected.ingress.transport is transport
    assert selected.ingress.ingress.marker == governed.marker

    flow = selected.ingress.ingress.flow
    assert isinstance(flow, TeamsConversationExperienceFlow)
    assert flow.identity_binder is fallback.identity_binder
    assert flow.request_factory is fallback.request_factory
    assert flow.orchestrator is fallback.orchestrator
    assert flow.transport is transport
    assert [item.name for item in flow.experience.kernel.reasoning.backends] == [
        "cheap-local",
        "stronger-local",
    ]
    assert flow.progressive_reads.max_specialized_reads_per_need == 5
    assert (tmp_path / "context.sqlite3").exists()


def test_enabled_cutover_uses_current_runtime_model_when_no_model_list_is_configured(tmp_path):
    app, _, _, _ = application(tmp_path)

    selected = apply_conversation_experience_cutover(
        app,
        runtime_settings=runtime_settings(tmp_path),
        environ={"JASON_CONVERSATION_EXPERIENCE_ENABLED": "true"},
    )

    flow = selected.ingress.ingress.flow
    assert [item.name for item in flow.experience.kernel.reasoning.backends] == [
        "current-local-model"
    ]


def test_cutover_requires_capability_registry_through_existing_governed_request_factory(tmp_path):
    transport = OpenClawReturnPathTransport()
    request_factory = GovernedTeamsOrchestrationRequestFactory(
        authority=Dummy(),
        capabilities=None,
    )
    app = RuntimeHttpApplication(
        ingress=OpenClawReturnPathConversationIngress(
            ingress=GovernedIngress(
                flow=FallbackFlow(
                    identity_binder=Dummy(),
                    request_factory=request_factory,
                    orchestrator=Dummy(),
                    transport=transport,
                )
            ),
            transport=transport,
        )
    )

    with pytest.raises(RuntimeError, match="Capability Registry"):
        apply_conversation_experience_cutover(
            app,
            runtime_settings=runtime_settings(tmp_path),
            environ={"JASON_CONVERSATION_EXPERIENCE_ENABLED": "true"},
        )


def test_cutover_rejects_transport_split_between_governed_flow_and_return_path(tmp_path):
    app, fallback, governed, _ = application(tmp_path)
    split = OpenClawReturnPathTransport()
    bad = RuntimeHttpApplication(
        ingress=OpenClawReturnPathConversationIngress(
            ingress=GovernedIngress(
                flow=FallbackFlow(
                    identity_binder=fallback.identity_binder,
                    request_factory=fallback.request_factory,
                    orchestrator=fallback.orchestrator,
                    transport=split,
                ),
                marker=governed.marker,
            ),
            transport=app.ingress.transport,
        )
    )

    with pytest.raises(RuntimeError, match="share one transport"):
        apply_conversation_experience_cutover(
            bad,
            runtime_settings=runtime_settings(tmp_path),
            environ={"JASON_CONVERSATION_EXPERIENCE_ENABLED": "true"},
        )


def test_invalid_environment_values_fail_closed(tmp_path):
    app, _, _, _ = application(tmp_path)

    with pytest.raises(ValueError, match="must be a boolean"):
        apply_conversation_experience_cutover(
            app,
            runtime_settings=runtime_settings(tmp_path),
            environ={"JASON_CONVERSATION_EXPERIENCE_ENABLED": "maybe"},
        )

    with pytest.raises(ValueError, match="must be numeric"):
        apply_conversation_experience_cutover(
            app,
            runtime_settings=runtime_settings(tmp_path),
            environ={
                "JASON_CONVERSATION_EXPERIENCE_ENABLED": "true",
                "JASON_CONVERSATION_REASONING_TIMEOUT_SECONDS": "later",
            },
        )
