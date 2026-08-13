from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


_ALLOWED_CONTEXT_VIEWS = frozenset({
    "semantic_knowledge",
    "capability_registry",
    "system_registry",
    "evidence_catalog",
    "derivation_registry",
})

_FORBIDDEN_PLAN_KEYS = frozenset({
    "provider",
    "provider_name",
    "connector",
    "connector_name",
    "tool",
    "tool_name",
    "agent",
    "target_agent",
    "shell",
    "command",
    "url",
    "credential",
    "credentials",
    "secret",
})


@dataclass(frozen=True, slots=True)
class IntentPlanningBudget:
    max_iterations: int = 6
    max_context_requests: int = 6

    def __post_init__(self) -> None:
        if not (1 <= self.max_iterations <= 20):
            raise ValueError("max_iterations must be between 1 and 20")
        if not (0 <= self.max_context_requests <= 20):
            raise ValueError("max_context_requests must be between 0 and 20")


@dataclass(frozen=True, slots=True)
class PlanningContextRequest:
    view: str
    query: Mapping[str, Any] = field(default_factory=dict)
    purpose: str = ""

    def __post_init__(self) -> None:
        if self.view not in _ALLOWED_CONTEXT_VIEWS:
            raise PermissionError(f"planning context view is not governed: {self.view}")
        _reject_forbidden_keys(self.query)


@dataclass(frozen=True, slots=True)
class FulfillmentPlanStepCandidate:
    capability_name: str
    purpose: str
    required_facts: tuple[str, ...] = ()
    expected_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.capability_name.strip():
            raise ValueError("capability_name is required")
        if not self.purpose.strip():
            raise ValueError("plan step purpose is required")


@dataclass(frozen=True, slots=True)
class FulfillmentPlanCandidate:
    steps: tuple[FulfillmentPlanStepCandidate, ...]
    rationale_summary: str
    unresolved_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.steps and not self.unresolved_requirements:
            raise ValueError("plan must contain steps or unresolved requirements")
        if not self.rationale_summary.strip():
            raise ValueError("plan rationale summary is required")


@dataclass(frozen=True, slots=True)
class PlanningTurn:
    status: str
    context_request: PlanningContextRequest | None = None
    plan: FulfillmentPlanCandidate | None = None
    gap_summary: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"request_context", "propose_plan", "declare_gap"}:
            raise ValueError("planning turn status is invalid")
        if self.status == "request_context" and self.context_request is None:
            raise ValueError("request_context turn requires context_request")
        if self.status == "propose_plan" and self.plan is None:
            raise ValueError("propose_plan turn requires plan")
        if self.status == "declare_gap" and not str(self.gap_summary or "").strip():
            raise ValueError("declare_gap turn requires gap_summary")


@dataclass(frozen=True, slots=True)
class PlanningTraceEntry:
    iteration: int
    status: str
    context_view: str | None = None


@dataclass(frozen=True, slots=True)
class IntentPlanningOutcome:
    status: str
    plan: FulfillmentPlanCandidate | None
    gap_summary: str | None
    trace: tuple[PlanningTraceEntry, ...]
    iterations_used: int
    context_requests_used: int


class SemanticIntentPlanningReasoner(Protocol):
    def next_turn(
        self,
        *,
        intent: Mapping[str, Any],
        context: Mapping[str, Any],
        history: Sequence[PlanningTraceEntry],
    ) -> PlanningTurn: ...


class GovernedPlanningContextReader(Protocol):
    def read(
        self,
        *,
        request: PlanningContextRequest,
        intent: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class IntentPlanningContextBootstrapper(Protocol):
    def requests_for(
        self,
        *,
        intent: Mapping[str, Any],
    ) -> Sequence[PlanningContextRequest]: ...


class IntentPlanSufficiencyValidator(Protocol):
    def validate(
        self,
        *,
        intent: Mapping[str, Any],
        plan: FulfillmentPlanCandidate,
        context: Mapping[str, Any],
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class BoundedSemanticIntentPlanningLoop:
    reasoner: SemanticIntentPlanningReasoner
    context_reader: GovernedPlanningContextReader
    budget: IntentPlanningBudget = IntentPlanningBudget()
    context_bootstrapper: IntentPlanningContextBootstrapper | None = None
    plan_validator: IntentPlanSufficiencyValidator | None = None

    def plan(self, *, intent: Mapping[str, Any]) -> IntentPlanningOutcome:
        _reject_forbidden_keys(intent)
        context: dict[str, Any] = {}
        trace: list[PlanningTraceEntry] = []
        context_requests = 0
        satisfied_requests: set[tuple[str, str]] = set()
        reconciled_satisfied_requests: set[tuple[str, str]] = set()
        rejected_plan_signatures: set[str] = set()

        if self.context_bootstrapper is not None:
            bootstrap_requests = tuple(self.context_bootstrapper.requests_for(intent=dict(intent)))
            if len(bootstrap_requests) > 5:
                raise ValueError("planning bootstrap context request limit exceeded")
            for request in bootstrap_requests:
                snapshot = self.context_reader.read(request=request, intent=dict(intent))
                _reject_forbidden_keys(snapshot)
                request_signature = (
                    request.view,
                    repr(sorted((str(key), repr(value)) for key, value in request.query.items())),
                )
                satisfied_requests.add(request_signature)
                context[request.view] = dict(snapshot)

        for iteration in range(1, self.budget.max_iterations + 1):
            turn = self.reasoner.next_turn(
                intent=dict(intent),
                context=dict(context),
                history=tuple(trace),
            )

            if turn.status == "request_context":
                assert turn.context_request is not None
                if context_requests >= self.budget.max_context_requests:
                    return IntentPlanningOutcome(
                        status="budget_exhausted",
                        plan=None,
                        gap_summary="planning context-request budget exhausted",
                        trace=tuple(trace),
                        iterations_used=iteration,
                        context_requests_used=context_requests,
                    )
                request = turn.context_request
                request_signature = (
                    request.view,
                    repr(sorted((str(key), repr(value)) for key, value in request.query.items())),
                )
                if request_signature in satisfied_requests:
                    if request_signature in reconciled_satisfied_requests:
                        return IntentPlanningOutcome(
                            status="knowledge_gap",
                            plan=None,
                            gap_summary=(
                                "planning reasoner repeated an already-satisfied governed context request "
                                "after explicit reconciliation feedback"
                            ),
                            trace=tuple(trace),
                            iterations_used=iteration,
                            context_requests_used=context_requests,
                        )
                    reconciled_satisfied_requests.add(request_signature)
                    context["context_request_feedback"] = {
                        "status": "already_satisfied",
                        "view": request.view,
                        "query": dict(request.query),
                        "instruction": (
                            "The requested governed context is already present in governed_context. "
                            "Do not request it again. Consume the existing snapshot, request a different "
                            "governed information need, revise the plan, or declare a knowledge gap."
                        ),
                    }
                    trace.append(PlanningTraceEntry(iteration, "context_reconciled", request.view))
                    continue
                snapshot = self.context_reader.read(request=request, intent=dict(intent))
                _reject_forbidden_keys(snapshot)
                context.pop("context_request_feedback", None)
                satisfied_requests.add(request_signature)
                context_requests += 1
                context[request.view] = dict(snapshot)
                trace.append(PlanningTraceEntry(iteration, turn.status, request.view))
                continue

            if turn.status == "propose_plan":
                assert turn.plan is not None
                _validate_plan_against_governed_capabilities(turn.plan, context)
                if self.plan_validator is not None:
                    validation = self.plan_validator.validate(
                        intent=dict(intent),
                        plan=turn.plan,
                        context=dict(context),
                    )
                    if not bool(getattr(validation, "sufficient", False)):
                        issues = tuple(str(item) for item in getattr(validation, "issues", ()))
                        signature = repr((turn.plan.steps, turn.plan.unresolved_requirements, issues))
                        if signature in rejected_plan_signatures:
                            trace.append(PlanningTraceEntry(iteration, "plan_rejected"))
                            return IntentPlanningOutcome(
                                status="knowledge_gap",
                                plan=None,
                                gap_summary=(
                                    "planning reasoner repeated a plan that did not satisfy the original intent"
                                ),
                                trace=tuple(trace),
                                iterations_used=iteration,
                                context_requests_used=context_requests,
                            )
                        rejected_plan_signatures.add(signature)
                        context["plan_validation"] = {
                            "sufficient": False,
                            "issues": issues,
                            "instruction": (
                                "Revise the plan using governed context, request different governed context, "
                                "or declare a knowledge gap. Do not repeat the rejected plan."
                            ),
                        }
                        trace.append(PlanningTraceEntry(iteration, "plan_rejected"))
                        continue
                trace.append(PlanningTraceEntry(iteration, turn.status))
                return IntentPlanningOutcome(
                    status="planned",
                    plan=turn.plan,
                    gap_summary=None,
                    trace=tuple(trace),
                    iterations_used=iteration,
                    context_requests_used=context_requests,
                )

            trace.append(PlanningTraceEntry(iteration, turn.status))
            return IntentPlanningOutcome(
                status="knowledge_gap",
                plan=None,
                gap_summary=str(turn.gap_summary),
                trace=tuple(trace),
                iterations_used=iteration,
                context_requests_used=context_requests,
            )

        return IntentPlanningOutcome(
            status="budget_exhausted",
            plan=None,
            gap_summary="planning iteration budget exhausted",
            trace=tuple(trace),
            iterations_used=self.budget.max_iterations,
            context_requests_used=context_requests,
        )


def _validate_plan_against_governed_capabilities(
    plan: FulfillmentPlanCandidate,
    context: Mapping[str, Any],
) -> None:
    capability_snapshot = context.get("capability_registry")
    if not isinstance(capability_snapshot, Mapping):
        raise PermissionError("plan cannot be accepted without governed capability-registry context")
    raw_names = capability_snapshot.get("capability_names", ())
    if not isinstance(raw_names, (list, tuple, set, frozenset)):
        raise ValueError("capability registry snapshot must expose capability_names")
    allowed = {str(item).strip() for item in raw_names if str(item).strip()}
    for step in plan.steps:
        if step.capability_name not in allowed:
            raise PermissionError(
                f"planning reasoner selected capability outside governed registry: {step.capability_name}"
            )


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().casefold()
            if key in _FORBIDDEN_PLAN_KEYS:
                raise PermissionError(f"planning contract contains prohibited direct-routing field: {raw_key}")
            _reject_forbidden_keys(child)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            _reject_forbidden_keys(child)
