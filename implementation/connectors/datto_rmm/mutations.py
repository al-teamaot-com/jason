from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from connectors.core.contracts import AuditSink, ConnectorRequest, ConnectorResult
from connectors.core.mutations import ApprovalResolver, MutationPlan, MutationPolicy, RiskLevel, require_mutation_authority


class DattoRmmMutationConnector:
    """Planning and approval boundary for Datto RMM actions.

    Live execution remains disabled until each component/action is explicitly
    allowlisted and its vendor API contract is verified.
    """

    provider_name = "datto_rmm"
    policies = {
        "datto_rmm.component.run": MutationPolicy("datto_rmm.component.run", RiskLevel.HIGH),
        "datto_rmm.device.reboot.schedule": MutationPolicy("datto_rmm.device.reboot.schedule", RiskLevel.HIGH),
        "datto_rmm.alert.resolve": MutationPolicy("datto_rmm.alert.resolve", RiskLevel.MEDIUM),
        "datto_rmm.device.udf.update": MutationPolicy("datto_rmm.device.udf.update", RiskLevel.MEDIUM),
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
        digest = self._digest(plan)
        require_mutation_authority(
            request,
            policy,
            argument_digest=digest,
            approval_resolver=self._approvals,
            audit=self._audit,
        )
        self._audit.record("connector.mutation.planned", request.context, {"provider": self.provider_name, "digest": digest})
        if request.context.mode != "propose":
            raise RuntimeError("Datto RMM live mutation executor is not configured.")
        return ConnectorResult(
            request.context.capability,
            self.provider_name,
            {"status": "proposed", "argument_digest": digest, "plan": self._plan_data(plan)},
            warnings=plan.warnings,
        )

    def _build_plan(self, request: ConnectorRequest) -> MutationPlan:
        a = request.arguments
        capability = request.context.capability
        device_uid = a.get("device_uid")
        if not isinstance(device_uid, str) or not device_uid.strip():
            raise ValueError("device_uid is required.")
        target: dict[str, Any] = {"device_uid": device_uid.strip()}

        if capability == "datto_rmm.component.run":
            component_uid = a.get("component_uid")
            if not isinstance(component_uid, str) or not component_uid.strip():
                raise ValueError("component_uid is required.")
            allowlist_name = a.get("allowlist_name")
            if not isinstance(allowlist_name, str) or not allowlist_name.strip():
                raise ValueError("An approved component allowlist name is required.")
            changes = {"component_uid": component_uid.strip(), "variables": dict(a.get("variables", {})), "allowlist_name": allowlist_name.strip()}
            warnings = ("Component execution can alter endpoint state.",)
        elif capability == "datto_rmm.device.reboot.schedule":
            execute_at = a.get("execute_at")
            if not isinstance(execute_at, str) or not execute_at.strip():
                raise ValueError("execute_at is required.")
            changes = {"execute_at": execute_at.strip(), "user_notification": a.get("user_notification", True)}
            warnings = ("A reboot can interrupt active users and services.",)
        elif capability == "datto_rmm.alert.resolve":
            alert_uid = a.get("alert_uid")
            if not isinstance(alert_uid, str) or not alert_uid.strip():
                raise ValueError("alert_uid is required.")
            target["alert_uid"] = alert_uid.strip()
            changes = {"resolution_note": str(a.get("resolution_note", "")).strip()}
            warnings = ()
        elif capability == "datto_rmm.device.udf.update":
            udf_number = int(a["udf_number"])
            if udf_number < 1:
                raise ValueError("udf_number must be positive.")
            changes = {"udf_number": udf_number, "value": a.get("value")}
            warnings = ()
        else:
            raise ValueError(f"Unsupported capability: {capability}")

        return MutationPlan(
            capability=capability,
            provider=self.provider_name,
            risk=self.policies[capability].risk,
            target=target,
            proposed_changes=changes,
            preconditions=("principal_authorized", "client_scope_valid", "device_identity_reconfirmed", "action_allowlisted"),
            rollback_notes=("Capture pre-action state.", "Use a compensating action only when vendor-supported."),
            warnings=warnings,
        )

    @staticmethod
    def _plan_data(plan: MutationPlan) -> Mapping[str, Any]:
        return {"capability": plan.capability, "provider": plan.provider, "risk": plan.risk.value, "target": dict(plan.target), "proposed_changes": dict(plan.proposed_changes), "preconditions": list(plan.preconditions), "rollback_notes": list(plan.rollback_notes), "warnings": list(plan.warnings)}

    @classmethod
    def _digest(cls, plan: MutationPlan) -> str:
        return hashlib.sha256(json.dumps(cls._plan_data(plan), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
