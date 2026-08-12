from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .canonical_fact_vocabulary import CanonicalFactVocabulary
from .semantic_fact_resolver import SemanticFactResolver
from .resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry
from .semantic_request_bridge import SemanticRequestBridge
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
    fact_vocabulary: CanonicalFactVocabulary | None = None
    fact_resolver: SemanticFactResolver | None = None

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
        if not isinstance(selector, Mapping):
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

        result_intent = str(
            proposed.get("result_intent", "summary")
        ).strip()
        completeness_requirement = str(
            proposed.get("completeness_requirement", "sufficient")
        ).strip()

        if result_intent not in {
            "summary",
            "enumerate",
            "count",
            "search",
            "inspect",
        }:
            raise ValueError("resource inquiry proposal has invalid result_intent")

        if completeness_requirement not in {
            "sufficient",
            "complete",
        }:
            raise ValueError(
                "resource inquiry proposal has invalid completeness_requirement"
            )

        normalized_facts = tuple(str(item).strip() for item in requested_facts)
        bridge = SemanticRequestBridge(
            fact_vocabulary=self.fact_vocabulary,
            fact_resolver=self.fact_resolver,
        )
        semantic_request = bridge.build(
            human_text=text,
            resource_type=resource_type,
            resource_selector=normalized_selector,
            requested_facts=normalized_facts,
            result_intent=result_intent,
            completeness_requirement=completeness_requirement,
            permission_mode=str(proposed.get("permission_mode", "observe")).strip(),
        )
        return bridge.lower(semantic_request, selector=normalized_selector)

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



@dataclass(frozen=True, slots=True)
class MetadataFirstResourceInquiryInterpreter:
    """Resolve obvious read-only resource inquiries without requiring AI.

    This layer is deliberately conservative. It only resolves a request when one
    governed metadata contract produces a unique direct semantic match. Anything
    ambiguous or requiring linguistic inference falls through to the existing
    bounded reasoned interpreter.

    Provider names in free-form text remain source context only and never become
    authority, provider selection, tenant scope, or a resource selector.
    """

    contracts: tuple[Mapping[str, Any], ...]
    fallback: "ResourceInquiryInterpreter"

    def interpret(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ResourceInquiry | None:
        deterministic = self._interpret_deterministically(text)
        if deterministic is not None:
            return deterministic

        return self.fallback.interpret(
            text=text,
            principal=principal,
        )

    def _interpret_deterministically(
        self,
        text: str,
    ) -> ResourceInquiry | None:
        normalized_text = self._normalize(text)
        if not normalized_text:
            return None

        matches: list[tuple[Mapping[str, Any], str]] = []

        for contract in self.contracts:
            fact_hints = tuple(
                str(item).strip()
                for item in contract.get("fact_hints", ())
                if str(item).strip()
            )

            matched_fact = self._best_explicit_fact_match(
                normalized_text,
                fact_hints,
            )
            if matched_fact is None:
                continue

            # Deterministic foundation currently handles only requests that do
            # not require us to infer a resource selector. Endpoint/device and
            # other named-resource requests continue through the reasoner until
            # selector extraction is generalized safely.
            selector_required = bool(contract.get("selector_required"))
            if selector_required:
                continue

            matches.append((contract, matched_fact))

        if len(matches) != 1:
            return None

        contract, requested_fact = matches[0]

        resource_types = tuple(
            str(item).strip()
            for item in contract.get("resource_types", ())
            if str(item).strip()
        )

        if len(resource_types) != 1:
            return None

        result_intent, completeness_requirement = (
            self._result_outcome(normalized_text)
        )

        # Fact hints are recognition aliases, not evidence contracts. When the
        # human requests an exhaustive collection outcome, normalize any matched
        # singular/plural/synonym hint to the capability's canonical collection
        # fact. This keeps varied language from collapsing a collection into one
        # arbitrary nested scalar.
        collection_fact = str(contract.get("collection_fact", "")).strip()
        if (
            collection_fact
            and result_intent in {"enumerate", "count"}
            and completeness_requirement == "complete"
        ):
            requested_fact = collection_fact

        return ResourceInquiry(
            resource_type=resource_types[0],
            resource_selector={},
            requested_facts=(requested_fact,),
            execution_mode="deterministic",
            permission_mode="observe",
            result_intent=result_intent,
            completeness_requirement=completeness_requirement,
        )

    @classmethod
    def _best_explicit_fact_match(
        cls,
        normalized_text: str,
        fact_hints: tuple[str, ...],
    ) -> str | None:
        candidates: list[tuple[int, str]] = []

        for hint in fact_hints:
            normalized_hint = cls._normalize(hint)
            if not normalized_hint:
                continue

            pattern = (
                r"(?<![a-z0-9])"
                + re.escape(normalized_hint)
                + r"(?![a-z0-9])"
            )

            if re.search(pattern, normalized_text):
                candidates.append((len(normalized_hint), hint))

        if not candidates:
            return None

        # Prefer the most specific explicit phrase: "open alerts" beats
        # "alerts", "managed sites" beats "sites", etc.
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates[0][1]

    @staticmethod
    def _result_outcome(normalized_text: str) -> tuple[str, str]:
        """Resolve only explicit generic result-shaping language.

        This does not recognize provider-specific questions. It identifies
        universal output operators such as count and complete enumeration.
        Ordinary/vague questions remain summary/sufficient and may still use
        semantic reasoning elsewhere when resource interpretation requires it.
        """

        words = set(normalized_text.split())

        count_phrases = (
            "how many",
            "number of",
            "count of",
        )
        if (
            "count" in words
            or any(phrase in normalized_text for phrase in count_phrases)
        ):
            return "count", "complete"

        enumeration_verbs = {
            "list",
            "enumerate",
        }
        explicit_all = (
            "all" in words
            or "every" in words
            or "complete list" in normalized_text
            or "full list" in normalized_text
        )

        if words.intersection(enumeration_verbs):
            return "enumerate", "complete"

        if explicit_all and (
            "show" in words
            or "give" in words
            or "display" in words
            or "return" in words
        ):
            return "enumerate", "complete"

        return "summary", "sufficient"

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(
            re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
        )


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
