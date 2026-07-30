from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters import (
    AuditProvider,
    ContextValidator,
    EvidenceProvider,
    MemoryProvider,
    ReasoningProvider,
    TransitionProvider,
)
from .quality import QualityGateResult, evaluate_reasoning_result
from .validation import validate_document
from .workflow import InvestigationWorkflow, WorkflowState


@dataclass(frozen=True, slots=True)
class InvestigationRun:
    case_package: dict[str, Any]
    reasoning_result: dict[str, Any]
    quality: QualityGateResult
    final_state: WorkflowState


class InvestigationService:
    """Read-only CAP-001 orchestrator with bounded authority and durable audit hooks.

    The service does not call another agent, modify a provider, grant authority,
    or treat retrieved content as executable instructions. It coordinates named
    capabilities and applies deterministic gates.
    """

    def __init__(
        self,
        *,
        evidence: EvidenceProvider,
        reasoning: ReasoningProvider,
        memory: MemoryProvider,
        audit: AuditProvider,
        context_validator: ContextValidator | None = None,
        transitions: TransitionProvider | None = None,
    ) -> None:
        self._evidence = evidence
        self._reasoning = reasoning
        self._memory = memory
        self._audit = audit
        self._context_validator = context_validator
        self._transitions = transitions

    def _transition(
        self,
        workflow: InvestigationWorkflow,
        to_state: WorkflowState,
        reason: str,
        *,
        correlation_id: str,
        case_id: str | None = None,
    ) -> None:
        transition = workflow.transition(to_state, reason)
        payload = {
            "correlation_id": correlation_id,
            "case_id": case_id,
            "from_state": transition.from_state.value,
            "to_state": transition.to_state.value,
            "reason": transition.reason,
        }
        self._audit.append("workflow.transitioned", payload)
        if self._transitions is not None:
            self._transitions.record_transition(
                correlation_id=correlation_id,
                case_id=case_id,
                from_state=transition.from_state.value,
                to_state=transition.to_state.value,
                reason=transition.reason,
            )

    def investigate(self, request: dict[str, Any]) -> InvestigationRun:
        validate_document("investigation_request", request)
        workflow = InvestigationWorkflow()
        context = request["execution_context"]
        ticket = request["ticket"]
        correlation_id = request["correlation_id"]
        case_id = f"case-{request['request_id']}"

        try:
            if self._context_validator is not None:
                self._context_validator.validate(request)
            elif context["client_id"] != ticket["client_id"]:
                raise PermissionError("Ticket and execution context client scopes differ.")
        except PermissionError as exc:
            self._transition(
                workflow,
                WorkflowState.REJECTED,
                str(exc),
                correlation_id=correlation_id,
                case_id=case_id,
            )
            self._audit.append(
                "capability.rejected",
                {
                    "correlation_id": correlation_id,
                    "case_id": case_id,
                    "client_id": context.get("client_id"),
                    "reason": "context_validation_failed",
                },
            )
            raise

        self._transition(
            workflow,
            WorkflowState.CONTEXT_VALIDATED,
            "Request contract, authority, and client context validated.",
            correlation_id=correlation_id,
            case_id=case_id,
        )
        self._audit.append(
            "execution_context.validated",
            {
                "correlation_id": correlation_id,
                "case_id": case_id,
                "client_id": context["client_id"],
                "context_id": context["context_id"],
                "requester_id": context["requester_id"],
            },
        )

        evidence = self._evidence.collect(request, client_id=context["client_id"])
        if any(item.get("client_id") != context["client_id"] for item in evidence):
            self._transition(
                workflow,
                WorkflowState.REJECTED,
                "Evidence crossed the authorized client boundary.",
                correlation_id=correlation_id,
                case_id=case_id,
            )
            self._audit.append(
                "client_boundary.violation_attempted",
                {
                    "correlation_id": correlation_id,
                    "case_id": case_id,
                    "client_id": context["client_id"],
                },
            )
            raise PermissionError("Evidence client scope mismatch.")

        self._transition(
            workflow,
            WorkflowState.EVIDENCE_COLLECTED,
            "Authorized evidence collection completed.",
            correlation_id=correlation_id,
            case_id=case_id,
        )
        case_package = {
            "schema_version": "0.1",
            "case_id": case_id,
            "correlation_id": correlation_id,
            "client_id": context["client_id"],
            "ticket": ticket,
            "evidence": evidence,
            "observations": [],
            "missing_information": [],
            "similar_case_references": [],
        }
        validate_document("case_package", case_package)
        self._transition(
            workflow,
            WorkflowState.CASE_NORMALIZED,
            "Evidence normalized into the CAP-001 case contract.",
            correlation_id=correlation_id,
            case_id=case_id,
        )
        self._memory.record_case(case_package)

        reasoning_result = self._reasoning.analyze(case_package)
        validate_document("reasoning_result", reasoning_result)
        if reasoning_result["case_id"] != case_package["case_id"]:
            self._transition(
                workflow,
                WorkflowState.REJECTED,
                "Reasoning result case identity does not match the request.",
                correlation_id=correlation_id,
                case_id=case_id,
            )
            raise ValueError("Reasoning result case mismatch.")

        self._transition(
            workflow,
            WorkflowState.REASONING_COMPLETE,
            "Structured reasoning result received.",
            correlation_id=correlation_id,
            case_id=case_id,
        )
        evidence_ids = {item["evidence_id"] for item in evidence}
        quality = evaluate_reasoning_result(reasoning_result, evidence_ids)
        self._transition(
            workflow,
            WorkflowState.QUALITY_GATED,
            "Deterministic quality gate completed.",
            correlation_id=correlation_id,
            case_id=case_id,
        )
        if not quality.passed:
            self._transition(
                workflow,
                WorkflowState.ESCALATION_REQUIRED,
                "Reasoning result failed deterministic safety checks.",
                correlation_id=correlation_id,
                case_id=case_id,
            )
            self._audit.append(
                "capability.quality_failed",
                {
                    "case_id": case_id,
                    "correlation_id": correlation_id,
                    "client_id": context["client_id"],
                    "finding_codes": [item.code for item in quality.findings],
                },
            )
            return InvestigationRun(case_package, reasoning_result, quality, workflow.state)

        self._memory.record_result(reasoning_result)
        self._transition(
            workflow,
            WorkflowState.RESPONSE_READY,
            "Reasoning result passed all deterministic quality checks.",
            correlation_id=correlation_id,
            case_id=case_id,
        )
        self._audit.append(
            "capability.recommendation_ready",
            {
                "case_id": case_id,
                "correlation_id": correlation_id,
                "client_id": context["client_id"],
            },
        )
        return InvestigationRun(case_package, reasoning_result, quality, workflow.state)
