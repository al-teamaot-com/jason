from __future__ import annotations

from jason_runtime.conversation_experience_cutover import (
    ConversationExperienceCutoverSettings,
    select_conversation_experience_flow,
)
from orchestrator.model_runtime_adapter import ModelRuntimeAdapter
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient


class Dummy:
    pass


def test_conversation_experience_wraps_each_ollama_backend_in_runtime_schema_adapter(tmp_path):
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

    experience_client = selected.experience.kernel.proposing.backends[0].client
    work_client = selected.progressive_reads.gaps.reasoning.backends[0].client

    assert isinstance(experience_client, ModelRuntimeAdapter)
    assert isinstance(work_client, ModelRuntimeAdapter)
    assert isinstance(experience_client.client, OllamaStructuredJsonClient)
    assert isinstance(work_client.client, OllamaStructuredJsonClient)
    assert experience_client.model == "quality-model"
    assert work_client.model == "cheap-work"
