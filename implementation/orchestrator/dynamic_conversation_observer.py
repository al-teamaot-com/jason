"""Derive provider-independent conversation entities from verified Jason responses.

The observer contains no provider, field, question, or synonym mappings. It receives
only response text that has already been assembled from governed orchestration
results. A bounded model may identify referable entities, but deterministic code
accepts only exact substrings of the sanitized response and generates Jason-owned
entity references itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .dynamic_conversation_kernel import (
    ConversationEntity,
    DynamicConversationContext,
)
from .evidence_sanitization import REDACTED, sanitize_evidence_tree


_MAX_OBSERVED_ENTITIES = 8
_MAX_ENTITY_LITERAL_CHARS = 256
_MAX_KIND_CHARS = 64
_KIND_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class DynamicConversationObservationError(ValueError):
    """A model observation was not grounded in verified response text."""


class StructuredObservationClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class DynamicConversationEntityObserver:
    """Project bounded referable entities from a verified conversational response."""

    client: StructuredObservationClient

    def observe(
        self,
        *,
        context: DynamicConversationContext,
        response_text: str,
        provenance: str,
    ) -> DynamicConversationContext:
        clean_provenance = provenance.strip()
        if not clean_provenance:
            raise ValueError("conversation observation provenance is required")

        sanitized = sanitize_evidence_tree(response_text)
        if not isinstance(sanitized, str):
            raise TypeError("sanitized conversation response must remain text")
        sanitized = sanitized.strip()
        if not sanitized or sanitized == REDACTED:
            return context

        payload = {
            "verified_response": sanitized,
            "existing_entities": [
                {
                    "ref": item.ref,
                    "kind": item.kind,
                    "canonical_id": item.canonical_id,
                    "display_name": item.display_name,
                }
                for item in context.entities
            ],
            "grounding_rule": (
                "canonical_literal and display_literal must each be copied exactly "
                "from verified_response; do not normalize or manufacture values"
            ),
        }
        proposal = self.client.complete(
            system=_OBSERVATION_INSTRUCTIONS,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema=_observation_schema(),
            max_output_tokens=384,
        )
        entities, active = _validate_observations(
            proposal=proposal,
            response_text=sanitized,
            provenance=clean_provenance,
        )
        if not entities:
            return context
        return context.with_verified_entities(
            entities,
            active_kinds=active,
        )


_OBSERVATION_INSTRUCTIONS = """You are Jason's bounded conversation-context observer. The supplied response text is a verified Jason response produced after normal identity, authorization, capability resolution, provider execution, evidence interpretation, and response rendering. Identify only concrete entities that a human could naturally refer to in a later conversational turn. Do not create semantic mappings, infer hidden identities, normalize names, or convert facts into new values. Every canonical_literal and display_literal must be an exact contiguous substring of verified_response. Use a short provider-independent kind such as device, person, ticket, mailbox, organization, document, or another kind justified by the text; these are examples, not a closed vocabulary. Mark an entity active only when the response makes it a clear conversational subject. Do not extract credentials, secrets, recovery material, tokens, or opaque authorization values. Return no entity rather than guessing. Return only the required structured object."""


def _observation_schema() -> Mapping[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["entities"],
        "properties": {
            "entities": {
                "type": "array",
                "maxItems": _MAX_OBSERVED_ENTITIES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "kind",
                        "canonical_literal",
                        "display_literal",
                        "make_active",
                    ],
                    "properties": {
                        "kind": {
                            "type": "string",
                            "maxLength": _MAX_KIND_CHARS,
                        },
                        "canonical_literal": {
                            "type": "string",
                            "maxLength": _MAX_ENTITY_LITERAL_CHARS,
                        },
                        "display_literal": {
                            "type": "string",
                            "maxLength": _MAX_ENTITY_LITERAL_CHARS,
                        },
                        "make_active": {"type": "boolean"},
                    },
                },
            }
        },
    }


def _validate_observations(
    *,
    proposal: Mapping[str, Any],
    response_text: str,
    provenance: str,
) -> tuple[tuple[ConversationEntity, ...], Mapping[str, str]]:
    raw_entities = proposal.get("entities", ())
    if not isinstance(raw_entities, Sequence) or isinstance(raw_entities, (str, bytes)):
        raise DynamicConversationObservationError("observed entities must be an array")
    if len(raw_entities) > _MAX_OBSERVED_ENTITIES:
        raise DynamicConversationObservationError("observed entity count exceeds safety bound")

    entities: list[ConversationEntity] = []
    active: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()

    for raw in raw_entities:
        if not isinstance(raw, Mapping):
            raise DynamicConversationObservationError("observed entity must be an object")
        kind = str(raw.get("kind", "")).strip()
        canonical = str(raw.get("canonical_literal", "")).strip()
        display = str(raw.get("display_literal", "")).strip()
        make_active = raw.get("make_active")

        if not _KIND_PATTERN.fullmatch(kind):
            raise DynamicConversationObservationError("observed entity kind is invalid")
        for value in (canonical, display):
            if (
                not value
                or len(value) > _MAX_ENTITY_LITERAL_CHARS
                or value == REDACTED
                or value not in response_text
            ):
                raise DynamicConversationObservationError(
                    "observed entity literal is not grounded verbatim in verified response"
                )
        if not isinstance(make_active, bool):
            raise DynamicConversationObservationError("observed entity active flag is invalid")

        dedupe = (kind.casefold(), canonical.casefold())
        if dedupe in seen:
            continue
        seen.add(dedupe)
        ref = _entity_ref(kind=kind, canonical=canonical)
        entity = ConversationEntity(
            ref=ref,
            kind=kind,
            canonical_id=canonical,
            display_name=display,
            provenance=provenance,
        )
        entities.append(entity)
        if make_active:
            existing = active.get(kind)
            if existing is not None and existing != ref:
                raise DynamicConversationObservationError(
                    "multiple observed entities cannot become active for one kind"
                )
            active[kind] = ref

    return tuple(entities), active


def _entity_ref(*, kind: str, canonical: str) -> str:
    digest = hashlib.sha256(
        f"{kind.casefold()}\0{canonical.casefold()}".encode("utf-8")
    ).hexdigest()[:20]
    return f"entity-{digest}"
