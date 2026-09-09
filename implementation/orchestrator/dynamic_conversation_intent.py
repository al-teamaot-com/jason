"""Ground dynamic conversational plans into normal governed ConversationIntent objects.

The binder contains no question-to-field or phrase-to-provider mappings.  A model may
choose only argument names exposed by the selected capability at runtime and may bind
only values that are already grounded in verified conversation entities or appear
verbatim in the human message.  Deterministic validation dereferences those sources
before the Central Orchestrator sees an intent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .dynamic_conversation_kernel import (
    DynamicConversationContext,
    DynamicConversationPlan,
    OfferedConversationCapability,
)
from .teams_conversation_flow import ConversationIntent, ConversationIntentPlan


_MAX_BINDINGS = 16
_MAX_LITERAL_CHARS = 512


class DynamicIntentBindingError(ValueError):
    """A proposed argument binding was not grounded in authorized conversation input."""


class StructuredIntentBindingClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class GroundedConversationIntentBuilder:
    """Convert a validated dynamic plan into existing governed intent contracts."""

    client: StructuredIntentBindingClient

    def build(
        self,
        *,
        text: str,
        context: DynamicConversationContext,
        plan: DynamicConversationPlan,
        capabilities: Sequence[OfferedConversationCapability],
    ) -> ConversationIntent | ConversationIntentPlan | None:
        if plan.outcome != "plan":
            return None

        offered = {item.capability_id: item for item in capabilities}
        intents: list[ConversationIntent] = []
        for requirement in plan.requirements:
            capability = offered.get(requirement.capability_id)
            if capability is None:
                raise DynamicIntentBindingError("planned capability is no longer offered")
            arguments = self._bind(
                text=text,
                context=context,
                capability=capability,
                entity_refs=requirement.entity_refs,
                purpose=requirement.purpose,
            )
            intents.append(
                ConversationIntent(
                    capability_name=capability.capability_id,
                    arguments=arguments,
                    permission_mode=capability.permission_mode,
                    risk=capability.risk,
                )
            )

        if len(intents) == 1:
            return intents[0]
        return ConversationIntentPlan(intents=tuple(intents))

    def _bind(
        self,
        *,
        text: str,
        context: DynamicConversationContext,
        capability: OfferedConversationCapability,
        entity_refs: tuple[str, ...],
        purpose: str,
    ) -> Mapping[str, Any]:
        selector_keys = tuple(
            str(item).strip()
            for item in capability.input_schema.get("selector_keys", ())
            if str(item).strip()
        )
        if not selector_keys:
            # A capability without exposed structural selectors may still receive the
            # natural-language information request.  No identifier is manufactured.
            return {"requested_facts": [text.strip()]}

        entities = [context.entity(ref) for ref in entity_refs]
        entity_sources: list[dict[str, str]] = []
        for entity in entities:
            entity_sources.extend(
                (
                    {
                        "source_id": f"{entity.ref}:canonical_id",
                        "entity_ref": entity.ref,
                        "value_kind": "canonical_id",
                        "value": entity.canonical_id,
                        "kind": entity.kind,
                    },
                    {
                        "source_id": f"{entity.ref}:display_name",
                        "entity_ref": entity.ref,
                        "value_kind": "display_name",
                        "value": entity.display_name,
                        "kind": entity.kind,
                    },
                )
            )

        payload = {
            "message": text.strip(),
            "purpose": purpose,
            "capability": capability.model_view(),
            "allowed_argument_names": list(selector_keys),
            "verified_entity_sources": entity_sources,
            "literal_rule": (
                "A literal binding value must be copied exactly from the human message."
            ),
        }
        proposal = self.client.complete(
            system=_BINDING_INSTRUCTIONS,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema=_binding_schema(selector_keys, tuple(item["source_id"] for item in entity_sources)),
            max_output_tokens=384,
        )
        arguments = _validate_and_dereference(
            proposal=proposal,
            text=text.strip(),
            selector_keys=set(selector_keys),
            entity_sources={item["source_id"]: item["value"] for item in entity_sources},
        )
        # Existing read capabilities use requested_facts as a provider-neutral signal
        # that a resolved resource should be read for the human's information request.
        # The value is the original human language, not a mapped/canonical fact name.
        arguments["requested_facts"] = [text.strip()]
        return arguments


_BINDING_INSTRUCTIONS = """You are Jason's bounded argument grounding step. Bind a selected governed capability using only the argument names supplied for that capability and values grounded in the current human message or verified conversation entities. There are no hidden field mappings, synonym tables, or provider-specific rules. Choose argument names by reasoning from the capability description/schema and source meaning. For a verified entity source, return its source_id; deterministic code will dereference the actual value. For a literal source, copy an exact contiguous substring from the human message. Never invent, normalize, expand, infer, or transform identifiers or values. Omit bindings that are not necessary. If the available grounded sources cannot safely satisfy a required selector, return no binding rather than guessing. Return only the structured object required by the schema."""


def _binding_schema(selector_keys: tuple[str, ...], source_ids: tuple[str, ...]) -> Mapping[str, Any]:
    source_id_schema: dict[str, Any] = {"type": ["string", "null"]}
    if source_ids:
        source_id_schema["enum"] = [*source_ids, None]
    else:
        source_id_schema["enum"] = [None]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["bindings"],
        "properties": {
            "bindings": {
                "type": "array",
                "maxItems": _MAX_BINDINGS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["argument", "source_type", "source_id", "literal"],
                    "properties": {
                        "argument": {"type": "string", "enum": list(selector_keys)},
                        "source_type": {"type": "string", "enum": ["entity", "literal"]},
                        "source_id": source_id_schema,
                        "literal": {"type": ["string", "null"], "maxLength": _MAX_LITERAL_CHARS},
                    },
                },
            }
        },
    }


def _validate_and_dereference(
    *,
    proposal: Mapping[str, Any],
    text: str,
    selector_keys: set[str],
    entity_sources: Mapping[str, str],
) -> dict[str, Any]:
    raw_bindings = proposal.get("bindings", ())
    if not isinstance(raw_bindings, Sequence) or isinstance(raw_bindings, (str, bytes)):
        raise DynamicIntentBindingError("bindings must be an array")
    if len(raw_bindings) > _MAX_BINDINGS:
        raise DynamicIntentBindingError("binding count exceeds safety bound")

    arguments: dict[str, Any] = {}
    for raw in raw_bindings:
        if not isinstance(raw, Mapping):
            raise DynamicIntentBindingError("binding must be an object")
        argument = str(raw.get("argument", "")).strip()
        if argument not in selector_keys:
            raise DynamicIntentBindingError("binding selected an argument not exposed by capability")
        if argument in arguments:
            raise DynamicIntentBindingError("duplicate argument binding is not permitted")

        source_type = str(raw.get("source_type", "")).strip()
        source_id = raw.get("source_id")
        literal = raw.get("literal")
        if source_type == "entity":
            if literal is not None:
                raise DynamicIntentBindingError("entity binding cannot carry a literal")
            clean_source_id = "" if source_id is None else str(source_id).strip()
            if clean_source_id not in entity_sources:
                raise DynamicIntentBindingError("entity binding source is not verified")
            value = entity_sources[clean_source_id]
        elif source_type == "literal":
            if source_id is not None:
                raise DynamicIntentBindingError("literal binding cannot carry an entity source")
            if literal is None:
                raise DynamicIntentBindingError("literal binding requires an exact message substring")
            value = str(literal)
            if not value or len(value) > _MAX_LITERAL_CHARS or value not in text:
                raise DynamicIntentBindingError("literal binding is not grounded verbatim in human message")
        else:
            raise DynamicIntentBindingError("binding source type is invalid")
        arguments[argument] = value

    return arguments
