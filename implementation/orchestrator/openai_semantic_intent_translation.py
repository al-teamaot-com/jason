from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass
from time import monotonic
from typing import Any, Mapping, Protocol

from usage_ledger.adapters import from_openai_response
from usage_ledger.contracts import (
    AttemptOutcome,
    TokenUsage,
    UsageContext,
    UsageEntry,
    UsageLedger,
    UsageSource,
)
from usage_ledger.runtime_context import new_attempt_context

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
    """OpenAI-backed semantic concept translation with no execution authority."""

    api_key: str
    transport: JsonHttpTransport
    model: str
    endpoint: str = "https://api.openai.com/v1/responses"
    timeout_seconds: float = 30.0
    max_output_tokens: int = 128
    usage_ledger: UsageLedger | None = None

    def translate(
        self,
        *,
        text: str,
        eligible_concepts: tuple[str, ...],
        grounded_selector: Mapping[str, str] | None = None,
    ) -> SemanticIntentTranslation | None:
        return self.translate_with_usage(
            text=text,
            eligible_concepts=eligible_concepts,
            grounded_selector=grounded_selector,
        ).translation

    def translate_with_usage(
        self,
        *,
        text: str,
        eligible_concepts: tuple[str, ...],
        grounded_selector: Mapping[str, str] | None = None,
    ) -> OpenAITranslationOutcome:
        concepts = self._normalize_concepts(
            eligible_concepts
        )

        # Jason may tell the semantic provider only whether a grounded target
        # exists. The provider never receives or returns the selector itself.
        grounded_target_present = bool(
            grounded_selector
        )

        payload = {
            "model": self.model,
            "instructions": (
                "Translate the human request into the smallest complete set "
                "of canonical semantic concepts from the supplied catalog. "
                "Return only concepts necessary to answer what the human "
                "actually asked. Do not add useful, adjacent, diagnostic, "
                "or related concepts. "
                "Examples of semantic precision: "
                "CPU normally means processor model; do not add logical "
                "processor count unless quantity/count was requested. "
                "A generic request for an endpoint's IP address requires "
                "both LAN IP address and WAN IP address because both are "
                "needed to completely satisfy that bounded ambiguity. "
                "A request about alerts maps to open alerts whether it refers "
                "to a specific grounded endpoint or to the environment broadly. "
                "Do not infer implementation topology from target presence. "
                "You do not select target identity, scope, resource type, "
                "provider, connector, capability, tool, agent, credential, "
                "permission, API route, or action. "
                "If the request cannot be represented confidently by the "
                "supplied concepts, return resolved=false with an empty "
                "requested_concepts array."
            ),
            "input": json.dumps(
                {
                    "human_text": text,
                    "eligible_concepts": concepts,
                    "grounded_target_present":
                        grounded_target_present,
                },
                sort_keys=True,
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "jason_semantic_intent",
                    "strict": True,
                    "schema": self._schema(
                        concepts
                    ),
                }
            },
            "max_output_tokens":
                self.max_output_tokens,
        }

        usage_context = new_attempt_context()
        started_at = datetime.now(timezone.utc)
        started_clock = monotonic()
        try:
            response = self.transport.request(
                method="POST",
                url=self.endpoint,
                headers={
                    "Authorization":
                        f"Bearer {self.api_key}",
                    "Content-Type":
                        "application/json",
                },
                json=payload,
                timeout_seconds=
                    self.timeout_seconds,
            )
        except Exception as error:
            self._record_failed_attempt(
                context=usage_context,
                started_at=started_at,
                duration_ms=int((monotonic() - started_clock) * 1000),
                outcome=(
                    AttemptOutcome.TIMED_OUT
                    if isinstance(error, TimeoutError)
                    else AttemptOutcome.FAILED
                ),
            )
            raise

        if self.usage_ledger is not None and usage_context is not None:
            self.usage_ledger.append(
                from_openai_response(
                    context=usage_context,
                    model=self.model,
                    response=response,
                    started_at=started_at,
                    duration_ms=int((monotonic() - started_clock) * 1000),
                )
            )

        usage = self._usage(response)
        decoded = self._decode_output(
            response
        )

        if decoded.get("resolved") is not True:
            return OpenAITranslationOutcome(
                translation=None,
                usage=usage,
            )

        raw_concepts = decoded.get(
            "requested_concepts"
        )

        if not isinstance(
            raw_concepts,
            list,
        ):
            raise ValueError(
                "semantic provider requested_concepts must be a list"
            )

        allowed = set(concepts)
        selected: list[str] = []

        for raw in raw_concepts:
            concept = str(raw).strip()

            if concept not in allowed:
                raise PermissionError(
                    "semantic provider selected concept outside governed catalog"
                )

            if concept not in selected:
                selected.append(concept)

        if not selected:
            return OpenAITranslationOutcome(
                translation=None,
                usage=usage,
            )

        translation = SemanticIntentTranslation(
            requested_concepts=
                tuple(selected),
            operation="read",
            confidence=float(
                decoded.get(
                    "confidence",
                    0.0,
                )
            ),
        )

        return OpenAITranslationOutcome(
            translation=translation,
            usage=usage,
        )

    def _record_failed_attempt(
        self,
        *,
        context: UsageContext | None,
        started_at: datetime,
        duration_ms: int,
        outcome: AttemptOutcome,
    ) -> None:
        if self.usage_ledger is None or context is None:
            return
        self.usage_ledger.append(
            UsageEntry(
                entry_id=context.attempt_id,
                context=context,
                provider="openai",
                model=self.model,
                outcome=outcome,
                usage_source=UsageSource.UNKNOWN,
                tokens=TokenUsage(),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                duration_ms=duration_ms,
                confidence=0.0,
            )
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
            raise ValueError(
                "semantic translation requires an eligible concept catalog"
            )

        if len(concepts) > 500:
            raise ValueError(
                "semantic concept catalog exceeds governed bound"
            )

        return concepts

    @staticmethod
    def _schema(
        concepts: tuple[str, ...],
    ) -> Mapping[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "resolved": {
                    "type": "boolean",
                },
                "requested_concepts": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": list(concepts),
                    },
                    "maxItems": min(
                        20,
                        len(concepts),
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
                "requested_concepts",
                "confidence",
            ],
        }

    @staticmethod
    def _decode_output(
        response: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        top_level = response.get(
            "output_text"
        )

        if isinstance(
            top_level,
            str,
        ):
            return (
                OpenAISemanticIntentTranslator
                ._decode_json(
                    top_level
                )
            )

        output = response.get(
            "output"
        )

        if isinstance(output, list):
            for item in output:
                if not isinstance(
                    item,
                    Mapping,
                ):
                    continue

                content = item.get(
                    "content"
                )

                if not isinstance(
                    content,
                    list,
                ):
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
                            OpenAISemanticIntentTranslator
                            ._decode_json(
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
            decoded = json.loads(
                raw
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                "OpenAI semantic response was not valid JSON"
            ) from error

        if not isinstance(
            decoded,
            Mapping,
        ):
            raise ValueError(
                "OpenAI semantic response must be a JSON object"
            )

        return dict(decoded)

    @staticmethod
    def _usage(
        response: Mapping[str, Any],
    ) -> OpenAITranslationUsage:
        raw = response.get(
            "usage"
        )

        if not isinstance(
            raw,
            Mapping,
        ):
            return OpenAITranslationUsage()

        return OpenAITranslationUsage(
            input_tokens=int(
                raw.get(
                    "input_tokens",
                    0,
                )
                or 0
            ),
            output_tokens=int(
                raw.get(
                    "output_tokens",
                    0,
                )
                or 0
            ),
            total_tokens=int(
                raw.get(
                    "total_tokens",
                    0,
                )
                or 0
            ),
        )
