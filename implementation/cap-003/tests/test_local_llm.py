from __future__ import annotations

import pytest

from jason_cap_003.local_llm import OllamaBusinessContextAnalyzer


def test_analyzer_requires_loopback_ollama_endpoint() -> None:
    analyzer = OllamaBusinessContextAnalyzer()
    assert analyzer.model == "qwen3:1.7b"

    with pytest.raises(ValueError, match="loopback"):
        OllamaBusinessContextAnalyzer(
            endpoint="http://192.168.12.149:11434/api/chat"
        )
