"""Execute one generic investigation observation through Jason governance.

This module bridges:
    InvestigationDecision
        -> opaque broker operation_ref
        -> safe grounded selector
        -> canonical ConversationIntent
        -> existing governed executor
        -> immutable investigation evidence

It does not invoke connectors directly, select providers, interpret provider
fields, or grant authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Protocol

from .dynamic_conversation_intent import (
    DynamicIntentBindingError,
    GroundedConversationIntentBuilder,
)
from .dynamic_conversation_kernel import (
    DynamicCapabilityRequirement,
    DynamicConversationContext,
    DynamicConversationPlan,
    OfferedConversationCapability,
)
from .conversation_resource_observation import (
    VerifiedConversationResourceObservation,
    observe_verified_resource_identity,
)
from .integration_broker import (
    IntegrationBroker,
    resolve_operation_ref,
)
from .investigation_decision import (
    InvestigationDecision,
    InvestigationDecisionKind,
)
from .investigation_redaction import (
    bounded_model_evidence,
)
from .teams_conversation_flow import ConversationIntent


class InvestigationExecutionError(RuntimeError):
    pass


class GovernedConversationIntentExecutor(Protocol):
    def execute(self, intent: ConversationIntent):
        ...


@dataclass(frozen=True, slots=True)
class InvestigationEvidence:
    operation_ref: str
    resource_type: str
    information_goal: str
    execution_id: str
    correlation_id: str
    provider_id: str
    capability_name: str
    data: Mapping[str, Any]
    evidence_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    verified_resource: (
        VerifiedConversationResourceObservation | None
    ) = None

    def model_view(self) -> Mapping[str, Any]:
        """Evidence view for reasoning.

        Provider/capability routing identifiers remain out of the model view.
        """
        return {
            "operation_ref": self.operation_ref,
            "resource_type": self.resource_type,
            "information_goal": self.information_goal,
            "execution_id": self.execution_id,
            "data": bounded_model_evidence(
                dict(self.data)
            ),
            "evidence_ids": list(self.evidence_ids),
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class InvestigationEvidenceWorkspace:
    _evidence: list[InvestigationEvidence] = field(
        default_factory=list
    )

    def add(self, evidence: InvestigationEvidence) -> None:
        self._evidence.append(evidence)

    def entries(self) -> tuple[InvestigationEvidence, ...]:
        return tuple(self._evidence)

    def model_evidence(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            item.model_view()
            for item in self._evidence
        )


@dataclass(frozen=True, slots=True)
class GovernedInvestigationExecutor:
    broker: IntegrationBroker
    grounding: GroundedConversationIntentBuilder

    def execute(
        self,
        *,
        decision: InvestigationDecision,
        human_text: str,
        context: DynamicConversationContext,
        executor: GovernedConversationIntentExecutor,
        workspace: InvestigationEvidenceWorkspace,
    ) -> InvestigationEvidence:
        if decision.kind is not InvestigationDecisionKind.INSPECT:
            raise InvestigationExecutionError(
                "only inspect decisions may execute"
            )

        operation_ref = (
            decision.operation_ref
            or ""
        ).strip()

        information_goal = (
            decision.information_goal
            or ""
        ).strip()

        if not operation_ref or not information_goal:
            raise InvestigationExecutionError(
                "inspect decision is incomplete"
            )

        target = resolve_operation_ref(
            self.broker,
            operation_ref,
        )

        if not target.operation.read_only:
            raise InvestigationExecutionError(
                "investigation execution is observe-only"
            )

        intent = self._build_intent(
            target=target,
            human_text=human_text,
            context=context,
        )

        result = executor.execute(intent)

        verified_resource = (
            self._observe_verified_resource(
                target=target,
                human_text=human_text,
                intent=intent,
                result=result,
            )
        )

        evidence = self._capture(
            target=target,
            decision=decision,
            result=result,
            verified_resource=verified_resource,
        )

        workspace.add(evidence)

        return evidence

    def _build_intent(
        self,
        *,
        target,
        human_text: str,
        context: DynamicConversationContext,
    ) -> ConversationIntent:
        selector_names = tuple(
            target.operation.selector_names
        )

        arguments: dict[str, Any] = {}

        if selector_names:
            selector_definitions = {
                selector.name: selector
                for selector in target.resource.selectors
            }

            selector_source_policy = {}
            selectors_requiring_grounding = []

            for selector_name in selector_names:
                definition = selector_definitions.get(
                    selector_name
                )

                if definition is None:
                    raise InvestigationExecutionError(
                        "broker operation references an "
                        "undeclared selector"
                    )

                if definition.verified_identity_required:
                    selector_source_policy[
                        selector_name
                    ] = "verified_entity_only"

                    active_ref = (
                        context.active_entity_refs.get(
                            target.resource.resource_type
                        )
                    )

                    if active_ref:
                        try:
                            entity = context.entity(
                                active_ref
                            )
                        except KeyError:
                            entity = None

                        if (
                            entity is not None
                            and entity.kind
                            == target.resource.resource_type
                        ):
                            arguments[
                                selector_name
                            ] = entity.canonical_id
                            continue

                selectors_requiring_grounding.append(
                    selector_name
                )

            offered = OfferedConversationCapability(
                capability_id=target.operation_ref,
                description=target.operation.description,
                provider=None,
                input_schema={
                    "selector_keys": tuple(
                        selectors_requiring_grounding
                    ),
                    "selector_source_policy": (
                        selector_source_policy
                    ),
                },
                output_schema={},
                permission_mode="observe",
                risk="low",
            )

            active_entity_refs = tuple(
                dict.fromkeys(
                    str(ref)
                    for ref
                    in context.active_entity_refs.values()
                    if str(ref).strip()
                )
            )

            plan = DynamicConversationPlan(
                outcome="plan",
                requirements=(
                    DynamicCapabilityRequirement(
                        capability_id=target.operation_ref,
                        purpose=human_text,
                        entity_refs=active_entity_refs,
                    ),
                ),
            )

            grounded = None

            if selectors_requiring_grounding:
                try:
                    grounded = self.grounding.build(
                        text=human_text,
                        context=context,
                        plan=plan,
                        capabilities=(offered,),
                    )
                except DynamicIntentBindingError as exc:
                    if target.operation.collection_supported:
                        grounded = None
                    else:
                        raise InvestigationExecutionError(
                            "selected investigation operation "
                            "requires a safely grounded selector"
                        ) from exc

            if isinstance(
                grounded,
                ConversationIntent,
            ):
                arguments.update(
                    dict(grounded.arguments)
                )

        grounded_selector_names = tuple(
            selector_name
            for selector_name in selector_names
            if str(
                arguments.get(
                    selector_name,
                    "",
                )
            ).strip()
        )

        if (
            selector_names
            and not grounded_selector_names
            and not target.operation.collection_supported
        ):
            raise InvestigationExecutionError(
                "selector-only investigation operation "
                "has no grounded selector"
            )

        if grounded_selector_names:
            arguments = {
                selector_name: arguments[selector_name]
                for selector_name in grounded_selector_names
            }
        elif selector_names:
            arguments = {}

        return ConversationIntent(
            capability_name=target.operation.capability_name,
            arguments=arguments,
            execution_mode="deterministic",
            permission_mode="observe",
            risk="low",
        )

    @staticmethod
    def _observe_verified_resource(
        *,
        target,
        human_text: str,
        intent: ConversationIntent,
        result,
    ) -> VerifiedConversationResourceObservation | None:
        """Promote only one literally grounded discovery selector.

        The selector must already have survived Jason's normal grounding
        contract and must occur verbatim in the human message. It is used
        only as the conversational mention; durable identity still comes
        exclusively from governed result evidence.
        """

        selector_definitions = {
            selector.name: selector
            for selector in target.resource.selectors
        }

        candidates = []

        for selector_name in target.operation.selector_names:
            definition = selector_definitions.get(
                selector_name
            )

            if (
                definition is None
                or definition.verified_identity_required
            ):
                continue

            value = str(
                intent.arguments.get(
                    selector_name,
                    "",
                )
            ).strip()

            if (
                value
                and value in human_text
            ):
                candidates.append(
                    value
                )

        candidates = list(
            dict.fromkeys(
                candidates
            )
        )

        if len(candidates) != 1:
            return None

        return observe_verified_resource_identity(
            kind=target.resource.resource_type,
            mention=candidates[0],
            expected_capability_name=(
                target.operation.capability_name
            ),
            result=result,
        )

    @staticmethod
    def _capture(
        *,
        target,
        decision: InvestigationDecision,
        result,
        verified_resource: (
            VerifiedConversationResourceObservation | None
        ) = None,
    ) -> InvestigationEvidence:
        raw_status = getattr(
            result,
            "status",
            "",
        )

        status = str(
            getattr(
                raw_status,
                "value",
                raw_status,
            )
        ).strip().casefold()

        if status != "succeeded":
            raise InvestigationExecutionError(
                "governed investigation read did not succeed"
            )

        output = getattr(
            result,
            "output",
            None,
        )

        if not isinstance(output, Mapping):
            raise InvestigationExecutionError(
                "governed investigation result has no output"
            )

        provider_id = str(
            getattr(result, "provider_id", "")
            or output.get("provider", "")
        ).strip()

        capability_name = str(
            getattr(result, "capability_name", "")
            or target.operation.capability_name
        ).strip()

        if (
            capability_name
            != target.operation.capability_name
        ):
            raise InvestigationExecutionError(
                "governed result capability does not "
                "match selected broker operation"
            )

        if (
            provider_id
            and provider_id
            != target.integration.provider_id
        ):
            raise InvestigationExecutionError(
                "governed result provider does not "
                "match selected broker integration"
            )

        raw_data = output.get(
            "data",
            {},
        )

        if not isinstance(raw_data, Mapping):
            raise InvestigationExecutionError(
                "governed investigation data must be an object"
            )

        evidence_ids = output.get(
            "evidence_ids",
            (),
        )

        warnings = output.get(
            "warnings",
            (),
        )

        return InvestigationEvidence(
            operation_ref=target.operation_ref,
            resource_type=target.resource.resource_type,
            information_goal=(
                decision.information_goal
                or ""
            ),
            execution_id=str(
                getattr(result, "execution_id", "")
            ),
            correlation_id=str(
                getattr(result, "correlation_id", "")
            ),
            provider_id=(
                provider_id
                or target.integration.provider_id
            ),
            capability_name=capability_name,
            data=dict(raw_data),
            evidence_ids=tuple(
                str(item)
                for item in evidence_ids
            ),
            warnings=tuple(
                str(item)
                for item in warnings
            ),
            verified_resource=verified_resource,
        )
