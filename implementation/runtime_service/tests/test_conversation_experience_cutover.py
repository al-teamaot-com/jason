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


def test_enabled_cutover_keeps_experience_models_separate_from_backend_work_models(tmp_path):
    identity = Dummy()
    factory = Dummy()
    orchestrator = Dummy()
    transport = Dummy()
    capabilities = Dummy()

    selected = select_conversation_experience_flow(
        settings=ConversationExperienceCutoverSettings(
            enabled=True,
            context_db=tmp_path / "context.sqlite3",
            experience_models=("quality-local", "quality-fallback"),
            work_models=("cheap-work", "work-fallback"),
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

    experience_backends = selected.experience.kernel.reasoning.backends
    assert [item.name for item in experience_backends] == [
        "experience:quality-local",
        "experience:quality-fallback",
    ]
    assert [item.client.timeout_seconds for item in experience_backends] == [120, 120]

    work_backends = selected.progressive_reads.gaps.reasoning.backends
    assert [item.name for item in work_backends] == [
        "work:cheap-work",
        "work:work-fallback",
    ]
    assert [item.client.timeout_seconds for item in work_backends] == [120, 120]

    review_backends = selected.progressive_reads.evidence.reasoner.reviewing.backends
    assert [item.name for item in review_backends] == [
        "experience:quality-local",
        "experience:quality-fallback",
    ]


def test_enabled_cutover_defaults_both_roles_to_existing_ollama_model_without_lock_in(tmp_path):
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
    ] == ["experience:current-runtime-model"]
    assert [
        item.name for item in selected.progressive_reads.gaps.reasoning.backends
    ] == ["work:current-runtime-model"]


def test_answer_drafting_tries_backend_work_model_before_experience_model(tmp_path):
    selected = select_conversation_experience_flow(
        settings=ConversationExperienceCutoverSettings(
            enabled=True,
            context_db=tmp_path / "context.sqlite3",
            experience_models=("quality-model",),
            work_models=("cheap-work",),
        ),
        fallback_flow=Dummy(),
        capabilities=Dummy(),
        ollama_url="http://ollama.invalid:11434",
        default_ollama_model="unused",
        identity_binder=Dummy(),
        request_factory=Dummy(),
        orchestrator=Dummy(),
        transport=Dummy(),
    )

    drafting = selected.progressive_reads.answerer.drafting.backends
    assert [item.name for item in drafting] == [
        "work:cheap-work",
        "experience:quality-model",
    ]
    reviewing = selected.progressive_reads.answerer.reviewing.backends
    assert [item.name for item in reviewing] == [
        "experience:quality-model"
    ]


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


def test_duplicate_or_untrimmed_model_names_are_rejected_by_role():
    with pytest.raises(ValueError, match="experience models must be unique"):
        ConversationExperienceCutoverSettings(
            enabled=True,
            experience_models=("same", "same"),
        )

    with pytest.raises(ValueError, match="work models must be non-empty normalized"):
        ConversationExperienceCutoverSettings(
            enabled=True,
            work_models=(" cheap ",),
        )
