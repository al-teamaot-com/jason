"""Generic evidence-driven investigation decision engine.

The model does not select providers, connectors, capability names, API endpoints,
field paths, or selector values.

It may only:
- request one currently available compiled broker operation,
- declare that current evidence is sufficient to answer, or
- declare that the currently available integrations cannot establish the answer.

All execution remains outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Mapping, Protocol, Sequence

from .dynamic_conversation_kernel import DynamicConversationContext
from .integration_broker import (
    IntegrationBroker,
    broker_model_context,
    broker_operation_targets,
    resolve_operation_ref,
)


class StructuredInvestigationClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


class InvestigationDecisionKind(str, Enum):
    INSPECT = "inspect"
    ANSWER = "answer"
    CANNOT_ESTABLISH = "cannot_establish"


@dataclass(frozen=True, slots=True)
class InvestigationDecision:
    kind: InvestigationDecisionKind
    operation_ref: str | None
    information_goal: str | None


@dataclass(frozen=True, slots=True)
class InvestigationDecisionEngine:
    client: StructuredInvestigationClient

    def decide(
        self,
        *,
        human_text: str,
        broker: IntegrationBroker,
        context: DynamicConversationContext | None = None,
        evidence: Sequence[Mapping[str, Any]] = (),
        excluded_operation_refs: Sequence[str] = (),
    ) -> InvestigationDecision:
        if not human_text.strip():
            raise ValueError(
                "investigation requires non-empty human text"
            )

        model_context = broker_model_context(broker)

        eligible_targets = _eligible_operation_targets(
            broker=broker,
            context=context,
        )

        excluded_refs = {
            str(ref).strip()
            for ref in excluded_operation_refs
            if str(ref).strip()
        }

        eligible_targets = tuple(
            target
            for target in eligible_targets
            if target.operation_ref not in excluded_refs
        )

        allowed_refs = tuple(
            target.operation_ref
            for target in eligible_targets
        )

        allowed_ref_set = set(allowed_refs)

        # Keep model-visible operations synchronized with the strict operation
        # enum. An operation that cannot currently be grounded must not appear
        # to the model as an available next observation.
        visible_resources = []

        for resource in model_context["resources"]:
            item = dict(resource)
            item["operations"] = [
                operation
                for operation in resource.get("operations", ())
                if operation.get("operation_ref") in allowed_ref_set
            ]

            if item["operations"]:
                visible_resources.append(item)

        result = self.client.complete(
            system=_SYSTEM,
            user=json.dumps(
                {
                    "request": human_text,
                    "available_resources": visible_resources,
                    "established_evidence": [
                        dict(item)
                        for item in evidence
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_schema(allowed_refs),
            max_output_tokens=320,
        )

        if not isinstance(result, Mapping):
            raise ValueError(
                "investigation decision must be an object"
            )

        return _validate_decision(
            result=result,
            broker=broker,
        )



def _eligible_operation_targets(
    *,
    broker: IntegrationBroker,
    context: DynamicConversationContext | None,
):
    """Return operations whose grounding prerequisites currently exist.

    This filters only by generic grounding feasibility.

    It does not:
    - choose providers,
    - interpret the human request,
    - construct selector values,
    - normalize identifiers,
    - infer identities,
    - grant authority.
    """

    active_identity_kinds: set[str] = set()

    if context is not None:
        active_identity_kinds = {
            str(kind).strip()
            for kind, ref
            in context.active_entity_refs.items()
            if str(kind).strip()
            and str(ref).strip()
        }

    eligible = []

    for target in broker_operation_targets(broker):
        selector_names = tuple(
            target.operation.selector_names
        )

        # No selector required.
        if not selector_names:
            eligible.append(target)
            continue

        # A collection/search operation may be attempted before durable
        # identity has been established.
        if target.operation.collection_supported:
            eligible.append(target)
            continue

        selector_definitions = {
            selector.name: selector
            for selector in target.resource.selectors
        }

        required = []

        valid = True

        for selector_name in selector_names:
            definition = selector_definitions.get(
                selector_name
            )

            if definition is None:
                valid = False
                break

            required.append(definition)

        # Broker registration should prevent this, but fail closed if an
        # inconsistent manifest reaches runtime.
        if not valid:
            continue

        # At least one selector can be grounded directly under the existing
        # grounding contract.
        if any(
            not definition.verified_identity_required
            for definition in required
        ):
            eligible.append(target)
            continue

        # Every selector is verified-identity-only. Such an operation becomes
        # eligible only after conversation context actually contains a
        # verified entity reference.
        if (
            target.resource.resource_type
            in active_identity_kinds
        ):
            eligible.append(target)

    return tuple(eligible)

def _validate_decision(
    *,
    result: Mapping[str, Any],
    broker: IntegrationBroker,
) -> InvestigationDecision:
    try:
        kind = InvestigationDecisionKind(
            str(result["decision"])
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(
            "invalid investigation decision kind"
        ) from exc

    raw_ref = result.get("operation_ref")
    operation_ref = (
        str(raw_ref).strip()
        if raw_ref is not None
        else None
    )

    raw_goal = result.get("information_goal")
    information_goal = (
        str(raw_goal).strip()
        if raw_goal is not None
        else None
    )

    if kind is InvestigationDecisionKind.INSPECT:
        if not operation_ref:
            raise ValueError(
                "inspect decision requires operation_ref"
            )

        if not information_goal:
            raise ValueError(
                "inspect decision requires information_goal"
            )

        try:
            resolve_operation_ref(
                broker,
                operation_ref,
            )
        except LookupError as exc:
            raise ValueError(
                "inspect decision references an unavailable operation"
            ) from exc

    else:
        # A terminal decision may not carry an executable operation reference.
        # Preserve that authority boundary.
        if operation_ref is not None:
            raise ValueError(
                "non-inspect decision cannot contain operation_ref"
            )

        # information_goal is harmless surplus reasoning metadata on a terminal
        # decision. Ignore it rather than failing an otherwise usable answer.
        information_goal = None

    return InvestigationDecision(
        kind=kind,
        operation_ref=operation_ref,
        information_goal=information_goal,
    )


def _schema(
    allowed_refs: tuple[str, ...],
) -> Mapping[str, Any]:
    operation_schema: Mapping[str, Any]

    if allowed_refs:
        operation_schema = {
            "anyOf": [
                {
                    "type": "string",
                    "enum": list(allowed_refs),
                },
                {
                    "type": "null",
                },
            ]
        }
    else:
        operation_schema = {
            "type": "null",
        }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "decision",
            "operation_ref",
            "information_goal",
        ],
        "properties": {
            "decision": {
                "type": "string",
                "enum": [
                    "inspect",
                    "answer",
                    "cannot_establish",
                ],
            },
            "operation_ref": operation_schema,
            "information_goal": {
                "anyOf": [
                    {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 240,
                    },
                    {
                        "type": "null",
                    },
                ]
            },
        },
    }


_SYSTEM = """
You are Jason's evidence-driven investigation decision component.

Your job is NOT to answer the technician and NOT to construct a complete query
plan.

Given:
- the technician's request,
- the resources and observations currently available through Jason,
- any governed evidence already established in this investigation,

choose exactly one next decision.

DECISION: inspect
Use this when another governed observation would materially improve the answer.
Select exactly one supplied operation_ref and state briefly what information
Jason should try to establish from that observation.

DECISION: answer
Use this only when the established evidence is already sufficient to answer the
technician's request without another provider read.

DECISION: cannot_establish
Use this only when the available governed resources cannot establish the
requested information.

Rules:
- Never invent an operation_ref.
- Never name or infer a provider, vendor, connector, capability, API, endpoint,
  database, implementation, or field path.
- Never invent selector values.
- Never turn a human-readable selector into durable identity.
- Never request an action or mutation.
- Prefer useful evidence, not exhaustive reads.
- Do not inspect another resource when existing evidence is already sufficient.
- Additional integrations may expose additional observations; reason only from
  the resources supplied in this turn.
- Do not answer the technician's substantive question.
- Return only the structured object required by the schema.
""".strip()
