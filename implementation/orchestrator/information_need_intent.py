"""Ground provider-independent information needs into existing governed intents.

Capability selection has already happened in the backend fulfillment layer before this
module runs. This adapter never changes the selected capability, target, authority, or
human information need. It only binds the already-grounded target value to one selector
name structurally offered by that capability so the existing request factory and Central
Orchestrator can be reused during migration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .conversation_kernel import InformationNeed, ValidatedReasoningPool
from .information_fulfillment import FulfillmentCapability, FulfillmentStep
from .semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER
from .teams_conversation_flow import ConversationIntent, ConversationIntentPlan


class InformationNeedIntentError(ValueError):
    """A bounded information-need grounding proposal was invalid."""


@dataclass(frozen=True, slots=True)
class PlannedInformationNeed:
    """One validated information need paired with its backend fulfillment choice."""

    need: InformationNeed
    step: FulfillmentStep
    capability: FulfillmentCapability

    def __post_init__(self) -> None:
        if self.step.capability_name != self.capability.capability_name:
            raise InformationNeedIntentError(
                "fulfillment step and capability do not describe the same capability"
            )
        if self.need.target.reference != self.step.target_reference:
            raise InformationNeedIntentError(
                "fulfillment step changed the grounded information target"
            )
        if self.need.target.source != self.step.target_source:
            raise InformationNeedIntentError(
                "fulfillment step changed the grounded target source"
            )
        if self.need.authority != self.step.authority:
            raise InformationNeedIntentError(
                "fulfillment step changed the requested authority"
            )
        if self.need.need != self.step.information_need:
            raise InformationNeedIntentError(
                "fulfillment step changed the human information need"
            )


@dataclass(frozen=True, slots=True)
class InformationNeedIntentBuilder:
    """Adapt backend fulfillment choices into the existing governed intent contract.

    The language model, when needed, may choose only a selector *name* from the
    structurally declared selector keys. The selector value is never model-generated;
    it is copied from the already validated InformationTarget. A single-selector
    capability requires no model call at all.
    """

    reasoning: ValidatedReasoningPool

    def build(
        self,
        *,
        human_text: str,
        planned: Sequence[PlannedInformationNeed],
    ) -> ConversationIntent | ConversationIntentPlan:
        clean_text = human_text.strip()
        if not clean_text:
            raise ValueError("human_text is required")
        items = tuple(planned)
        if not items:
            raise InformationNeedIntentError(
                "at least one planned information need is required"
            )

        groups: dict[tuple[str, str, str, str], list[PlannedInformationNeed]] = {}
        order: list[tuple[str, str, str, str]] = []
        for item in items:
            key = (
                item.capability.capability_name,
                item.need.target.source,
                item.need.target.reference,
                item.need.authority,
            )
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(item)

        intents: list[ConversationIntent] = []
        for key in order:
            group = tuple(groups[key])
            first = group[0]
            if any(item.capability != first.capability for item in group):
                raise InformationNeedIntentError(
                    "coalesced information needs disagree on capability contract"
                )
            arguments = self._arguments(
                human_text=clean_text,
                items=group,
                capability=first.capability,
            )
            intents.append(
                ConversationIntent(
                    capability_name=first.capability.capability_name,
                    arguments=arguments,
                    permission_mode=first.need.authority,
                    risk=first.capability.risk,
                )
            )

        if len(intents) == 1:
            return intents[0]
        return ConversationIntentPlan(intents=tuple(intents))

    def _arguments(
        self,
        *,
        human_text: str,
        items: tuple[PlannedInformationNeed, ...],
        capability: FulfillmentCapability,
    ) -> Mapping[str, Any]:
        requested_facts = _canonical_requested_facts(
            human_text=human_text,
            items=items,
        )

        selector_keys = tuple(
            dict.fromkeys(key.strip() for key in capability.selector_keys if key.strip())
        )
        if not selector_keys:
            return {
                "requested_facts": list(requested_facts),
            }

        target = items[0].need.target
        if any(item.need.target != target for item in items):
            raise InformationNeedIntentError(
                "one intent cannot bind several different grounded targets"
            )

        if target.selector is not None:
            selector_name = target.selector.strip()
            if selector_name not in selector_keys:
                raise InformationNeedIntentError(
                    "grounded target selector is not supported by selected capability"
                )
        elif (
            not capability.selector_required
            and capability.collection_scope is not None
        ):
            # The capability contract explicitly authorizes a selectorless
            # collection read. No model may manufacture a selector simply
            # because selector keys also exist.
            return {
                "requested_facts": list(requested_facts),
            }
        elif len(selector_keys) == 1:
            selector_name = selector_keys[0]
        else:
            selector_name, _ = self.reasoning.complete_validated(
                system=(
                    "You are Jason's bounded backend resource-selector grounding step. "
                    "The Conversation Kernel has already determined the human target and "
                    "information need, and the fulfillment layer has already selected the "
                    "governed capability. Choose only which offered selector argument name "
                    "best represents the already-grounded target reference for that "
                    "capability. Do not select another capability, provider, connector, "
                    "resource, API operation, or target. Do not transform or return the "
                    "target value. Return only the required structured object."
                ),
                user=json.dumps(
                    {
                        "target_kind": target.kind,
                        "target_source": target.source,
                        "information_needs": [item.need.need for item in items],
                        "capability": {
                            "description": capability.description,
                            "operation": capability.operation,
                            "selector_keys": list(selector_keys),
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["argument"],
                    "properties": {
                        "argument": {
                            "type": "string",
                            "enum": list(selector_keys),
                        }
                    },
                },
                max_output_tokens=64,
                validator=lambda proposal: _validate_selector(
                    proposal=proposal,
                    selector_keys=selector_keys,
                ),
            )

        return {
            selector_name: target.reference,
            # requested_facts carries the already-grounded information obligation,
            # not the entire human utterance. Canonicalization is provider-neutral
            # and cannot change capability, target, selector, authority, or value.
            "requested_facts": list(requested_facts),
        }


def _canonical_requested_facts(
    *,
    human_text: str,
    items: tuple[PlannedInformationNeed, ...],
) -> tuple[str, ...]:
    """Preserve bounded information needs as canonical fact obligations.

    For one information need, the original human sentence may supply an explicit
    registered semantic term such as "needs to be restarted". For multiple needs,
    each validated need is canonicalized independently so one explicit term cannot
    collapse several requested facts into a single obligation.

    Unknown concepts remain conservative passthrough facts.
    """

    raw = tuple(
        dict.fromkeys(
            item.need.need.strip()
            for item in items
            if item.need.need.strip()
        )
    )

    if not raw:
        raise InformationNeedIntentError(
            "planned information need is empty"
        )

    if len(raw) == 1:
        canonical = (
            DEFAULT_SEMANTIC_FACT_RESOLVER
            .canonicalize_requested_facts(
                human_text=human_text,
                requested_facts=raw,
            )
        )
    else:
        values: list[str] = []

        for fact in raw:
            resolved = (
                DEFAULT_SEMANTIC_FACT_RESOLVER
                .canonicalize_requested_facts(
                    human_text=fact,
                    requested_facts=(fact,),
                )
            )

            for value in resolved:
                clean = str(value).strip()

                if (
                    clean
                    and clean not in values
                ):
                    values.append(clean)

        canonical = tuple(values)

    if not canonical:
        raise InformationNeedIntentError(
            "planned information need produced no fact obligation"
        )

    return tuple(canonical)


def _validate_selector(
    *,
    proposal: Mapping[str, Any],
    selector_keys: tuple[str, ...],
) -> str:
    if not isinstance(proposal, Mapping):
        raise InformationNeedIntentError("selector proposal must be an object")
    if set(proposal) != {"argument"}:
        raise InformationNeedIntentError(
            "selector proposal may contain only the offered argument name"
        )
    argument = str(proposal.get("argument", "")).strip()
    if argument not in set(selector_keys):
        raise InformationNeedIntentError(
            "selector proposal chose an argument outside the capability contract"
        )
    return argument
