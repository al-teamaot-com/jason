from __future__ import annotations

from dataclasses import dataclass

from .conversation_resource_intent import MetadataFirstResourceInquiryInterpreter
from .semantic_fact_reasoning import SemanticFactReasoner
from .semantic_fact_resolver import SemanticFactResolver
from .semantic_request_bridge import SemanticRequestBridge
from .teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationClarificationRequiredError,
)
from .resource_inquiry import ResourceInquiry


@dataclass(frozen=True, slots=True)
class GroundedSemanticResourceInquiryInterpreter(
    MetadataFirstResourceInquiryInterpreter
):
    """Add dynamic semantic fact inference without surrendering target grounding.

    Literal/qualified requests continue through the deterministic metadata-first path.
    When the human names a structurally grounded endpoint but expresses the desired
    information in free-form language, only the requested fact meaning is delegated to
    semantic reasoning. The grounded selector is never model output and therefore
    cannot be replaced by a word from the question.
    """

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

        if self.semantic_fact_reasoner is None or self.fact_vocabulary is None:
            return self.fallback.interpret(text=text, principal=principal)

        endpoint_identifier = self._extract_endpoint_identifier(text)
        if endpoint_identifier is None:
            return self.fallback.interpret(text=text, principal=principal)

        selector = {"hostname": endpoint_identifier.upper()}
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
            # A grounded endpoint must not be reinterpreted as some other selector merely
            # because semantic fact classification was uncertain. Ask for meaning instead.
            raise ConversationClarificationRequiredError(
                reason_code="grounded_resource_fact_meaning_unresolved",
                candidate_facts=eligible_facts,
            )

        allowed = set(eligible_facts)
        outside = tuple(fact for fact in requested_facts if fact not in allowed)
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
        return bridge.lower(request, selector=selector)
