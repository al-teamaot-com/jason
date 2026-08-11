from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry
from .teams_conversation_flow import BoundConversationPrincipal, ConversationIntent


class StructuredResourceInquiryReasoner(Protocol):
    """Interpret human language into provider-neutral resource facts only.

    Implementations may use JAC-001 Reasoning, but they are not given connector
    handles, provider credentials, execution authority, or a provider selection.
    """

    def propose(
        self,
        *,
        text: str,
        organization_id: str,
        client_id: str | None,
    ) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class ReasonedResourceInquiryInterpreter:
    reasoner: StructuredResourceInquiryReasoner

    _FORBIDDEN_TOP_LEVEL = frozenset(
        {
            "provider",
            "provider_id",
            "connector",
            "connector_id",
            "capability",
            "capability_name",
            "shell",
            "shell_command",
            "target_agent",
            "agent_endpoint",
            "invoke_agent",
        }
    )
    _FORBIDDEN_SELECTOR_KEYS = frozenset(
        {
            "provider",
            "provider_id",
            "connector",
            "connector_id",
            "capability",
            "capability_name",
            "shell_command",
            "target_agent",
        }
    )
    _IDENTIFIER_CHAR_CLASS = r"A-Za-z0-9._:/\\-"

    def interpret(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ResourceInquiry | None:
        proposed = self.reasoner.propose(
            text=text,
            organization_id=principal.organization_id,
            client_id=principal.client_id,
        )
        if proposed is None:
            return None
        if not isinstance(proposed, Mapping):
            raise ValueError("resource inquiry reasoner must return an object")

        forbidden = sorted(self._FORBIDDEN_TOP_LEVEL.intersection(proposed))
        if forbidden:
            raise PermissionError(
                "resource inquiry reasoner attempted provider/execution selection: "
                + ", ".join(forbidden)
            )

        resource_type = str(proposed.get("resource_type", "")).strip()
        selector = proposed.get("resource_selector")
        requested_facts = proposed.get("requested_facts")
        if not resource_type:
            raise ValueError("resource inquiry proposal is missing resource_type")
        if not isinstance(selector, Mapping) or not selector:
            raise ValueError("resource inquiry proposal requires a resource_selector object")
        if not isinstance(requested_facts, (list, tuple)) or not requested_facts:
            raise ValueError("resource inquiry proposal requires requested_facts")

        selector_forbidden = sorted(self._FORBIDDEN_SELECTOR_KEYS.intersection(selector))
        if selector_forbidden:
            raise PermissionError(
                "resource selector attempted provider/execution selection: "
                + ", ".join(selector_forbidden)
            )

        normalized_selector: dict[str, str] = {}
        for raw_key, raw_value in selector.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("resource selector keys must be non-empty")
            if not isinstance(raw_value, str):
                raise ValueError("resource selector values must be scalar strings")
            value = raw_value.strip()
            if not value:
                raise ValueError("resource selector values must be non-empty")
            if not self._selector_value_is_grounded(text=text, value=value):
                raise ValueError(
                    "resource selector values must be grounded in identifiers explicitly supplied by the human"
                )
            normalized_selector[key] = value

        return ResourceInquiry(
            resource_type=resource_type,
            resource_selector=normalized_selector,
            requested_facts=tuple(str(item).strip() for item in requested_facts),
            execution_mode=str(proposed.get("execution_mode", "deterministic")).strip(),
            permission_mode=str(proposed.get("permission_mode", "observe")).strip(),
        )

    @classmethod
    def _selector_value_is_grounded(cls, *, text: str, value: str) -> bool:
        """Require selector values to come from the human text, not authority context.

        Identifier punctuation such as hyphens is treated as part of the same token.
        Therefore an authority value like ``AOT`` does not count as grounded merely
        because the human supplied a hostname such as ``AOT-50282``.
        """

        boundary = cls._IDENTIFIER_CHAR_CLASS
        pattern = rf"(?<![{boundary}]){re.escape(value)}(?![{boundary}])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None


class ResourceInquiryInterpreter(Protocol):
    def interpret(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ResourceInquiry | None: ...


@dataclass(frozen=True, slots=True)
class GovernedResourceConversationIntentResolver:
    """Turn a human resource question into a validated provider-neutral capability.

    Language interpretation describes *what information is needed*. The resource
    planner determines *which registered broad capability can retrieve it*. Neither
    stage chooses or invokes a provider. The Central Orchestrator remains responsible
    for policy evaluation and provider resolution.
    """

    interpreter: ResourceInquiryInterpreter
    planner: GovernedResourceInquiryPlanner

    def resolve(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ConversationIntent | None:
        inquiry = self.interpreter.interpret(text=text, principal=principal)
        if inquiry is None:
            return None

        plan = self.planner.plan(inquiry)
        if len(plan.steps) != 1:
            # TeamsConversationFlow currently executes one governed capability per
            # turn. Never discard or silently flatten a multi-step governed plan.
            raise LookupError(
                "resource inquiry requires multi-step orchestration that is not yet enabled"
            )

        step = plan.steps[0]
        return ConversationIntent(
            capability_name=step.capability_name,
            arguments=dict(step.arguments),
            execution_mode=inquiry.execution_mode,
            permission_mode=inquiry.permission_mode,
            risk="low",
        )
