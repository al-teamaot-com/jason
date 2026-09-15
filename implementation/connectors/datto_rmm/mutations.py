from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from connectors.core.contracts import AuditSink, ConnectorRequest, ConnectorResult
from connectors.core.mutations import (
    ApprovalResolver,
    MutationPlan,
    MutationPolicy,
    RiskLevel,
    require_mutation_authority,
)
from connectors.datto_rmm.component_execution import DattoRmmComponentExecutionPolicy


class DattoRmmMutationConnector:
    """Planning and approval boundary for Datto RMM actions.

    Component proposals may construct and digest the exact provider request, but
    this connector still has no live Datto mutation executor. Production writes
    remain disabled until a later explicit activation step.
    """

    provider_name = "datto_rmm"
    policies = {
        "datto_rmm.component.run": MutationPolicy(
            "datto_rmm.component.run", RiskLevel.HIGH
        ),
        "datto_rmm.device.reboot.schedule": MutationPolicy(
            "datto_rmm.device.reboot.schedule", RiskLevel.HIGH
        ),
        "datto_rmm.alert.resolve": MutationPolicy(
            "datto_rmm.alert.resolve", RiskLevel.MEDIUM
        ),
        "datto_rmm.device.udf.update": MutationPolicy(
            "datto_rmm.device.udf.update", RiskLevel.MEDIUM
        ),
    }
    capabilities = frozenset(policies)

    def __init__(
        self,
        *,
        audit: AuditSink,
        approvals: ApprovalResolver | None = None,
        component_execution_policy: DattoRmmComponentExecutionPolicy | None = None,
    ) -> None:
        self._audit = audit
        self._approvals = approvals
        self._component_execution_policy = component_execution_policy

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
        self._audit.record(
            "connector.mutation.planned",
            request.context,
            {"provider": self.provider_name, "digest": digest},
        )

        # Source/test work may prove the exact request that would be sent, but
        # provider mutation remains intentionally unavailable in every runtime.
        if request.context.mode != "propose":
            raise RuntimeError("Datto RMM live mutation executor is not configured.")

        return ConnectorResult(
            request.context.capability,
            self.provider_name,
            {
                "status": "proposed",
                "argument_digest": digest,
                "plan": self._plan_data(plan),
            },
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
            if not request.context.client_id:
                raise PermissionError(
                    "component execution requires an explicit governed client scope"
                )
            if self._component_execution_policy is None:
                raise RuntimeError(
                    "Datto RMM component execution allowlist policy is not configured."
                )

            component_uid = a.get("component_uid")
            if not isinstance(component_uid, str) or not component_uid.strip():
                raise ValueError("component_uid is required.")

            allowlist_name = a.get("allowlist_name")
            if not isinstance(allowlist_name, str) or not allowlist_name.strip():
                raise ValueError("An approved component allowlist name is required.")

            device_class = a.get("device_class")
            if not isinstance(device_class, str) or not device_class.strip():
                raise ValueError("device_class is required for component execution.")

            variables = a.get("variables", {})
            if not isinstance(variables, Mapping):
                raise ValueError("component variables must be a mapping")

            prepared = self._component_execution_policy.prepare(
                allowlist_name=allowlist_name.strip(),
                device_uid=device_uid.strip(),
                device_class=device_class.strip(),
                component_uid=component_uid.strip(),
                variables=variables,
                job_name=(
                    str(a.get("job_name")).strip()
                    if a.get("job_name") is not None
                    else None
                ),
                observed_component_name=(
                    str(a.get("observed_component_name")).strip()
                    if a.get("observed_component_name") is not None
                    else None
                ),
                observed_metadata_fingerprint=(
                    str(a.get("observed_metadata_fingerprint")).strip()
                    if a.get("observed_metadata_fingerprint") is not None
                    else None
                ),
            )

            reason = str(a.get("reason") or "").strip()
            target["device_class"] = device_class.strip().casefold()
            changes = {
                "component_uid": prepared.allowlist_entry.provider_component_uid,
                "component_name": prepared.allowlist_entry.display_name,
                "allowlist_name": prepared.allowlist_entry.allowlist_name,
                "variables": dict(prepared.normalized_variables),
                "job_name": prepared.job_name,
                # Include reason in the plan digest so an approval cannot be
                # replayed after the human-readable purpose is changed.
                "reason": reason,
                # Bind approval to the exact Datto method/path/body without
                # releasing the provider request as user-facing proposal data.
                "provider_request_digest": prepared.provider_request.digest(),
            }
            warnings = (
                "Component execution can alter endpoint state.",
                "Datto quick jobs run immediately when live execution is later enabled.",
            )

        elif capability == "datto_rmm.device.reboot.schedule":
            execute_at = a.get("execute_at")
            if not isinstance(execute_at, str) or not execute_at.strip():
                raise ValueError("execute_at is required.")
            changes = {
                "execute_at": execute_at.strip(),
                "user_notification": a.get("user_notification", True),
            }
            warnings = ("A reboot can interrupt active users and services.",)

        elif capability == "datto_rmm.alert.resolve":
            alert_uid = a.get("alert_uid")
            if not isinstance(alert_uid, str) or not alert_uid.strip():
                raise ValueError("alert_uid is required.")
            target["alert_uid"] = alert_uid.strip()
            changes = {
                "resolution_note": str(a.get("resolution_note", "")).strip()
            }
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
            preconditions=(
                "principal_authorized",
                "client_scope_valid",
                "device_identity_reconfirmed",
                "action_allowlisted",
            ),
            rollback_notes=(
                "Capture pre-action state.",
                "Use a compensating action only when vendor-supported.",
            ),
            warnings=warnings,
        )

    @staticmethod
    def _plan_data(plan: MutationPlan) -> Mapping[str, Any]:
        return {
            "capability": plan.capability,
            "provider": plan.provider,
            "risk": plan.risk.value,
            "target": dict(plan.target),
            "proposed_changes": dict(plan.proposed_changes),
            "preconditions": list(plan.preconditions),
            "rollback_notes": list(plan.rollback_notes),
            "warnings": list(plan.warnings),
        }

    @classmethod
    def _digest(cls, plan: MutationPlan) -> str:
        return hashlib.sha256(
            json.dumps(
                cls._plan_data(plan),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
