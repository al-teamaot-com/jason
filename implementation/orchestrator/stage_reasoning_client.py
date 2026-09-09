"""Stage-specific structured reasoning budgets for Jason conversation execution.

The underlying reasoning client remains provider-independent and has no execution
authority. This adapter declares the minimum bounded generation budget needed by a
specific semantic stage so one caller's generic default cannot make the stage's
structured contract impossible to complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class StructuredReasoningClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class StageReasoningClient:
    """Apply one explicit, bounded output budget to a semantic reasoning stage."""

    client: StructuredReasoningClient
    output_tokens: int

    def __post_init__(self) -> None:
        if self.output_tokens < 16 or self.output_tokens > 1024:
            raise ValueError("stage reasoning output budget is invalid")

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]:
        del max_output_tokens
        return self.client.complete(
            system=system,
            user=user,
            schema=schema,
            max_output_tokens=self.output_tokens,
        )
