from __future__ import annotations

from dataclasses import dataclass

from .conversation_resource_intent import (
    MetadataFirstResourceInquiryInterpreter,
)
from .resource_inquiry import ResourceInquiry
from .semantic_fact_reasoning import SemanticFactReasoner
from .semantic_fact_resolver import SemanticFactResolver
from .semantic_intent_translation import SemanticIntentTranslator
from .semantic_request_bridge import SemanticRequestBridge
from .teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationClarificationRequiredError,
)


@dataclass(frozen=True, slots=True)
class GroundedSemanticResourceInquiryInterpreter(
    MetadataFirstResourceInquiryInterpreter
):
    """Interpret read meaning while keeping grounding and topology inside Jason.

    Resolution order:

    1. deterministic metadata-first interpretation;
    2. hosted concept-only semantic interpretation;
    3. legacy local semantic fact interpretation for grounded endpoints;
    4. existing full inquiry fallback.

    Hosted semantic interpretation may select canonical facts only. It cannot
    select resource types, selectors, providers, capabilities, authority,
    credentials, execution modes, tools, or agents.
    """

    semantic_intent_translator: SemanticIntentTranslator | None = None
    semantic_fact_reasoner: SemanticFactReasoner | None = None
    fact_resolver: SemanticFactResolver | None = None

    def interpret(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ResourceInquiry | None:
        deterministic = self._interpret_deterministically(text)
        if deterministic is not None:
            return deterministic

        endpoint_identifier = self._extract_endpoint_identifier(text)

        selector: dict[str, str] = {}
        if endpoint_identifier is not None:
            selector = {
                "hostname": endpoint_identifier.upper(),
            }

        hosted = self._interpret_with_hosted_semantics(
            text=text,
            selector=selector,
        )
        if hosted is not None:
            return hosted

        # Rollback path for the current local endpoint fact reasoner.
        if (
            endpoint_identifier is not None
            and self.semantic_fact_reasoner is not None
            and self.fact_vocabulary is not None
        ):
            return self._interpret_with_local_fact_reasoner(
                text=text,
                selector=selector,
            )

        return self.fallback.interpret(
            text=text,
            principal=principal,
        )

    def _interpret_with_hosted_semantics(
        self,
        *,
        text: str,
        selector: dict[str, str],
    ) -> ResourceInquiry | None:
        if (
            self.semantic_intent_translator is None
            or self.fact_vocabulary is None
        ):
            return None

        if selector:
            eligible_facts = self._eligible_canonical_facts(
                resource_type="endpoint",
            )
        else:
            eligible_facts = self._eligible_unscoped_canonical_facts()

        if not eligible_facts:
            return None

        translation = self.semantic_intent_translator.translate(
            text=text,
            eligible_concepts=eligible_facts,
            grounded_selector=selector or None,
        )

        if translation is None:
            return None

        requested_facts = tuple(
            translation.requested_concepts
        )

        if len(requested_facts) > self._MAX_BOUNDED_FACT_EXPANSION:
            raise ConversationClarificationRequiredError(
                reason_code="semantic_fact_set_exceeds_safe_bound",
                candidate_facts=requested_facts,
            )

        allowed = set(eligible_facts)
        outside = tuple(
            fact
            for fact in requested_facts
            if fact not in allowed
        )
        if outside:
            raise PermissionError(
                "semantic translator selected facts outside governed candidates: "
                + ", ".join(outside)
            )

        if selector:
            resource_type = "endpoint"
        else:
            resource_type = self._resource_type_for_unscoped_facts(
                requested_facts
            )
            if resource_type is None:
                return None

        result_intent, completeness_requirement = self._result_outcome(
            self._normalize(text)
        )

        bridge = SemanticRequestBridge(
            fact_vocabulary=self.fact_vocabulary,
            fact_resolver=self.fact_resolver,
        )

        request = bridge.build(
            human_text=text,
            resource_type=resource_type,
            resource_selector=selector,
            requested_facts=requested_facts,
            result_intent=result_intent,
            completeness_requirement=completeness_requirement,
            permission_mode="observe",
        )

        return bridge.lower(
            request,
            selector=selector,
        )

    def _interpret_with_local_fact_reasoner(
        self,
        *,
        text: str,
        selector: dict[str, str],
    ) -> ResourceInquiry:
        assert self.semantic_fact_reasoner is not None
        assert self.fact_vocabulary is not None

        eligible_facts = self._eligible_canonical_facts(
            resource_type="endpoint",
        )

        requested_facts = self.semantic_fact_reasoner.infer(
            text=text,
            resource_type="endpoint",
            resource_selector=selector,
            eligible_facts=eligible_facts,
        )

        if not requested_facts:
            raise ConversationClarificationRequiredError(
                reason_code="grounded_resource_fact_meaning_unresolved",
                candidate_facts=eligible_facts,
            )

        allowed = set(eligible_facts)
        outside = tuple(
            fact
            for fact in requested_facts
            if fact not in allowed
        )
        if outside:
            raise PermissionError(
                "semantic fact reasoner selected facts outside governed endpoint facts: "
                + ", ".join(outside)
            )

        if len(requested_facts) > self._MAX_BOUNDED_FACT_EXPANSION:
            raise ConversationClarificationRequiredError(
                reason_code="semantic_fact_set_exceeds_safe_bound",
                candidate_facts=requested_facts,
            )

        result_intent, completeness_requirement = self._result_outcome(
            self._normalize(text)
        )

        bridge = SemanticRequestBridge(
            fact_vocabulary=self.fact_vocabulary,
            fact_resolver=self.fact_resolver,
        )

        request = bridge.build(
            human_text=text,
            resource_type="endpoint",
            resource_selector=selector,
            requested_facts=tuple(requested_facts),
            result_intent=result_intent,
            completeness_requirement=completeness_requirement,
            permission_mode="observe",
        )

        return bridge.lower(
            request,
            selector=selector,
        )

    def _eligible_unscoped_canonical_facts(
        self,
    ) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()

        for contract in self.contracts:
            if bool(contract.get("selector_required")):
                continue

            for raw_fact in contract.get(
                "canonical_facts",
                (),
            ):
                definition = self.fact_vocabulary.resolve(
                    str(raw_fact)
                )

                if definition is None:
                    continue

                canonical = definition.canonical_fact

                if canonical in seen:
                    continue

                seen.add(canonical)
                result.append(canonical)

        return tuple(result)

    def _resource_type_for_unscoped_facts(
        self,
        requested_facts: tuple[str, ...],
    ) -> str | None:
        requested = set(requested_facts)
        candidates: set[str] = set()

        for contract in self.contracts:
            if bool(contract.get("selector_required")):
                continue

            governed = {
                str(item).strip()
                for item in contract.get(
                    "canonical_facts",
                    (),
                )
                if str(item).strip()
            }

            if not requested.issubset(governed):
                continue

            resource_types = tuple(
                str(item).strip()
                for item in contract.get(
                    "resource_types",
                    (),
                )
                if str(item).strip()
            )

            if len(resource_types) == 1:
                candidates.add(resource_types[0])

        if len(candidates) != 1:
            return None

        return next(iter(candidates))
