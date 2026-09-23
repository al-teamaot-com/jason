"""Temporary working-first Teams + DRMM read baseline.

Purpose:
- authenticate/bind the Teams human normally
- expose only authorized read-only endpoint capabilities
- resolve the human endpoint reference independently of the requested fact
- lock one provider-verified durable resource identity
- let the reasoning model iteratively choose useful reads
- keep every provider read behind the existing Central Orchestrator boundary
- answer only from governed provider evidence

This module intentionally does not contain provider fact mappings or
question-specific routing. It is a temporary baseline used to prove normal
agentic DRMM behavior before governance gates are reintroduced incrementally.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any, Protocol

from .evidence_sanitization import sanitize_evidence_tree
from .teams_conversation_experience import (
    BoundTeamsConversationIntentExecutor,
    TeamsConversationExperienceResult,
)
from .teams_conversation_flow import (
    ConversationIntent,
    TeamsConversationRequest,
)


class PermissiveReasoningClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, object],
        max_output_tokens: int,
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class _LockedResource:
    resource_id: str
    human_reference: str
    verified_match: Mapping[str, object]


_TARGET_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "has_endpoint_target",
        "human_reference",
    ],
    "properties": {
        "has_endpoint_target": {
            "type": "boolean",
        },
        "human_reference": {
            "type": [
                "string",
                "null",
            ],
        },
    },
}


_SELECTOR_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "selector_key",
        "selector_value",
    ],
    "properties": {
        "selector_key": {
            "type": "string",
        },
        "selector_value": {
            "type": "string",
        },
    },
}


_AGENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "action",
        "capability_name",
        "answer",
    ],
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "tool",
                "answer",
                "cannot_answer",
            ],
        },
        "capability_name": {
            "type": [
                "string",
                "null",
            ],
        },
        "answer": {
            "type": [
                "string",
                "null",
            ],
        },
    },
}


_TARGET_SYSTEM = """Identify only the endpoint resource reference in the human message.

Do not interpret the factual question yet.

Examples of endpoint references include a hostname, endpoint/device name, serial-like device reference, or other explicit machine identifier supplied by the human.

Do not infer a person merely because the question asks about a logged-in user.
Do not invent a target.

If one explicit endpoint target is present, return it exactly as the human supplied it.
Otherwise has_endpoint_target=false.

Return only the required structured object."""


_SELECTOR_SYSTEM = """Resolve one human-supplied endpoint reference.

Choose the best selector only from the offered selector keys.

The requested factual property is deliberately not provided because it must not influence resource identity.

A human-friendly hostname or endpoint name is not automatically a durable resource_id.

Use previous failed resolution attempts to choose another valid selector when necessary.

Return only the required structured object."""


_AGENT_SYSTEM = """You are Jason's working-first read-only endpoint operations agent.

The human's endpoint has already been independently resolved to exactly one provider-verified durable resource identity. You may not reinterpret or substitute the target.

You are given authorized read-only endpoint capabilities and governed provider evidence.

Reason naturally about which capability or capabilities can answer the human's question.

Rules:

1. Select only from offered authorized read capabilities.
2. Jason binds every read to the locked durable resource_id.
3. Inspect provider evidence directly, including nested structured fields.
4. Positive evidence may support an answer immediately.
5. Absence from one source is not proof that the fact is unavailable.
6. If evidence is insufficient and another untried capability could plausibly help, call it.
7. Do not invent operational facts.
8. Do not confuse semantic neighbors such as site versus manufacturer or device type versus system model.
9. Do not execute mutations, writes, commands, jobs, or administrative actions.
10. If all useful authorized evidence is exhausted, explain the limitation truthfully.

For another read:
action=tool
capability_name=<one offered untried capability>
answer=null

For a grounded answer:
action=answer
capability_name=null
answer=<human-facing grounded answer>

For genuinely unavailable evidence:
action=cannot_answer
capability_name=null
answer=<non-empty explanation>

Return only the required structured object."""


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _contains_exact(
    value: object,
    expected: str,
) -> bool:
    wanted = _clean(expected).casefold()

    if isinstance(value, Mapping):
        return any(
            _contains_exact(child, expected)
            for child in value.values()
        )

    if (
        isinstance(value, Sequence)
        and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        )
    ):
        return any(
            _contains_exact(child, expected)
            for child in value
        )

    return (
        value is not None
        and _clean(value).casefold() == wanted
    )


def _safe_evidence(
    value: object,
    *,
    max_chars: int = 60000,
) -> str:
    rendered = json.dumps(
        sanitize_evidence_tree(value),
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )

    if len(rendered) <= max_chars:
        return rendered

    return rendered[:max_chars] + "...[TRUNCATED]"


@dataclass(slots=True)
class PermissiveDrmmTeamsFlow:
    """Read-only endpoint agent baseline using existing governed execution."""

    identity_binder: Any
    request_factory: Any
    orchestrator: Any
    transport: Any
    catalog: Any
    reasoning: PermissiveReasoningClient
    fallback_flow: Any
    max_reads: int = 8

    def handle(
        self,
        request: TeamsConversationRequest,
    ) -> TeamsConversationExperienceResult:
        principal = self.identity_binder.bind(
            request.identity
        )

        if principal is None:
            raise PermissionError(
                "Teams identity is not bound to a Jason principal"
            )

        human_text = request.text.strip()

        target = self._extract_target(
            human_text
        )

        if target is None:
            return self.fallback_flow.handle(
                request
            )

        available = tuple(
            self.catalog.list_available()
        )

        device_search = next(
            (
                item
                for item in available
                if (
                    item.capability_name
                    == "endpoint.device.search"
                    and item.permission_mode
                    == "observe"
                )
            ),
            None,
        )

        if device_search is None:
            return self.fallback_flow.handle(
                request
            )

        correlation_id = (
            self.request_factory
            .new_correlation_id()
        )

        executor = (
            BoundTeamsConversationIntentExecutor(
                request_factory=(
                    self.request_factory
                ),
                orchestrator=(
                    self.orchestrator
                ),
                principal=principal,
                identity=request.identity,
                correlation_id=correlation_id,
            )
        )

        locked = self._resolve_and_lock(
            target=target,
            device_search=device_search,
            executor=executor,
        )

        if locked is None:
            response_text = (
                "I could not resolve that endpoint "
                "to exactly one governed resource."
            )
        else:
            response_text = self._answer(
                question=human_text,
                locked=locked,
                available=available,
                executor=executor,
            )

        if not response_text.strip():
            raise RuntimeError(
                "Permissive DRMM baseline produced empty response"
            )

        message_id = self.transport.send(
            conversation_id=(
                request.identity.conversation_id
            ),
            text=response_text.strip(),
            correlation_id=correlation_id,
        )

        if not str(message_id).strip():
            raise RuntimeError(
                "Teams transport did not return a message identifier"
            )

        return TeamsConversationExperienceResult(
            response_text=response_text.strip(),
            transport_message_id=str(
                message_id
            ).strip(),
            correlation_id=correlation_id,
            orchestrations=tuple(
                executor.results
            ),
        )

    def _extract_target(
        self,
        human_text: str,
    ) -> str | None:
        result = self._complete(
            system=_TARGET_SYSTEM,
            payload={
                "human_message": human_text,
            },
            schema=_TARGET_SCHEMA,
            max_output_tokens=160,
        )

        if not bool(
            result.get(
                "has_endpoint_target"
            )
        ):
            return None

        target = _clean(
            result.get(
                "human_reference"
            )
        )

        return target or None

    def _resolve_and_lock(
        self,
        *,
        target: str,
        device_search: Any,
        executor: BoundTeamsConversationIntentExecutor,
    ) -> _LockedResource | None:
        selector_keys = tuple(
            device_search.selector_keys
        )

        failures: list[
            Mapping[str, object]
        ] = []

        for _ in range(
            min(
                4,
                max(
                    1,
                    len(selector_keys),
                ),
            )
        ):
            proposal = self._complete(
                system=_SELECTOR_SYSTEM,
                payload={
                    "human_resource_reference": (
                        target
                    ),
                    "available_selector_keys": list(
                        selector_keys
                    ),
                    "failed_attempts": failures,
                },
                schema=_SELECTOR_SCHEMA,
                max_output_tokens=160,
            )

            selector_key = _clean(
                proposal.get(
                    "selector_key"
                )
            )

            selector_value = _clean(
                proposal.get(
                    "selector_value"
                )
            )

            if (
                selector_key
                not in selector_keys
                or not selector_value
            ):
                failures.append(
                    {
                        "selector_key": (
                            selector_key
                        ),
                        "selector_value": (
                            selector_value
                        ),
                        "reason": (
                            "invalid selector"
                        ),
                    }
                )
                continue

            result = executor.execute(
                ConversationIntent(
                    capability_name=(
                        device_search
                        .capability_name
                    ),
                    arguments={
                        selector_key: (
                            selector_value
                        ),
                        "requested_facts": [
                            (
                                "Resolve this "
                                "endpoint resource."
                            )
                        ],
                    },
                    permission_mode="observe",
                    risk=device_search.risk,
                )
            )

            data = (
                result.output.get(
                    "data"
                )
                if result.output
                else None
            )

            verified = (
                self._verified_resolution(
                    data=data,
                    human_target=target,
                )
            )

            if verified is not None:
                return verified

            failures.append(
                {
                    "selector_key": (
                        selector_key
                    ),
                    "selector_value": (
                        selector_value
                    ),
                    "reason": (
                        "result was not one "
                        "corroborated resource"
                    ),
                }
            )

        return None

    @staticmethod
    def _verified_resolution(
        *,
        data: object,
        human_target: str,
    ) -> _LockedResource | None:
        if not isinstance(
            data,
            Mapping,
        ):
            return None

        resource_id = _clean(
            data.get(
                "resolved_resource_id"
            )
        )

        matches = data.get(
            "resource_matches"
        )

        if (
            not resource_id
            or not isinstance(
                matches,
                Sequence,
            )
            or isinstance(
                matches,
                (
                    str,
                    bytes,
                    bytearray,
                ),
            )
            or len(matches) != 1
            or not isinstance(
                matches[0],
                Mapping,
            )
        ):
            return None

        match = matches[0]

        if (
            _clean(
                match.get(
                    "resource_id"
                )
            )
            != resource_id
        ):
            return None

        if not _contains_exact(
            match,
            human_target,
        ):
            return None

        return _LockedResource(
            resource_id=resource_id,
            human_reference=human_target,
            verified_match=match,
        )

    def _answer(
        self,
        *,
        question: str,
        locked: _LockedResource,
        available: Sequence[Any],
        executor: BoundTeamsConversationIntentExecutor,
    ) -> str:
        reads = {
            item.capability_name: item
            for item in available
            if (
                item.permission_mode
                == "observe"
                and item.operation
                in {
                    "read",
                    "search",
                }
                and "endpoint"
                in item.resource_types
                and "resource_id"
                in item.selector_keys
            )
        }

        attempted: list[str] = []
        evidence: list[
            Mapping[str, object]
        ] = []

        for _ in range(
            max(
                1,
                min(
                    self.max_reads + 2,
                    len(reads) + 2,
                ),
            )
        ):
            untried = [
                {
                    "capability_name": (
                        reads[name]
                        .capability_name
                    ),
                    "description": (
                        reads[name]
                        .description
                    ),
                }
                for name in reads
                if name not in attempted
            ]

            proposal = self._complete(
                system=_AGENT_SYSTEM,
                payload={
                    "human_question": (
                        question
                    ),
                    "locked_resource": {
                        "human_reference": (
                            locked
                            .human_reference
                        ),
                        "resource_id": (
                            locked.resource_id
                        ),
                        "verified_match": (
                            locked
                            .verified_match
                        ),
                    },
                    "attempted_capabilities": (
                        attempted
                    ),
                    "untried_capabilities": (
                        untried
                    ),
                    "governed_evidence": (
                        evidence
                    ),
                },
                schema=_AGENT_SCHEMA,
                max_output_tokens=1000,
            )

            action = _clean(
                proposal.get(
                    "action"
                )
            ).casefold()

            if action == "tool":
                name = _clean(
                    proposal.get(
                        "capability_name"
                    )
                )

                if (
                    name not in reads
                    or name in attempted
                ):
                    continue

                self._run_read(
                    question=question,
                    locked=locked,
                    name=name,
                    capability=reads[name],
                    executor=executor,
                    attempted=attempted,
                    evidence=evidence,
                )
                continue

            answer = _clean(
                proposal.get(
                    "answer"
                )
            )

            if (
                action == "answer"
                and answer
            ):
                return answer

            if (
                action
                == "cannot_answer"
                and untried
            ):
                # Working-first baseline:
                # uncertainty does not terminate while
                # additional governed evidence sources remain.
                next_name = (
                    untried[0]
                    ["capability_name"]
                )

                self._run_read(
                    question=question,
                    locked=locked,
                    name=next_name,
                    capability=reads[
                        next_name
                    ],
                    executor=executor,
                    attempted=attempted,
                    evidence=evidence,
                )
                continue

            if (
                action
                == "cannot_answer"
                and answer
            ):
                return answer

        final = self._complete(
            system=_AGENT_SYSTEM,
            payload={
                "human_question": (
                    question
                ),
                "locked_resource": {
                    "human_reference": (
                        locked.human_reference
                    ),
                    "resource_id": (
                        locked.resource_id
                    ),
                },
                "attempted_capabilities": (
                    attempted
                ),
                "untried_capabilities": [],
                "governed_evidence": (
                    evidence
                ),
                "instruction": (
                    "Give the best grounded answer "
                    "possible now. If evidence does "
                    "not establish the requested fact, "
                    "state that limitation."
                ),
            },
            schema=_AGENT_SCHEMA,
            max_output_tokens=1000,
        )

        answer = _clean(
            final.get(
                "answer"
            )
        )

        if answer:
            return answer

        return (
            "The available governed endpoint "
            "evidence does not establish the "
            "requested information."
        )

    @staticmethod
    def _run_read(
        *,
        question: str,
        locked: _LockedResource,
        name: str,
        capability: Any,
        executor: BoundTeamsConversationIntentExecutor,
        attempted: list[str],
        evidence: list[
            Mapping[str, object]
        ],
    ) -> None:
        result = executor.execute(
            ConversationIntent(
                capability_name=name,
                arguments={
                    "resource_id": (
                        locked.resource_id
                    ),
                    "requested_facts": [
                        question
                    ],
                },
                permission_mode="observe",
                risk=capability.risk,
            )
        )

        data = (
            result.output.get(
                "data"
            )
            if result.output
            else None
        )

        # Refuse a provider result that explicitly
        # changes the locked resource identity.
        if isinstance(
            data,
            Mapping,
        ):
            returned_id = _clean(
                data.get(
                    "resolved_resource_id"
                )
            )

            if (
                returned_id
                and returned_id
                != locked.resource_id
            ):
                raise PermissionError(
                    "provider evidence escaped the locked endpoint resource"
                )

        attempted.append(
            name
        )

        evidence.append(
            {
                "capability_name": (
                    result.capability_name
                ),
                "status": (
                    result.status.value
                ),
                "provider_id": (
                    result.provider_id
                ),
                "data": (
                    _safe_evidence(
                        data
                    )
                    if data
                    is not None
                    else None
                ),
            }
        )

    def _complete(
        self,
        *,
        system: str,
        payload: Mapping[str, object],
        schema: Mapping[str, object],
        max_output_tokens: int,
    ) -> Mapping[str, object]:
        last_error: Exception | None = None

        for _ in range(3):
            try:
                result = self.reasoning.complete(
                    system=system,
                    user=json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    schema=schema,
                    max_output_tokens=(
                        max_output_tokens
                    ),
                )

                if not isinstance(
                    result,
                    Mapping,
                ):
                    raise ValueError(
                        "structured reasoning result "
                        "was not an object"
                    )

                return result

            except Exception as exc:
                last_error = exc

        assert last_error is not None
        raise last_error
