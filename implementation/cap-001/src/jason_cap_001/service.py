from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters import AuditProvider, EvidenceProvider, MemoryProvider, ReasoningProvider
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
    """Reference read-only CAP-001 orchestrator.

    The service does not call another agent, modify a provider, or grant authority.
    It coordinates named provider capabilities and applies deterministic gates.
    """

    def __init__(
        self,
        *,
        evidence: EvidenceProvider,
        reasoning: ReasoningProvider,
        memory: MemoryProvider,
        audit: AuditProvider,
    ) -> None:
        self._evidence = evidence
        self._reasoning = reasoning
        self._memory = memory
        self._audit = audit

    def investigate(self, request: dict[str, Any]) -> InvestigationRun:
        validate_document("investigation_request", request)
        workflow = InvestigationWorkflow()
        context = request["execution_context"]
        ticket = request["ticket"]

        if context["client_id"] != ticket["client_id"]:
            workflow.transition(WorkflowState.REJECTED, "Ticket and execution context client scopes differ.")
            self._audit.append("capability.rejected", {"correlation_id": request["correlation_id"], "reason": "client_scope_mismatch"})
            raise PermissionError("Client scope mismatch.")

        workflow.transition(WorkflowState.CONTEXT_VALIDATED, "Request contract and client context validated.")
        evidence = self._evidence.collect(request, client_id=context["client_id"])
        if any(item.get("client_id") != context["client_id"] for item in evidence):
            workflow.transition(WorkflowState.REJECTED, "Evidence crossed the authorized client boundary.")
            raise PermissionError("Evidence client scope mismatch.")

        workflow.transition(WorkflowState.EVIDENCE_COLLECTED, "Authorized evidence collection completed.")
        case_package = {
            "schema_version": "0.1",
            "case_id": f"case-{request['request_id']}",
            "correlation_id": request["correlation_id"],
            "client_id": context["client_id"],
            "ticket": ticket,
            "evidence": evidence,
            "observations": [],
            "missing_information": [],
            "similar_case_references": [],
        }
        validate_document("case_package", case_package)
        workflow.transition(WorkflowState.CASE_NORMALIZED, "Evidence normalized into the CAP-001 case contract.")
        self._memory.record_case(case_package)

        reasoning_result = self._reasoning.analyze(case_package)
        validate_document("reasoning_result", reasoning_result)
        if reasoning_result["case_id"] != case_package["case_id"]:
            workflow.transition(WorkflowState.REJECTED, "Reasoning result case identity does not match the request.")
            raise ValueError("Reasoning result case mismatch.")

        workflow.transition(WorkflowState.REASONING_COMPLETE, "Structured reasoning result received.")
        evidence_ids = {item["evidence_id"] for item in evidence}
        quality = evaluate_reasoning_result(reasoning_result, evidence_ids)
        workflow.transition(WorkflowState.QUALITY_GATED, "Deterministic quality gate completed.")
        if not quality.passed:
            workflow.transition(WorkflowState.ESCALATION_REQUIRED, "Reasoning result failed deterministic safety checks.")
            self._audit.append("capability.quality_failed", {"case_id": case_package["case_id"], "finding_codes": [item.code for item in quality.findings]})
            return InvestigationRun(case_package, reasoning_result, quality, workflow.state)

        self._memory.record_result(reasoning_result)
        workflow.transition(WorkflowState.RESPONSE_READY, "Reasoning result passed all deterministic quality checks.")
        self._audit.append("capability.recommendation_ready", {"case_id": case_package["case_id"], "correlation_id": request["correlation_id"]})
        return InvestigationRun(case_package, reasoning_result, quality, workflow.state)
