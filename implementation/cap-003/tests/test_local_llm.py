from __future__ import annotations

import pytest

from jason_cap_003.context import AutotaskBusinessContext
from jason_cap_003.local_llm import OllamaBusinessContextAnalyzer


def test_analyzer_requires_loopback_ollama_endpoint() -> None:
    analyzer = OllamaBusinessContextAnalyzer()
    assert analyzer.model == "qwen3:1.7b"

    with pytest.raises(ValueError, match="loopback"):
        OllamaBusinessContextAnalyzer(
            endpoint="http://192.168.12.149:11434/api/chat"
        )


def test_business_context_projection_is_bounded_and_selective() -> None:
    long_description = "x" * 2000
    context = AutotaskBusinessContext(
        company={
            "id": 208,
            "companyName": "Example Company",
            "internalProviderMetadata": "must-not-reach-model",
        },
        contacts=tuple(
            {
                "id": index,
                "firstName": f"Contact {index}",
                "privateMetadata": "omit",
            }
            for index in range(12)
        ),
        configurations=(),
        tickets=(
            {
                "id": 33,
                "ticketNumber": "T1",
                "title": "Example issue",
                "description": long_description,
                "providerMetadata": "omit",
            },
        ),
        contracts=(),
        projects=(),
    )

    compact = OllamaBusinessContextAnalyzer._compact_context(context)

    assert compact["company"] == {
        "id": 208,
        "companyName": "Example Company",
    }
    assert len(compact["contacts"]) == 10
    assert "privateMetadata" not in compact["contacts"][0]
    assert "providerMetadata" not in compact["tickets"][0]
    assert compact["tickets"][0]["description"].endswith("...")
    assert len(compact["tickets"][0]["description"]) == 1203
    assert compact["record_counts"]["contacts"] == 12
