from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class SemanticIntentTranslation:
    """Provider-neutral meaning of one human request.

    The translation contains meaning only. It contains no provider,
    connector, credential, authority, tool, agent, API route, or
    execution decision.

    resource_selector is grounded outside the semantic model. An empty
    selector is valid for bounded collection reads such as management-wide
    alerts or site enumeration.
    """

    resource_type: str
    requested_concepts: tuple[str, ...]
    resource_selector: Mapping[str, str] = field(default_factory=dict)
    operation: str = "read"
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.resource_type.strip():
            raise ValueError(
                "semantic intent resource type is required"
            )

        if not self.requested_concepts:
            raise ValueError(
                "semantic intent requested concepts are required"
            )

        if self.operation != "read":
            raise PermissionError(
                "semantic intent translator may only produce read interpretation"
            )

        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValueError(
                "semantic intent confidence must be between zero and one"
            )


class SemanticIntentTranslator(Protocol):
    """Translate human language into bounded canonical meaning only.

    eligible_resources is authoritative. The translator may choose only a
    supplied resource type and concepts belonging to that resource.

    grounded_selectors is also authoritative. The semantic provider does not
    create, modify, or infer selectors.
    """

    def translate(
        self,
        *,
        text: str,
        eligible_resources: Mapping[str, tuple[str, ...]],
        grounded_selectors: (
            Mapping[str, Mapping[str, str]] | None
        ) = None,
    ) -> SemanticIntentTranslation | None:
        ...
