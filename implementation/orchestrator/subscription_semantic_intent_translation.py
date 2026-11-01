from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .semantic_intent_translation import SemanticIntentTranslation


@dataclass(frozen=True, slots=True)
class SubscriptionSemanticIntentTranslator:
    """Semantic translation through the governed subscription structured client."""

    structured_client: Any

    def translate(
        self,
        *,
        text: str,
        eligible_concepts: tuple[str, ...],
        grounded_selector: Mapping[str, str] | None = None,
    ) -> SemanticIntentTranslation | None:
        concepts = self._normalize_concepts(eligible_concepts)
        result = self.structured_client.complete(
            system=(
                "Translate the human request into the smallest complete set of "
                "canonical semantic concepts from the supplied catalog. Return "
                "only concepts necessary to answer what was actually asked. Do "
                "not choose providers, connectors, tools, credentials, permissions "
                "or actions. If the request cannot be represented confidently by "
                "the supplied concepts, return resolved=false and an empty list."
            ),
            user=json.dumps(
                {
                    "human_text": str(text),
                    "eligible_concepts": concepts,
                    "grounded_target_present": bool(grounded_selector),
                },
                sort_keys=True,
            ),
            schema=self._schema(concepts),
            max_output_tokens=256,
        )
        if result.get("resolved") is not True:
            return None
        raw = result.get("requested_concepts")
        if not isinstance(raw, list):
            raise ValueError("semantic provider requested_concepts must be a list")
        allowed = set(concepts)
        selected: list[str] = []
        for item in raw:
            concept = str(item).strip()
            if concept not in allowed:
                raise PermissionError(
                    "semantic provider selected concept outside governed catalog"
                )
            if concept not in selected:
                selected.append(concept)
        if not selected:
            return None
        return SemanticIntentTranslation(
            requested_concepts=tuple(selected),
            operation="read",
            confidence=float(result.get("confidence", 0.0)),
        )

    @staticmethod
    def _normalize_concepts(
        eligible_concepts: tuple[str, ...],
    ) -> tuple[str, ...]:
        concepts = tuple(
            dict.fromkeys(
                str(item).strip()
                for item in eligible_concepts
                if str(item).strip()
            )
        )
        if not concepts:
            raise ValueError("semantic translation requires an eligible concept catalog")
        if len(concepts) > 500:
            raise ValueError("semantic concept catalog exceeds governed bound")
        return concepts

    @staticmethod
    def _schema(concepts: tuple[str, ...]) -> Mapping[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "resolved": {"type": "boolean"},
                "requested_concepts": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(concepts)},
                    "maxItems": min(20, len(concepts)),
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
            "required": ["resolved", "requested_concepts", "confidence"],
        }
