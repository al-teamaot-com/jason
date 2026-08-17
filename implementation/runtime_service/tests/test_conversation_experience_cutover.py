from __future__ import annotations

import pytest

from jason_runtime.conversation_experience_cutover import (
    ConversationExperienceCutoverSettings,
    select_conversation_experience_flow,
)
from orchestrator.teams_conversation_experience import TeamsConversationExperienceFlow


class Dummy:
    pass


def test_disabled_cutover_returns_exact_existing_flow_without_constructing_new_state(tmp_path):
    fallback = Dummy()

    selected = select_conversation_experience_flow(
        settings=ConversationExperienceCutoverSettings(
            enabled=False,
            context_db=tmp_path / "unused.sqlite3",
        ),
        fallback_flow=fallback,
        capabilities=Dummy(),
        ollama_url="",
        default_ollama_model="",
        identity_binder=Dummy(),
        request_factory=Dummy(),
        orchestrator=Dummy(),
        transport=Dummy(),
    )

    assert selected is fallback
    assert not (tmp_path / "unused.sqlite3").exists()


def test_enabled_cutover_composes_one_teams_experience_around_existing_governed_dependencies(tmp_path):
    identity = Dummy()
    factory = Dummy()
    orchestrator = Dummy()
    transport = Dummy()
    capabilities = Dummy()

    selected = select_conversation_experience_flow(
        settings=ConversationExperienceCutoverSettings(
            enabled=True,
            context_db=tmp_path / "context.sqlite3",
            reasoning_models=("cheap-local", "stronger-local"),
            reasoning_timeout_seconds=120,
        ),
        fallback_flow=Dummy(),
        capabilities=capabilities,
        ollama_url="http://ollama.invalid:11434",
        default_ollama_model="unused-default",
        identity_binder=identity,
        request_factory=factory,
        orchestrator=orchestrator,
        transport=transport,
    )

    assert isinstance(selected, TeamsConversationExperienceFlow)
    assert selected.identity_binder is identity
    assert selected.request_factory is factory
    assert selected.orchestrator is orchestrator
    assert selected.transport is transport
    assert not hasattr(selected, "observer")
    assert (tmp_path / "context.sqlite3").exists()

    backends = selected.experience.kernel.reasoning.backends
    assert [item.name for item in backends] == [
        "cheap-local",
        "stronger-local",
    ]
    assert [item.client.timeout_seconds for item in backends] == [120, 120]


def test_enabled_cutover_defaults_to_existing_ollama_model_without_model_lock_in(tmp_path):
    selected = select_conversation_experience_flow(
        settings=ConversationExperienceCutoverSettings(
            enabled=True,
            context_db=tmp_path / "context.sqlite3",
        ),
        fallback_flow=Dummy(),
        capabilities=Dummy(),
        ollama_url="http://ollama.invalid:11434",
        default_ollama_model="current-runtime-model",
        identity_binder=Dummy(),
        request_factory=Dummy(),
        orchestrator=Dummy(),
        transport=Dummy(),
    )

    assert [
        item.name for item in selected.experience.kernel.reasoning.backends
    ] == ["current-runtime-model"]


def test_reasoning_timeout_and_specialized_read_budget_are_bounded():
    with pytest.raises(ValueError, match="reasoning timeout"):
        ConversationExperienceCutoverSettings(
            enabled=True,
            reasoning_timeout_seconds=301,
        )

    with pytest.raises(ValueError, match="specialized read budget"):
        ConversationExperienceCutoverSettings(
            enabled=True,
            max_specialized_reads_per_need=33,
        )


def test_duplicate_reasoning_models_are_rejected():
    with pytest.raises(ValueError, match="must be unique"):
        ConversationExperienceCutoverSettings(
            enabled=True,
            reasoning_models=("same", "same"),
        )
