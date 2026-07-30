from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from connectors.core.contracts import AuditSink, ConnectorRequest, ConnectorResult
from connectors.core.mutations import ApprovalResolver, MutationPlan, MutationPolicy, RiskLevel, require_mutation_authority


class N8nMutationConnector:
    provider_name = "n8n"
    policies = {
        "n8n.workflow.invoke_write": MutationPolicy("n8n.workflow.invoke_write", RiskLevel.HIGH),
        "n8n.workflow.enable": MutationPolicy("n8n.workflow.enable", RiskLevel.HIGH),
        "n8n.workflow.disable": MutationPolicy("n8n.workflow.disable", RiskLevel.MEDIUM),
    }
    capabilities = frozenset(policies)

    def __init__(
        self,
        *,
        audit: AuditSink,
        approved_workflows: Mapping[str, Mapping[str, Any]],
        approvals: ApprovalResolver | None = None,
    ) -> None:
        self._audit = audit
        self._approved_workflows = dict(approved_workflows)
        self._approvals = approvals

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        policy = self.policies.get(request.context.capability)
        if policy is None:
            raise ValueError(f"Unsupported capability: {request.context.capability}")
        plan = self._build_plan(request)
        digest = hashlib.sha256(json.dumps(self._plan_data(plan), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        require_mutation_authority(request, policy, argument_digest=digest, approval_resolver=self._approvals, audit=self._audit)
        self._audit.record("connector.mutation.planned", request.context, {"provider": self.provider_name, "digest": digest})
        if request.context.mode != "propose":
            raise RuntimeError("n8n live mutation executor is not configured.")
        return ConnectorResult(request.context.capability, self.provider_name, {"status": "proposed", "argument_digest": digest, "plan": self._plan_data(plan)})

    def _build_plan(self, request: ConnectorRequest) -> MutationPlan:
        a = request.arguments
        logical_name = a.get("workflow_name")
        if not isinstance(logical_name, str) or logical_name not in self._approved_workflows:
            raise ValueError("workflow_name must reference an approved logical workflow.")

        registration = self._approved_workflows[logical_name]
        capability = request.context.capability
        allowed_actions = set(registration.get("allowed_actions", ()))
        requested_action = capability.rsplit(".", 1)[-1]
        if requested_action not in allowed_actions:
            raise ValueError("The requested action is not approved for this workflow.")

        parameters = a.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise ValueError("parameters must be an object.")
        allowed_parameters = set(registration.get("allowed_parameters", ()))
        unexpected = set(parameters) - allowed_parameters
        if unexpected:
            raise ValueError(f"Unapproved workflow parameters: {', '.join(sorted(unexpected))}")

        target = {"workflow_name": logical_name}
        changes = {"action": requested_action, "parameters": dict(parameters)}
        return MutationPlan(
            capability=capability,
            provider=self.provider_name,
            risk=self.policies[capability].risk,
            target=target,
            proposed_changes=changes,
            preconditions=("principal_authorized", "workflow_registered", "action_allowlisted", "parameters_allowlisted", "client_scope_valid"),
            rollback_notes=("Workflow-specific compensation must be declared in its registration.",),
            warnings=("n8n is an execution adapter, not an authority boundary.",),
        )

    @staticmethod
    def _plan_data(plan: MutationPlan) -> Mapping[str, Any]:
        return {"capability": plan.capability, "provider": plan.provider, "risk": plan.risk.value, "target": dict(plan.target), "proposed_changes": dict(plan.proposed_changes), "preconditions": list(plan.preconditions), "rollback_notes": list(plan.rollback_notes), "warnings": list(plan.warnings)}
