from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pytest

from orchestrator.stage_reasoning_client import StageReasoningClient


@dataclass
class RecordingClient:
    calls: list[Mapping[str, Any]] = field(default_factory=list)

    def complete(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"status": "ok"}


def test_stage_budget_replaces_generic_caller_default_without_expanding_itself():
    client = RecordingClient()
    stage = StageReasoningClient(client=client, output_tokens=256)

    result = stage.complete(
        system="interpret the request",
        user="synthetic request",
        schema={"type": "object"},
        max_output_tokens=160,
    )

    assert result == {"status": "ok"}
    assert client.calls[0]["max_output_tokens"] == 256


def test_independent_stages_can_hold_different_bounded_generation_contracts():
    client = RecordingClient()
    planning = StageReasoningClient(client=client, output_tokens=384)
    compact = StageReasoningClient(client=client, output_tokens=96)

    planning.complete(system="plan", user="one", schema={"type": "object"})
    compact.complete(system="select", user="two", schema={"type": "object"})

    assert [call["max_output_tokens"] for call in client.calls] == [384, 96]


@pytest.mark.parametrize("tokens", [0, 15, 1025])
def test_stage_budget_remains_bounded(tokens):
    with pytest.raises(ValueError, match="output budget"):
        StageReasoningClient(client=RecordingClient(), output_tokens=tokens)
