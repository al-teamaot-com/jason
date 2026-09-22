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
from dataclasses import dataclass, field
import json
from typing import Any, Protocol

from .evidence_sanitization import sanitize_evidence_tree
from .teams_conversation_experience import (
    BoundTeamsConversationIntentExecutor,
    TeamsConversationExperienceResult,
)
from .teams_conversation_flow import (
    ConversationGuidanceRequiredError,
    ConversationIntent,
    TeamsConversationRequest,
)
from usage_ledger.contracts import UsageContext
from usage_ledger.runtime_context import bind_usage_context


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


@dataclass(frozen=True, slots=True)
class _ConversationSubject:
    kind: str
    reference: str


@dataclass(frozen=True, slots=True)
class _PendingClarification:
    original_request: str
    clarification_question: str
    semantic_frame: Mapping[str, object] | None = None


_SUBJECT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "subject_kind",
        "subject_reference",
    ],
    "properties": {
        "subject_kind": {
            "type": "string",
            "enum": [
                "endpoint",
                "user",
                "none",
            ],
        },
        "subject_reference": {
            "type": [
                "string",
                "null",
            ],
        },
    },
}


_SUBJECT_SYSTEM = """Identify the explicit operational subject in the human message.

Interpret meaning, not wording.

subject_kind=endpoint:
The human explicitly identifies one managed endpoint/device/machine as the subject.

subject_kind=user:
The human explicitly identifies a human/account/user identity as the subject.

subject_kind=none:
No new explicit endpoint or user subject is introduced in this message.

Preserve the human-supplied identifying reference exactly enough to use as a governed discovery selector.

Do not decide what provider capability to execute.
Do not infer a new subject merely from pronouns or follow-up wording.
Return only the required structured object."""


_CLARIFICATION_FRAME_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status",
        "resolved_request",
        "clarification_question",
        "frame",
    ],
    "properties": {
        "status": {
            "type": "string",
            "enum": [
                "ready",
                "clarify",
                "new_request",
            ],
        },
        "resolved_request": {
            "type": [
                "string",
                "null",
            ],
        },
        "clarification_question": {
            "type": [
                "string",
                "null",
            ],
        },
        "frame": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "resource_kind",
                "information_need",
                "result_shape",
                "temporal_scope",
                "constraints",
                "unresolved_dimensions",
            ],
            "properties": {
                "resource_kind": {
                    "type": "string",
                },
                "information_need": {
                    "type": "string",
                },
                "result_shape": {
                    "type": "string",
                },
                "temporal_scope": {
                    "type": "string",
                },
                "constraints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "dimension",
                            "value",
                        ],
                        "properties": {
                            "dimension": {
                                "type": "string",
                            },
                            "value": {
                                "type": "string",
                            },
                        },
                    },
                },
                "unresolved_dimensions": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
            },
        },
    },
}


_CLARIFICATION_FRAME_SYSTEM = """Continue one pending conversational request by meaning, not wording.

You receive:
- the original human request,
- the material clarification Jason asked,
- any previously accumulated provider-independent semantic frame,
- the human's current reply.

The prior clarification question identifies the human semantic dimension that was materially unresolved.

Interpret the current reply against that pending request. Do not treat the reply as an isolated new request unless it clearly abandons or replaces the pending request.

Never use or imply phrase tables, keyword mappings, synonym tables, question templates, provider mappings, capability mappings, fact mappings, or field mappings.

Build a provider-independent semantic frame containing:
- resource_kind: what kind of thing the request concerns;
- information_need: what the human ultimately wants established;
- result_shape: the requested form such as a count, set, status, value, summary, or another semantic result;
- temporal_scope: the relevant time meaning;
- constraints: semantic dimensions and values actually supplied or resolved by the human;
- unresolved_dimensions: only remaining dimensions for which a human choice would materially change the target, requested meaning, authority, action, or risk.

Constraint dimension names describe human meaning. They are never provider fields, evidence-source names, capability names, API choices, data collections, record types, or implementation mechanisms.

IMPORTANT CLARIFICATION POLICY:

Once the human has answered the material choice Jason actually asked about, do not invent a new clarification merely because several backend evidence sources, capabilities, provider records, data collections, or retrieval strategies might answer the request.

Choosing where or how Jason obtains governed evidence is Jason's responsibility.

Uncertainty about:
- which provider evidence source to inspect,
- which capability to use,
- which record or collection contains the fact,
- which API or backend method should answer,
- whether one source is better than another,
does not constitute unresolved human meaning.

Do not ask the human to choose between internal evidence sources or retrieval methods.

status=ready:
Use this when the human reply resolves the prior material clarification and no other genuine human semantic choice remains.
resolved_request must be a concise standalone restatement combining the original request with the newly supplied meaning.
Preserve literal identifiers exactly.
Do not broaden, narrow, or add requirements beyond the conversation.

status=clarify:
Use this only when a human choice still materially changes target, meaning, authority, action, or risk.
clarification_question must ask only that remaining human semantic question.
Never use clarify for internal evidence-source or implementation choices.

status=new_request:
Use this only when the human clearly abandoned the pending request and started another request.

Return only the required structured object."""


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


_TEMPORAL_SCOPE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scope"],
    "properties": {
        "scope": {
            "type": "string",
            "enum": [
                "current",
                "historical",
                "mixed",
            ],
        },
    },
}


_TEMPORAL_SCOPE_SYSTEM = """Classify only the temporal scope of the human's operational question.

current:
The human asks about present/current state, configuration, inventory, health, value, or status.

historical:
The human explicitly asks about past events, prior states, history, resolved events, previous occurrences, or what has happened.

mixed:
The human asks for both current state and historical/past information.

Do not interpret provider fields or choose tools.
Return only the required structured object."""


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


_RELATIONSHIP_SET_SYSTEM = """You are answering a governed read-only relationship query.

The conversational subject and provider evidence are supplied separately from the human wording.

Use only the supplied provider evidence.

The endpoint.device.search user_identity relationship is provider-reported endpoint/user association evidence. It can establish which managed endpoints match the provider's reported user identity evidence.

It does not by itself prove a historical interactive sign-in timeline. If the human asks for historical activity and the evidence only establishes current/last-user association, retain the subject and explain that evidence limitation instead of inventing history or asking the human to repeat the subject.

Preserve ambiguity when multiple resources match.
Do not invent operational facts.
Return a concise human-facing answer grounded in the supplied evidence.

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
5. The broad endpoint read is baseline context, not proof that specialized inventories are complete.
6. Prefer direct current resource or inventory evidence over alerts when answering current-state questions.
7. Historical or resolved-alert evidence describes past events. It must not override a current direct measurement or current endpoint state.
8. Do not use a history capability for a current-state question unless current resource/inventory sources are exhausted and history is genuinely necessary for context.
9. Absence from one source is not proof that the fact is unavailable.
10. If a specialized untried capability could materially improve or verify the requested answer, call it before answering.
11. Do not invent operational facts.
12. Do not confuse semantic neighbors such as site versus manufacturer or device type versus system model.
13. Do not execute mutations, writes, commands, jobs, or administrative actions.
14. If all useful authorized evidence is exhausted, explain the limitation truthfully.

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
    _conversation_targets: dict[
        tuple[str, str, str],
        _LockedResource,
    ] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    _conversation_subjects: dict[
        tuple[str, str, str],
        _ConversationSubject,
    ] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    _pending_clarifications: dict[
        tuple[str, str, str],
        _PendingClarification,
    ] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

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

        usage_context = UsageContext(
            workflow_id=request.identity.conversation_id,
            request_id=request.identity.message_id,
            attempt_id="turn-scope",
            organization_id=principal.organization_id,
            client_id=principal.client_id,
            capability="conversation.reason",
            routing_profile="teams-permissive-drmm",
            metadata={
                "principal_id": principal.principal_id,
                "teams_conversation_id": (
                    request.identity.conversation_id
                ),
                "teams_message_id": (
                    request.identity.message_id
                ),
            },
        )

        with bind_usage_context(
            usage_context
        ):
            return self._handle_with_bound_usage(
                request
            )

    def _handle_with_bound_usage(
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

        conversation_key = (
            principal.organization_id,
            principal.principal_id,
            request.identity.conversation_id,
        )

        pending = self._pending_clarifications.get(
            conversation_key
        )

        if pending is not None:
            continuation = (
                self._resume_pending_clarification(
                    pending=pending,
                    human_reply=human_text,
                )
            )

            status = _clean(
                continuation.get(
                    "status"
                )
            ).casefold()

            resolved_request = _clean(
                continuation.get(
                    "resolved_request"
                )
            )

            clarification_question = _clean(
                continuation.get(
                    "clarification_question"
                )
            )

            semantic_frame = continuation.get(
                "frame"
            )

            if not isinstance(
                semantic_frame,
                Mapping,
            ):
                semantic_frame = None

            if status == "new_request":
                self._pending_clarifications.pop(
                    conversation_key,
                    None,
                )

            elif status == "clarify":
                if not clarification_question:
                    raise RuntimeError(
                        "clarification continuation omitted "
                        "the remaining material question"
                    )

                self._pending_clarifications[
                    conversation_key
                ] = _PendingClarification(
                    original_request=(
                        resolved_request
                        or pending.original_request
                    ),
                    clarification_question=(
                        clarification_question
                    ),
                    semantic_frame=semantic_frame,
                )

                raise ConversationGuidanceRequiredError(
                    reason_code=(
                        "permissive_semantic_frame_incomplete"
                    ),
                    guidance_text=(
                        clarification_question
                    ),
                )

            elif status == "ready":
                if not resolved_request:
                    raise RuntimeError(
                        "ready clarification continuation "
                        "omitted the resolved request"
                    )

                self._pending_clarifications.pop(
                    conversation_key,
                    None,
                )

                resumed_request = (
                    TeamsConversationRequest(
                        text=resolved_request,
                        identity=request.identity,
                    )
                )

                return self._handle_with_bound_usage(
                    resumed_request
                )

            else:
                raise RuntimeError(
                    "clarification continuation returned "
                    "an invalid status"
                )

        explicit_subject = self._extract_subject(
            human_text
        )

        prior_subject = self._conversation_subjects.get(
            conversation_key
        )

        subject = (
            explicit_subject
            if explicit_subject is not None
            else prior_subject
        )

        target = self._extract_target(
            human_text
        )

        prior_locked = self._conversation_targets.get(
            conversation_key
        )

        if (
            subject is None
            and target is None
            and prior_locked is None
        ):
            return self._fallback_with_pending(
                request=request,
                conversation_key=conversation_key,
                human_text=human_text,
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
            return self._fallback_with_pending(
                request=request,
                conversation_key=conversation_key,
                human_text=human_text,
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

        if (
            subject is not None
            and subject.kind == "user"
        ):
            self._conversation_subjects[
                conversation_key
            ] = subject

            response_text = self._answer_user_relationship(
                question=human_text,
                subject=subject,
                device_search=device_search,
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

        if target is None:
            locked = prior_locked
        else:
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
            self._conversation_targets[
                conversation_key
            ] = locked

            self._conversation_subjects[
                conversation_key
            ] = _ConversationSubject(
                kind="endpoint",
                reference=locked.human_reference,
            )

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

    def _resume_pending_clarification(
        self,
        *,
        pending: _PendingClarification,
        human_reply: str,
    ) -> Mapping[str, object]:
        result = self._complete(
            system=_CLARIFICATION_FRAME_SYSTEM,
            payload={
                "original_request": (
                    pending.original_request
                ),
                "clarification_question": (
                    pending.clarification_question
                ),
                "prior_semantic_frame": (
                    dict(
                        pending.semantic_frame
                    )
                    if pending.semantic_frame
                    is not None
                    else None
                ),
                "human_reply": human_reply,
            },
            schema=_CLARIFICATION_FRAME_SCHEMA,
            max_output_tokens=500,
        )

        if not isinstance(
            result,
            Mapping,
        ):
            raise RuntimeError(
                "clarification continuation did not "
                "return a structured frame"
            )

        return result

    def _fallback_with_pending(
        self,
        *,
        request: TeamsConversationRequest,
        conversation_key: tuple[
            str,
            str,
            str,
        ],
        human_text: str,
    ):
        try:
            return self.fallback_flow.handle(
                request
            )
        except ConversationGuidanceRequiredError as error:
            self._pending_clarifications[
                conversation_key
            ] = _PendingClarification(
                original_request=human_text,
                clarification_question=(
                    error.guidance_text
                ),
            )
            raise

    def _extract_subject(
        self,
        human_text: str,
    ) -> _ConversationSubject | None:
        result = self._complete(
            system=_SUBJECT_SYSTEM,
            payload={
                "human_message": human_text,
            },
            schema=_SUBJECT_SCHEMA,
            max_output_tokens=160,
        )

        kind = _clean(
            result.get(
                "subject_kind"
            )
        ).casefold()

        reference = _clean(
            result.get(
                "subject_reference"
            )
        )

        if (
            kind not in {
                "endpoint",
                "user",
            }
            or not reference
        ):
            return None

        return _ConversationSubject(
            kind=kind,
            reference=reference,
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

    def _answer_user_relationship(
        self,
        *,
        question: str,
        subject: _ConversationSubject,
        device_search: Any,
        executor: BoundTeamsConversationIntentExecutor,
    ) -> str:
        if "user_identity" not in tuple(
            device_search.selector_keys
        ):
            return (
                "The authorized endpoint search capability "
                "does not expose a user-identity relationship selector."
            )

        result = executor.execute(
            ConversationIntent(
                capability_name=(
                    device_search.capability_name
                ),
                arguments={
                    "user_identity": (
                        subject.reference
                    ),
                    "requested_facts": [
                        question
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

        if not isinstance(
            data,
            Mapping,
        ):
            return (
                "The governed endpoint search did not return "
                "usable relationship evidence."
            )

        scope = self._temporal_scope(
            question
        )

        proposal = self._complete(
            system=_RELATIONSHIP_SET_SYSTEM,
            payload={
                "human_question": question,
                "temporal_scope": scope,
                "subject": {
                    "kind": subject.kind,
                    "reference": (
                        subject.reference
                    ),
                },
                "capability": {
                    "name": (
                        device_search.capability_name
                    ),
                    "selector": "user_identity",
                },
                "governed_evidence": {
                    "resource_matches": (
                        data.get(
                            "resource_matches"
                        )
                    ),
                    "resolved_resource_id": (
                        data.get(
                            "resolved_resource_id"
                        )
                    ),
                    "discovery_complete": (
                        data.get(
                            "discovery_complete"
                        )
                    ),
                    "provider_data": (
                        _safe_evidence(
                            data.get(
                                "provider_data"
                            )
                        )
                        if data.get(
                            "provider_data"
                        )
                        is not None
                        else None
                    ),
                },
            },
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["answer"],
                "properties": {
                    "answer": {
                        "type": "string",
                    },
                },
            },
            max_output_tokens=900,
        )

        answer = _clean(
            proposal.get(
                "answer"
            )
        )

        if answer:
            return answer

        return (
            "The governed endpoint relationship search "
            "did not establish an answer."
        )

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
        temporal_scope = self._temporal_scope(
            question
        )

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

        # Start every resolved endpoint question with the provider's broad
        # endpoint read when available. This supplies the model with current
        # endpoint state before it reasons about whether specialized audit,
        # software, or alert evidence is also needed.
        #
        # This is capability-level behavior, not fact routing: no requested
        # property is mapped to a provider field or specialized capability.
        baseline = reads.get("endpoint.device.read")

        if baseline is not None:
            self._run_read(
                question=question,
                locked=locked,
                name="endpoint.device.read",
                capability=baseline,
                executor=executor,
                attempted=attempted,
                evidence=evidence,
            )

        for _ in range(
            max(
                1,
                min(
                    self.max_reads + 2,
                    len(reads) + 2,
                ),
            )
        ):
            remaining_names = [
                name
                for name in reads
                if name not in attempted
            ]

            # Historical event evidence is a fallback evidence tier.
            #
            # Do not offer historical reads while current resource,
            # inventory, software, or current-alert reads remain
            # available. This prevents stale/past observations from
            # displacing current operational evidence without mapping
            # any requested fact to a provider field or capability.
            non_historical = [
                name
                for name in remaining_names
                if name
                != "endpoint.alert.history.search"
            ]

            if temporal_scope == "historical":
                offered_names = remaining_names
            elif temporal_scope == "mixed":
                offered_names = remaining_names
            else:
                offered_names = (
                    non_historical
                    if non_historical
                    else remaining_names
                )

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
                for name in offered_names
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
                    or name not in offered_names
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

        if name == "endpoint.alert.history.search":
            evidence_class = "historical_event_evidence"
        elif name == "endpoint.alert.search":
            evidence_class = "current_alert_evidence"
        elif name == "endpoint.audit.read":
            evidence_class = "current_inventory_evidence"
        elif name == "endpoint.software.search":
            evidence_class = "current_inventory_evidence"
        else:
            evidence_class = "current_resource_evidence"

        evidence.append(
            {
                "capability_name": (
                    result.capability_name
                ),
                "evidence_class": (
                    evidence_class
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

    def _temporal_scope(
        self,
        question: str,
    ) -> str:
        result = self._complete(
            system=_TEMPORAL_SCOPE_SYSTEM,
            payload={
                "human_question": question,
            },
            schema=_TEMPORAL_SCOPE_SCHEMA,
            max_output_tokens=80,
        )

        scope = _clean(
            result.get("scope")
        ).casefold()

        if scope not in {
            "current",
            "historical",
            "mixed",
        }:
            return "current"

        return scope

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
