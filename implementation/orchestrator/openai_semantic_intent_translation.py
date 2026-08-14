from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .semantic_intent_translation import (
    SemanticIntentTranslation,
)


class JsonHttpTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class OpenAITranslationUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class OpenAITranslationOutcome:
    translation: SemanticIntentTranslation | None
    usage: OpenAITranslationUsage


@dataclass(frozen=True, slots=True)
class OpenAISemanticIntentTranslator:
    """OpenAI-backed semantic interpretation with no execution authority.

    The model may choose only:
      - one resource type from Jason's bounded catalog;
      - concepts from Jason's bounded catalog;
      - a confidence value.

    The model cannot return selectors, providers, capabilities, credentials,
    permissions, tools, agents, API routes, or execution instructions.
    """

    api_key: str
    transport: JsonHttpTransport
    model: str
    endpoint: str = "https://api.openai.com/v1/responses"
    timeout_seconds: float = 30.0
    max_output_tokens: int = 160

    def translate(
        self,
        *,
        text: str,
        eligible_resources: Mapping[str, tuple[str, ...]],
        grounded_selectors: (
            Mapping[str, Mapping[str, str]] | None
        ) = None,
    ) -> SemanticIntentTranslation | None:
        return self.translate_with_usage(
            text=text,
            eligible_resources=eligible_resources,
            grounded_selectors=grounded_selectors,
        ).translation

    def translate_with_usage(
        self,
        *,
        text: str,
        eligible_resources: Mapping[str, tuple[str, ...]],
        grounded_selectors: (
            Mapping[str, Mapping[str, str]] | None
        ) = None,
    ) -> OpenAITranslationOutcome:
        catalog = self._normalize_catalog(
            eligible_resources
        )

        selectors = {
            str(resource_type): {
                str(key): str(value)
                for key, value in selector.items()
            }
            for resource_type, selector in (
                grounded_selectors or {}
            ).items()
        }

        schema = self._schema(catalog)

        payload = {
            "model": self.model,
            "instructions": (
                "Translate the human request into the smallest complete "
                "provider-neutral Jason intent. Choose exactly one resource "
                "type from the supplied catalog and only the canonical "
                "concepts necessary to answer the request. Do not add useful "
                "but unrequested concepts. A generic bounded request may map "
                "to multiple concepts only when all are required for the "
                "complete safe meaning, such as a generic endpoint IP request "
                "mapping to both LAN IP address and WAN IP address. "
                "You have no authority to select or describe providers, "
                "connectors, capabilities, tools, agents, credentials, "
                "permissions, API routes, selectors, or actions. Selectors "
                "are grounded by Jason outside this model. If the request "
                "cannot be represented confidently by the supplied catalog, "
                "return resolved=false with an empty requested_concepts list."
            ),
            "input": json.dumps(
                {
                    "human_text": text,
                    "eligible_resources": catalog,
                    "grounded_resource_types": sorted(
                        selectors
                    ),
                },
                sort_keys=True,
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "jason_semantic_intent",
                    "strict": True,
                    "schema": schema,
                }
            },
            "max_output_tokens": self.max_output_tokens,
        }

        response = self.transport.request(
            method="POST",
            url=self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout_seconds=self.timeout_seconds,
        )

        usage = self._usage(response)
        decoded = self._decode_output(response)

        if decoded.get("resolved") is not True:
            return OpenAITranslationOutcome(
                translation=None,
                usage=usage,
            )

        resource_type = str(
            decoded.get("resource_type", "")
        ).strip()

        if resource_type not in catalog:
            raise PermissionError(
                "semantic provider selected resource type outside governed catalog"
            )

        raw_concepts = decoded.get(
            "requested_concepts"
        )
        if not isinstance(raw_concepts, list):
            raise ValueError(
                "semantic provider requested_concepts must be a list"
            )

        allowed = set(catalog[resource_type])
        concepts: list[str] = []

        for raw in raw_concepts:
            concept = str(raw).strip()

            if concept not in allowed:
                raise PermissionError(
                    "semantic provider selected concept outside governed resource catalog"
                )

            if concept not in concepts:
                concepts.append(concept)

        if not concepts:
            return OpenAITranslationOutcome(
                translation=None,
                usage=usage,
            )

        confidence = float(
            decoded.get("confidence", 0.0)
        )

        translation = SemanticIntentTranslation(
            resource_type=resource_type,
            resource_selector=selectors.get(
                resource_type,
                {},
            ),
            requested_concepts=tuple(concepts),
            operation="read",
            confidence=confidence,
        )

        return OpenAITranslationOutcome(
            translation=translation,
            usage=usage,
        )

    @staticmethod
    def _normalize_catalog(
        eligible_resources: Mapping[
            str,
            tuple[str, ...],
        ],
    ) -> dict[str, tuple[str, ...]]:
        result: dict[str, tuple[str, ...]] = {}

        for raw_resource, raw_concepts in (
            eligible_resources.items()
        ):
            resource = str(raw_resource).strip()

            if not resource:
                continue

            concepts = tuple(
                dict.fromkeys(
                    str(item).strip()
                    for item in raw_concepts
                    if str(item).strip()
                )
            )

            if concepts:
                result[resource] = concepts

        if not result:
            raise ValueError(
                "semantic translation requires an eligible resource catalog"
            )

        if len(result) > 50:
            raise ValueError(
                "semantic resource catalog exceeds governed bound"
            )

        if sum(
            len(concepts)
            for concepts in result.values()
        ) > 500:
            raise ValueError(
                "semantic concept catalog exceeds governed bound"
            )

        return result

    @staticmethod
    def _schema(
        catalog: Mapping[str, tuple[str, ...]],
    ) -> Mapping[str, Any]:
        all_concepts = tuple(
            dict.fromkeys(
                concept
                for concepts in catalog.values()
                for concept in concepts
            )
        )

        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "resolved": {
                    "type": "boolean",
                },
                "resource_type": {
                    "type": "string",
                    "enum": list(catalog),
                },
                "requested_concepts": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": list(
                            all_concepts
                        ),
                    },
                    "uniqueItems": True,
                    "maxItems": min(
                        20,
                        len(all_concepts),
                    ),
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
            "required": [
                "resolved",
                "resource_type",
                "requested_concepts",
                "confidence",
            ],
        }

    @staticmethod
    def _decode_output(
        response: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        top_level = response.get("output_text")
        if isinstance(top_level, str):
            return OpenAISemanticIntentTranslator._decode_json(
                top_level
            )

        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, Mapping):
                    continue

                content = item.get("content")
                if not isinstance(content, list):
                    continue

                for part in content:
                    if not isinstance(
                        part,
                        Mapping,
                    ):
                        continue

                    if (
                        part.get("type")
                        == "output_text"
                        and isinstance(
                            part.get("text"),
                            str,
                        )
                    ):
                        return (
                            OpenAISemanticIntentTranslator._decode_json(
                                part["text"]
                            )
                        )

        raise ValueError(
            "OpenAI response did not contain structured output text"
        )

    @staticmethod
    def _decode_json(
        raw: str,
    ) -> Mapping[str, Any]:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                "OpenAI semantic response was not valid JSON"
            ) from error

        if not isinstance(decoded, Mapping):
            raise ValueError(
                "OpenAI semantic response must be a JSON object"
            )

        return dict(decoded)

    @staticmethod
    def _usage(
        response: Mapping[str, Any],
    ) -> OpenAITranslationUsage:
        raw = response.get("usage")

        if not isinstance(raw, Mapping):
            return OpenAITranslationUsage()

        return OpenAITranslationUsage(
            input_tokens=int(
                raw.get("input_tokens", 0) or 0
            ),
            output_tokens=int(
                raw.get("output_tokens", 0) or 0
            ),
            total_tokens=int(
                raw.get("total_tokens", 0) or 0
            ),
        )
