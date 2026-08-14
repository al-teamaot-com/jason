from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class SemanticIntentTranslation:
    """Provider-neutral interpretation of one human request.

    This object represents meaning only. It contains no provider, connector,
    credential, authority, tool, agent, API route, or execution decision.
    """

    resource_type: str
    resource_selector: Mapping[str, str]
    requested_concepts: tuple[str, ...]
    operation: str = "read"
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.resource_type.strip():
            raise ValueError("semantic intent resource type is required")

        if not self.resource_selector:
            raise ValueError("semantic intent resource selector is required")

        if not self.requested_concepts:
            raise ValueError("semantic intent requested concepts are required")

        if self.operation != "read":
            raise PermissionError(
                "semantic intent translator may only produce read interpretation"
            )

        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValueError(
                "semantic intent confidence must be between zero and one"
            )


class SemanticIntentTranslator(Protocol):
    """Translate human language into bounded canonical meaning only."""

    def translate(
        self,
        *,
        text: str,
        resource_type: str,
        resource_selector: Mapping[str, str],
        eligible_concepts: tuple[str, ...],
    ) -> SemanticIntentTranslation | None:
        ...
