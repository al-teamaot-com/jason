from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Protocol

from .ollama_reasoning import OllamaStructuredJsonClient
from .semantic_fact_resolver import (
    DEFAULT_SEMANTIC_FACT_RESOLVER,
    SemanticFactResolver,
)


class SemanticFactReasoner(Protocol):
    """Infer requested governed facts without resource or execution authority."""

    def infer(
        self,
        *,
        text: str,
        resource_type: str,
        resource_selector: Mapping[str, str],
        eligible_facts: tuple[str, ...],
    ) -> tuple[str, ...] | None: ...


@dataclass(frozen=True, slots=True)
class OllamaSemanticFactReasoner:
    """Classify free-form human wording into a closed governed fact vocabulary.

    The resource selector is supplied only as already-grounded context. The model's
    output schema contains no selector, provider, capability, tool, authority, or
    execution fields, so semantic language interpretation cannot change the target or
    cross an execution boundary.
    """

    client: OllamaStructuredJsonClient
    fact_resolver: SemanticFactResolver = DEFAULT_SEMANTIC_FACT_RESOLVER
    max_facts: int = 20

    def infer(
        self,
        *,
        text: str,
        resource_type: str,
        resource_selector: Mapping[str, str],
        eligible_facts: tuple[str, ...],
    ) -> tuple[str, ...] | None:
        allowed = tuple(dict.fromkeys(str(item).strip() for item in eligible_facts if str(item).strip()))
        if not allowed:
            return None
        if len(allowed) > 100:
            raise ValueError("semantic fact candidate set exceeds governed bound")

        candidates = []
        for fact in allowed:
            resolution = self.fact_resolver.resolve(fact)
            candidates.append(
                {
                    "canonical_fact": fact,
                    "expected_shape": (
                        resolution.expected_shape
                        if resolution is not None
                        else None
                    ),
                    "evidence_contexts": (
                        list(resolution.evidence_contexts)
                        if resolution is not None
                        else []
                    ),
                }
            )

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "resolved": {"type": "boolean"},
                "requested_facts": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(allowed)},
                    "maxItems": min(self.max_facts, len(allowed)),
                    "uniqueItems": True,
                },
            },
            "required": ["resolved", "requested_facts"],
        }

        result = self.client.complete(
            system=(
                "Interpret only what information the human is asking to know about an "
                "already-grounded resource. Infer meaning semantically across natural "
                "paraphrase, shorthand, ellipsis, word order, and relationship wording; "
                "do not require literal phrase overlap. Choose only from the supplied "
                "governed canonical facts and choose the smallest complete fact set that "
                "answers the request. Do not add merely useful or related facts. The "
                "resource target is already fixed and cannot be changed here. You have no "
                "authority to choose or describe selectors, providers, connectors, "
                "capabilities, tools, agents, credentials, tenant scope, permissions, or "
                "actions. If the requested meaning cannot be represented confidently by "
                "the supplied facts, return resolved=false and requested_facts=[]."
            ),
            user=json.dumps(
                {
                    "text": text,
                    "grounded_resource": {
                        "resource_type": resource_type,
                        "selector": dict(resource_selector),
                    },
                    "governed_fact_candidates": candidates,
                },
                sort_keys=True,
            ),
            schema=schema,
            max_output_tokens=96,
        )

        if result.get("resolved") is not True:
            return None

        raw = result.get("requested_facts")
        if not isinstance(raw, list) or not raw:
            return None

        allowed_set = set(allowed)
        selected: list[str] = []
        for item in raw:
            fact = str(item).strip()
            if fact not in allowed_set:
                raise PermissionError(
                    "semantic fact reasoner selected fact outside governed candidates"
                )
            if fact not in selected:
                selected.append(fact)

        if len(selected) > self.max_facts:
            raise ValueError("semantic fact selection exceeds governed bound")

        return tuple(selected)
