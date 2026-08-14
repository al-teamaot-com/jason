from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class SemanticIntentTranslation:
    """Provider-neutral semantic meaning of one human request.

    The semantic provider identifies canonical fact obligations only.

    It does not determine:
      - target identity;
      - target scope;
      - resource implementation;
      - capability;
      - provider;
      - connector;
      - credential;
      - permission;
      - authority;
      - tool;
      - agent;
      - API route;
      - execution behavior.

    Those remain Jason responsibilities.
    """

    requested_concepts: tuple[str, ...]
    operation: str = "read"
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.requested_concepts:
            raise ValueError(
                "semantic intent requested concepts are required"
            )

        if self.operation != "read":
            raise PermissionError(
                "semantic intent translator may only produce read interpretation"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "semantic intent confidence must be between zero and one"
            )


class SemanticIntentTranslator(Protocol):
    """Translate human language into bounded canonical fact obligations."""

    def translate(
        self,
        *,
        text: str,
        eligible_concepts: tuple[str, ...],
        grounded_selector: Mapping[str, str] | None = None,
    ) -> SemanticIntentTranslation | None:
        ...
