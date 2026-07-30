from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from connectors.core.contracts import AuditSink, ConnectorRequest, ConnectorResult
from connectors.core.mutations import ApprovalResolver, MutationPlan, MutationPolicy, RiskLevel, require_mutation_authority


class ItGlueMutationConnector:
    provider_name = "it_glue"
    policies = {
        "it_glue.document.create": MutationPolicy("it_glue.document.create", RiskLevel.MEDIUM),
        "it_glue.document.update": MutationPolicy("it_glue.document.update", RiskLevel.MEDIUM),
        "it_glue.flexible_asset.create": MutationPolicy("it_glue.flexible_asset.create", RiskLevel.MEDIUM),
        "it_glue.flexible_asset.update": MutationPolicy("it_glue.flexible_asset.update", RiskLevel.MEDIUM),
        "it_glue.configuration.update": MutationPolicy("it_glue.configuration.update", RiskLevel.MEDIUM),
    }
    capabilities = frozenset(policies)

    def __init__(self, *, audit: AuditSink, approvals: ApprovalResolver | None = None) -> None:
        self._audit = audit
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
            raise RuntimeError("IT Glue live mutation executor is not configured.")
        return ConnectorResult(request.context.capability, self.provider_name, {"status": "proposed", "argument_digest": digest, "plan": self._plan_data(plan)})

    def _build_plan(self, request: ConnectorRequest) -> MutationPlan:
        a = request.arguments
        capability = request.context.capability
        organization_id = int(a["organization_id"])
        target: dict[str, Any] = {"organization_id": organization_id}

        if capability == "it_glue.document.create":
            changes = self._required(a, "name", "content", "folder_id")
        elif capability == "it_glue.document.update":
            target["document_id"] = int(a["document_id"])
            changes = self._at_least_one(a, "name", "content", "folder_id")
        elif capability == "it_glue.flexible_asset.create":
            changes = self._required(a, "flexible_asset_type_id", "name", "traits")
        elif capability == "it_glue.flexible_asset.update":
            target["flexible_asset_id"] = int(a["flexible_asset_id"])
            changes = self._at_least_one(a, "name", "traits")
        elif capability == "it_glue.configuration.update":
            target["configuration_id"] = int(a["configuration_id"])
            changes = self._at_least_one(a, "name", "notes", "configuration_status_id", "contact_id", "location_id")
        else:
            raise ValueError(f"Unsupported capability: {capability}")

        return MutationPlan(
            capability=capability,
            provider=self.provider_name,
            risk=self.policies[capability].risk,
            target=target,
            proposed_changes=changes,
            preconditions=("principal_authorized", "organization_scope_valid", "existing_object_rechecked", "structured_object_preferred_over_document"),
            rollback_notes=("Capture the prior object representation.", "Restore prior values using a compensating update when possible."),
        )

    @staticmethod
    def _required(arguments: Mapping[str, Any], *names: str) -> dict[str, Any]:
        missing = [name for name in names if arguments.get(name) in (None, "")]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        return {name: arguments[name] for name in names}

    @staticmethod
    def _at_least_one(arguments: Mapping[str, Any], *names: str) -> dict[str, Any]:
        values = {name: arguments[name] for name in names if name in arguments}
        if not values:
            raise ValueError("At least one approved field must be supplied.")
        return values

    @staticmethod
    def _plan_data(plan: MutationPlan) -> Mapping[str, Any]:
        return {"capability": plan.capability, "provider": plan.provider, "risk": plan.risk.value, "target": dict(plan.target), "proposed_changes": dict(plan.proposed_changes), "preconditions": list(plan.preconditions), "rollback_notes": list(plan.rollback_notes)}
